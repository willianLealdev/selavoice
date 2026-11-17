"""Cobrança: Stripe (real/fake), verificação de webhook, concessão de direitos e cotas.

REGRAS (da spec):
- Direitos (entitlements) só são concedidos APÓS webhook verificado (assinatura HMAC + tolerância
  de tempo) e deduplicado pelo id do evento Stripe. O redirect de sucesso do front NÃO concede nada.
- Pagamento que falha NÃO concede acesso.
- Versões de preço são imutáveis; assinante antigo continua na `plan_version` que contratou.
- Cota consumida em livro-razão append-only; checagem de início de evento é feita com lock.
"""
import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from .plan_schema import UNLIM, grant_amounts, is_unlimited, limit as plan_limit, max_event_minutes
from .platform_settings import get_trial
from .secrets_store import get_secret
from ..models import (BillingType, CreditLedger, Entitlement, Event, EventStatus, OneOffPurchase,
                      PlanVersion, StripeWebhookEvent, Tenant, TenantSubscription, TopupPack, UsageEvent)

settings = get_settings()

def grant_trial(db: Session, tenant_id) -> None:
    """Concede o TESTE GRÁTIS conforme a configuração do painel (Super Admin > Teste grátis). Desligado = não concede.
    Idempotente por organização. Não envolve pagamento."""
    cfg = get_trial(db)
    if not cfg["enabled"]:
        return
    ref = str(tenant_id)
    if db.scalar(select(Entitlement).where(Entitlement.source == "trial", Entitlement.source_ref == ref)):
        return
    limits = cfg["limits"]
    g = grant_amounts(limits)
    expires = datetime.now(timezone.utc) + timedelta(days=cfg["days"]) if cfg["days"] else None
    db.add(Entitlement(tenant_id=tenant_id, source="trial", source_ref=ref, limits=limits, events_remaining=g["events"],
                       language_minutes_remaining=g["language_minutes"], event_minutes_remaining=g["event_minutes"], expires_at=expires))
    db.commit()


# ---------------- Stripe: verificação de assinatura ----------------
def stripe_signature(payload: bytes, secret: str, ts: int | None = None) -> str:
    """Gera o header Stripe-Signature (usado pelo FakeStripe e pelos testes)."""
    ts = ts or int(time.time())
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def verify_stripe_signature(payload: bytes, header: str, secret: str, tolerance: int) -> bool:
    """Valida `Stripe-Signature` (t=timestamp,v1=assinatura) com comparação em tempo constante."""
    if not secret:  # sem segredo configurado NUNCA aceita (HMAC com chave vazia seria forjável)
        return False
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        v1 = [p.split("=", 1)[1] for p in header.split(",") if p.startswith("v1=")]
    except (KeyError, ValueError):
        return False
    if abs(time.time() - ts) > tolerance:  # protege contra replay antigo
        return False
    good = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(good, s) for s in v1)


# ---------------- Provedor Stripe (interface) ----------------
class FakeStripe:
    """Stripe simulado (sem chave). Não cobra nada; usado em dev/CI."""
    def create_price(self, product_name: str, amount_cents: int, currency: str, recurring: bool) -> str:
        return f"price_fake_{uuid.uuid4().hex[:12]}"

    def create_checkout(self, *, tenant_id: str, plan_version: PlanVersion, success_url: str, cancel_url: str,
                        customer_id: str | None) -> dict:
        sid = f"cs_fake_{uuid.uuid4().hex[:16]}"
        return {"id": sid, "url": f"{settings.public_web_url}/fake-checkout?session={sid}"}

    def create_topup_checkout(self, *, tenant_id: str, pack: TopupPack, success_url: str, cancel_url: str, customer_id: str | None) -> dict:
        sid = f"cs_fake_{uuid.uuid4().hex[:16]}"
        return {"id": sid, "url": f"{settings.public_web_url}/fake-checkout?session={sid}"}

    def billing_portal(self, customer_id: str, return_url: str) -> str:
        return f"{settings.public_web_url}/fake-portal"

    def refund(self, payment_ref: str) -> dict:
        return {"id": f"re_fake_{uuid.uuid4().hex[:10]}", "status": "succeeded"}


