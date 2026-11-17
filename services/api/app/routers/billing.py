"""Planos públicos, checkout, portal de cobrança, webhook Stripe e uso.

O webhook é a ÚNICA porta de entrada de direitos pagos (assinatura verificada + dedupe).
O endpoint `/billing/fake/complete` só existe em modo `fake` fora de produção e passa
pelo MESMO caminho de verificação, para testar o fluxo completo sem Stripe real.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..db import get_db, scoped
from ..deps import Ctx, require_admin, require_member
from ..models import Entitlement, Plan, PlanVersion, Tenant, UsageEvent
from ..services.billing import (stripe_mode, webhook_secret, credit_balance, get_stripe, minutes_remaining, process_webhook,
                                stripe_signature, usage_minutes_used, verify_stripe_signature)

settings = get_settings()
router = APIRouter(tags=["billing"])
_FAKE_SESSIONS: dict[str, dict] = {}  # sessões de checkout simuladas (somente dev)


def plan_out(p: Plan, v: PlanVersion) -> dict:
    return {"plan_id": str(p.id), "plan_version_id": str(v.id), "name": p.public_name, "slug": p.slug,
            "description": p.description, "billing_type": v.billing_type.value, "currency": v.currency,
            "amount_cents": v.amount_cents, "version": v.version, "entitlements": v.entitlements}


@router.get("/plans")
def public_plans(db: Session = Depends(get_db)):
    """Planos publicados (versão mais recente efetiva). Assinantes antigos mantêm a versão que contrataram."""
    out = []
    for p in db.scalars(select(Plan).where(Plan.status == "published").order_by(Plan.created_at)):
        if p.versions:
            out.append(plan_out(p, p.versions[-1]))
    return out


class CheckoutIn(BaseModel):
    plan_version_id: UUID


@router.post("/checkout")
def checkout(body: CheckoutIn, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    pv = db.get(PlanVersion, body.plan_version_id)
    if not pv or pv.plan.status != "published":
        raise HTTPException(404, "Plano não disponível.")
    tenant = db.get(Tenant, ctx.tenant_id)  # tenant vem da membership, nunca do corpo
    s = get_stripe().create_checkout(
        tenant_id=str(ctx.tenant_id), plan_version=pv, customer_id=tenant.stripe_customer_id,
        success_url=f"{settings.public_web_url}/dashboard/billing?status=processing",  # só informativo!
        cancel_url=f"{settings.public_web_url}/dashboard/billing?status=canceled")
    if stripe_mode() == "fake":
        _FAKE_SESSIONS[s["id"]] = {"tenant_id": str(ctx.tenant_id), "plan_version_id": str(pv.id),
                                   "recurring": pv.billing_type.value == "MONTHLY"}
    audit(db, action="billing.checkout_created", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=s["id"], ip=ctx.ip)
    return {"checkout_url": s["url"], "session_id": s["id"]}


@router.post("/billing/portal")
def portal(ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    tenant = db.get(Tenant, ctx.tenant_id)
    if not tenant.stripe_customer_id and stripe_mode() != "fake":
        raise HTTPException(409, "Nenhuma assinatura para gerenciar.")
    return {"url": get_stripe().billing_portal(tenant.stripe_customer_id or "cus_fake", f"{settings.public_web_url}/dashboard/billing")}


@router.post("/billing/webhook/stripe")
async def stripe_webhook(request: Request, stripe_signature_h: str | None = Header(default=None, alias="Stripe-Signature"),
                         db: Session = Depends(get_db)):
    payload = await request.body()
    if not stripe_signature_h or not verify_stripe_signature(
            payload, stripe_signature_h, webhook_secret(), settings.stripe_tolerance_seconds):
        raise HTTPException(400, "Assinatura inválida.")
    try:
        event = json.loads(payload)
    except ValueError:
        raise HTTPException(400, "Payload inválido.")
    outcome = process_webhook(db, event)
    return {"received": True, "outcome": outcome}


@router.post("/billing/fake/complete")
async def fake_complete(session_id: str, request: Request, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    """DEV: simula o pagamento concluído enviando um webhook assinado ao próprio caminho real."""
    if settings.is_prod or stripe_mode() != "fake":
        raise HTTPException(404)
    info = _FAKE_SESSIONS.get(session_id)
    if not info or info["tenant_id"] != str(ctx.tenant_id):
        raise HTTPException(404, "Sessão não encontrada.")
    event = {"id": f"evt_fake_{session_id}", "type": "checkout.session.completed", "data": {"object": {
        "id": session_id, "payment_status": "paid", "subscription": f"sub_fake_{session_id}" if info["recurring"] else None,
        "metadata": {"tenant_id": info["tenant_id"], "plan_version_id": info["plan_version_id"]}}}}
    payload = json.dumps(event).encode()
    assert verify_stripe_signature(payload, stripe_signature(payload, webhook_secret()),
                                   webhook_secret(), settings.stripe_tolerance_seconds)
    return {"outcome": process_webhook(db, event)}


@router.get("/usage")
def usage(ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    ents = db.scalars(scoped(db, Entitlement, ctx.tenant_id).where(Entitlement.active.is_(True))).all()
    return {"language_minutes_used": usage_minutes_used(db, ctx.tenant_id),
            "language_minutes_remaining": minutes_remaining(db, ctx.tenant_id),
            "credits": credit_balance(db, ctx.tenant_id),
            "events_remaining": sum(e.events_remaining for e in ents),
            # horas de transmissão restantes (None = ilimitado); contam desde o início de cada evento
            "event_minutes_remaining": None if any(e.event_minutes_remaining is None for e in ents) else sum(e.event_minutes_remaining for e in ents),
            "entitlements": [{"source": e.source, "events_remaining": e.events_remaining, "limits": e.limits} for e in ents]}