class RealStripe:
    """Stripe real via API REST (modo test primeiro). Requer STRIPE_SECRET_KEY."""
    base = "https://api.stripe.com/v1"

    def _post(self, path: str, data: dict) -> dict:
        r = httpx.post(f"{self.base}{path}", data=data, auth=(get_secret("stripe", "secret_key"), ""), timeout=20)
        r.raise_for_status()
        return r.json()

    def create_price(self, product_name: str, amount_cents: int, currency: str, recurring: bool) -> str:
        prod = self._post("/products", {"name": product_name})
        data = {"unit_amount": amount_cents, "currency": currency, "product": prod["id"]}
        if recurring:
            data["recurring[interval]"] = "month"
        return self._post("/prices", data)["id"]

    def create_checkout(self, *, tenant_id, plan_version, success_url, cancel_url, customer_id) -> dict:
        data = {
            "mode": "subscription" if plan_version.billing_type == BillingType.MONTHLY else "payment",
            "line_items[0][price]": plan_version.stripe_price_id, "line_items[0][quantity]": 1,
            "success_url": success_url, "cancel_url": cancel_url,
            # Metadados definidos pelo SERVIDOR a partir da membership (nunca do cliente).
            "metadata[tenant_id]": tenant_id, "metadata[plan_version_id]": str(plan_version.id),
        }
        if customer_id:
            data["customer"] = customer_id
        s = self._post("/checkout/sessions", data)
        return {"id": s["id"], "url": s["url"]}

    def create_topup_checkout(self, *, tenant_id, pack, success_url, cancel_url, customer_id) -> dict:
        data = {"mode": "payment", "line_items[0][price]": pack.stripe_price_id, "line_items[0][quantity]": 1,
                "success_url": success_url, "cancel_url": cancel_url,
                "metadata[tenant_id]": tenant_id, "metadata[topup_pack_id]": str(pack.id)}   # definidos pelo SERVIDOR
        if customer_id:
            data["customer"] = customer_id
        s = self._post("/checkout/sessions", data)
        return {"id": s["id"], "url": s["url"]}

    def billing_portal(self, customer_id: str, return_url: str) -> str:
        return self._post("/billing_portal/sessions", {"customer": customer_id, "return_url": return_url})["url"]

    def refund(self, payment_ref: str) -> dict:
        return self._post("/refunds", {"payment_intent": payment_ref})


def stripe_mode() -> str:
    """Modo efetivo (painel > .env). `live` só é aceito se salvo com confirmação explícita no painel."""
    return get_secret("stripe", "mode") or settings.stripe_mode or "fake"


DEV_WEBHOOK_SECRET = "whsec_dev_fake_secret"


def webhook_secret() -> str:
    """Segredo do webhook: painel (banco) > .env. Em PRODUÇÃO o valor padrão de desenvolvimento é IGNORADO (retorna ""),
    senão qualquer pessoa que conhecesse o padrão poderia forjar um pagamento. Vazio => o webhook é recusado."""
    v = get_secret("stripe", "webhook_secret") or settings.stripe_webhook_secret
    return "" if (settings.is_prod and (not v or v == DEV_WEBHOOK_SECRET)) else v


def get_stripe():
    mode = stripe_mode()
    if mode == "fake" or not get_secret("stripe", "secret_key"):
        return FakeStripe()
    return RealStripe()


# ---------------- Webhook ----------------
def process_webhook(db: Session, event: dict) -> str:
    """Processa um evento JÁ VERIFICADO. Idempotente. Retorna o resultado."""
    eid, etype = event.get("id", ""), event.get("type", "")
    if not eid:
        return "ignored_no_id"
    row = StripeWebhookEvent(stripe_event_id=eid, type=etype, payload={"type": etype})
    db.add(row)
    try:
        db.flush()  # a UNIQUE(stripe_event_id) garante dedupe mesmo com requisições paralelas
    except IntegrityError:
        db.rollback()
        return "duplicate"
    obj = event.get("data", {}).get("object", {})
    meta = obj.get("metadata", {}) or {}
    outcome = "ignored"
    if etype == "checkout.session.completed" and obj.get("payment_status") == "paid":
        outcome = _fulfill_checkout(db, obj, meta)
    elif etype == "invoice.paid":
        outcome = _renew_subscription(db, obj)
    elif etype in ("invoice.payment_failed",):
        sub = db.scalar(select(TenantSubscription).where(
            TenantSubscription.stripe_subscription_id == obj.get("subscription")))
        if sub:
            sub.status = "past_due"  # NÃO concede/renova; o acesso fica restrito
            _set_entitlements_active(db, sub.tenant_id, f"sub:{sub.id}", False)
        outcome = "payment_failed"
    elif etype == "customer.subscription.deleted":
        sub = db.scalar(select(TenantSubscription).where(
            TenantSubscription.stripe_subscription_id == obj.get("id")))
        if sub:
            sub.status = "canceled"
            _set_entitlements_active(db, sub.tenant_id, f"sub:{sub.id}", False)
        outcome = "subscription_canceled"
    elif etype == "charge.refunded":
        outcome = "refund_recorded"
    row.outcome = outcome
    db.commit()
    return outcome


def _ent_from_version(pv: PlanVersion) -> dict:
    e = pv.entitlements or {}
    g = grant_amounts(e)  # entende "ilimitado" (null) e horas de transmissão
    return {"limits": e, "events": g["events"], "minutes": g["language_minutes"], "event_minutes": g["event_minutes"]}


def apply_topup(db: Session, tenant_id, *, hours: int, events: int, ref: str) -> Entitlement:
    """Soma a RECARGA ao saldo da organização.
    - Há direito ativo (plano, teste, manual): soma horas/eventos NELE (se for ilimitado nesse item, não muda nada).
    - Não há nenhum: cria um direito novo "topup" só com o que foi comprado (mínimo 1 evento, senão não dá para iniciar).
    Idempotência: quem chama (webhook) já é deduplicado pelo id do evento Stripe; o ajuste manual é auditado."""
    now = datetime.now(timezone.utc)
    ents = [e for e in db.scalars(select(Entitlement).where(Entitlement.tenant_id == tenant_id, Entitlement.active.is_(True)))
            if not e.expires_at or e.expires_at.replace(tzinfo=timezone.utc) > now]
    if ents:
        ent = max(ents, key=lambda e: (e.expires_at is None, e.created_at))   # o mais duradouro/recente
        if hours and ent.event_minutes_remaining is not None:
            ent.event_minutes_remaining += hours * 60
        if events and not is_unlimited(ent.events_remaining):
            ent.events_remaining += events
        return ent
    limits = {"included_events": max(events, 1), "included_hours": hours, "max_concurrent_events": 1, "overage": "hard_stop"}
    ent = Entitlement(tenant_id=tenant_id, source="topup", source_ref=ref, limits=limits, events_remaining=max(events, 1),
                      language_minutes_remaining=UNLIM, event_minutes_remaining=hours * 60 if hours else None)
    db.add(ent)
    return ent


def _fulfill_topup(db: Session, obj: dict, meta: dict) -> str:
    try:
        tenant_id = uuid.UUID(meta["tenant_id"])
        pack = db.get(TopupPack, uuid.UUID(meta["topup_pack_id"]))
    except (KeyError, ValueError):
        return "bad_metadata"
    if not pack or not db.get(Tenant, tenant_id):
        return "unknown_target"
    apply_topup(db, tenant_id, hours=pack.hours, events=pack.events, ref=f"topup:{obj.get('id', '')}")
    audit(db, action="billing.topup_granted", tenant_id=tenant_id, target=str(pack.id), commit=False)
    return "topup_granted"


def _fulfill_checkout(db: Session, obj: dict, meta: dict) -> str:
    if "topup_pack_id" in meta:
        return _fulfill_topup(db, obj, meta)
    try:
        tenant_id = uuid.UUID(meta["tenant_id"])
        pv = db.get(PlanVersion, uuid.UUID(meta["plan_version_id"]))
    except (KeyError, ValueError):
        return "bad_metadata"
    if not pv or not db.get(Tenant, tenant_id):
        return "unknown_target"
    d = _ent_from_version(pv)
    sess_id = obj.get("id", "")
    if pv.billing_type == BillingType.ONE_OFF:
        purchase = db.scalar(select(OneOffPurchase).where(OneOffPurchase.stripe_session_id == sess_id))
        if not purchase:
            purchase = OneOffPurchase(tenant_id=tenant_id, plan_version_id=pv.id, stripe_session_id=sess_id)
            db.add(purchase)
        purchase.status, purchase.events_remaining = "paid", d["events"] or 1
        ref, source = f"oneoff:{sess_id}", "one_off"
    else:
        sub = TenantSubscription(tenant_id=tenant_id, plan_version_id=pv.id, status="active",
                                 stripe_subscription_id=obj.get("subscription"),
                                 current_period_end=datetime.now(timezone.utc) + timedelta(days=31))
        db.add(sub)
        db.flush()
        ref, source = f"sub:{sub.id}", "subscription"
    try:
        db.add(Entitlement(tenant_id=tenant_id, source=source, source_ref=ref, limits=d["limits"],
                           events_remaining=d["events"], language_minutes_remaining=d["minutes"],
                           event_minutes_remaining=d["event_minutes"]))
        db.flush()
    except IntegrityError:
        db.rollback()
        return "duplicate_grant"
    audit(db, action="billing.entitlement_granted", tenant_id=tenant_id, target=ref, commit=False)
    return "granted"


def _renew_subscription(db: Session, obj: dict) -> str:
    sub = db.scalar(select(TenantSubscription).where(
        TenantSubscription.stripe_subscription_id == obj.get("subscription")))
    if not sub:
        return "unknown_subscription"
    pv = db.get(PlanVersion, sub.plan_version_id)  # grandfathering: usa a versão contratada
    sub.status = "active"
    sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=31)
    d = _ent_from_version(pv)
    period = obj.get("id", uuid.uuid4().hex)
    db.add(Entitlement(tenant_id=sub.tenant_id, source="subscription", source_ref=f"sub:{sub.id}:{period}",
                       limits=d["limits"], events_remaining=d["events"], language_minutes_remaining=d["minutes"],
                       event_minutes_remaining=d["event_minutes"]))
    _set_entitlements_active(db, sub.tenant_id, f"sub:{sub.id}", True)
    return "renewed"


def _set_entitlements_active(db: Session, tenant_id, ref_prefix: str, active: bool) -> None:
    for e in db.scalars(select(Entitlement).where(Entitlement.tenant_id == tenant_id,
                                                  Entitlement.source_ref.like(f"{ref_prefix}%"))):
        e.active = active


# ---------------- Cotas ----------------
def credit_balance(db: Session, tenant_id) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(CreditLedger.delta_language_minutes), 0))
                         .where(CreditLedger.tenant_id == tenant_id)) or 0)


def active_entitlement(db: Session, tenant_id, *, lock: bool = False) -> Entitlement | None:
    """Melhor direito ativo (maior saldo de eventos). `lock` serializa inícios paralelos (Postgres)."""
    q = select(Entitlement).where(Entitlement.tenant_id == tenant_id, Entitlement.active.is_(True),
                                  Entitlement.events_remaining > 0)
    now = datetime.now(timezone.utc)
    ents = [e for e in db.scalars(q.with_for_update() if lock else q)
            if (not e.expires_at or e.expires_at.replace(tzinfo=timezone.utc) > now)
            and (e.event_minutes_remaining is None or e.event_minutes_remaining > 0)]  # sem horas = não serve para iniciar
    return max(ents, key=lambda e: e.events_remaining, default=None)


class QuotaError(Exception):
    """Violação de cota (mapeada para HTTP 402/409 pelas rotas)."""
    def __init__(self, code: str, msg: str):
        super().__init__(msg)
        self.code, self.msg = code, msg


def reserve_event_start(db: Session, tenant_id) -> Entitlement:
    """Consome 1 evento do direito, atomicamente. Impede início paralelo acima do limite
    (ex.: passe avulso não inicia 2 eventos simultâneos)."""
    tenant = db.execute(select(Tenant).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
    ent = active_entitlement(db, tenant.id, lock=True)
    if not ent:
        raise QuotaError("no_entitlement", "Sem plano ativo ou eventos disponíveis. Contrate um plano.")
    max_conc = plan_limit(ent.limits, "max_concurrent_events", 1)  # None = ilimitado
    live = db.scalar(select(func.count()).select_from(Event).where(
        Event.tenant_id == tenant.id, Event.status == EventStatus.LIVE)) or 0
    if max_conc is not None and live >= int(max_conc):
        raise QuotaError("concurrent_limit", f"Limite de {max_conc} evento(s) simultâneo(s) atingido.")
    if not is_unlimited(ent.events_remaining):
        ent.events_remaining -= 1
    return ent


def usage_minutes_used(db: Session, tenant_id) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
        UsageEvent.tenant_id == tenant_id, UsageEvent.kind == "language_minute")) or 0)


def record_usage(db: Session, *, tenant_id, event_id, session_id, language, provider, minutes: float,
                 cost_micros: int = 0, key: str | None = None) -> None:
    """Lança no livro-razão (append-only) e debita o saldo do direito. Idempotente via `key`."""
    if key and db.scalar(select(UsageEvent).where(UsageEvent.idempotency_key == key)):
        return
    db.add(UsageEvent(tenant_id=tenant_id, event_id=event_id, session_id=session_id, language=language,
                      provider=provider, quantity=minutes, provider_cost_micros=cost_micros, idempotency_key=key))
    ent = db.scalar(select(Entitlement).where(Entitlement.tenant_id == tenant_id, Entitlement.active.is_(True))
                    .order_by(Entitlement.created_at.desc()))
    if ent and not is_unlimited(ent.language_minutes_remaining):
        ent.language_minutes_remaining = max(0, ent.language_minutes_remaining - int(round(minutes)))
    db.commit()


def minutes_remaining(db: Session, tenant_id) -> int:
    total = db.scalar(select(func.coalesce(func.sum(Entitlement.language_minutes_remaining), 0)).where(
        Entitlement.tenant_id == tenant_id, Entitlement.active.is_(True))) or 0
    return int(total) + credit_balance(db, tenant_id)
