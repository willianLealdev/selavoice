"""Console do SUPER ADMIN (/admin/*).

- Todas as rotas exigem super admin + MFA verificado na sessão.
- NÃO há bypass automático dos limites de tenant: para ver dados de um cliente é preciso uma
  ELEVAÇÃO explícita (motivo obrigatório, auditada, 10 min, SOMENTE LEITURA).
- Planos: versões são IMUTÁVEIS. Mudar preço/limites cria nova versão e novo preço no Stripe;
  assinantes existentes continuam na versão contratada (grandfathering) até migração deliberada.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..core.ratelimit import client_ip
from ..core.timeutil import iso
from ..db import get_db
from ..deps import require_super
from ..models import (AuditLog, BillingType, CreditLedger, Event, FailoverEvent, Membership, Plan, PlanVersion, Tenant,
                      TenantSubscription, UsageEvent, User)
from ..providers.base import ProviderHealth
from ..security import create_access_token
from ..services.billing import get_stripe
from ..services.plan_schema import PlanError, normalize
from ..services.channels import registry, router as failover_router

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenants")
def tenants(_: User = Depends(require_super), db: Session = Depends(get_db)):
    rows = db.scalars(select(Tenant).order_by(Tenant.created_at.desc())).all()
    users = dict(db.execute(select(Membership.tenant_id, func.count()).group_by(Membership.tenant_id)).all())
    events = dict(db.execute(select(Event.tenant_id, func.count()).group_by(Event.tenant_id)).all())
    minutes = dict(db.execute(select(UsageEvent.tenant_id, func.coalesce(func.sum(UsageEvent.quantity), 0)).group_by(UsageEvent.tenant_id)).all())
    plan_of: dict = {}
    for sub in db.scalars(select(TenantSubscription).where(TenantSubscription.status == "active")).all():
        pv = db.get(PlanVersion, sub.plan_version_id)
        plan_of[sub.tenant_id] = pv.plan.public_name if pv else ""
    return [{"id": str(t.id), "name": t.name, "slug": t.slug, "type": t.type, "status": t.status,
             "created_at": iso(t.created_at), "users": users.get(t.id, 0), "events": events.get(t.id, 0),
             "language_minutes": round(float(minutes.get(t.id, 0)), 1), "plan": plan_of.get(t.id, "")} for t in rows]


class ReasonIn(BaseModel):
    reason: str = Field(min_length=10, max_length=300)


@router.post("/tenants/{tenant_id}/suspend")
def suspend(tenant_id: UUID, body: ReasonIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404)
    t.status = "suspended"
    db.commit()
    audit(db, action="admin.tenant_suspend", actor_id=su.id, actor_role="SUPER_ADMIN", tenant_id=t.id,
          reason=body.reason, ip=client_ip(request))
    return {"status": t.status}


@router.post("/tenants/{tenant_id}/activate")
def activate(tenant_id: UUID, body: ReasonIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    t = db.get(Tenant, tenant_id)
    if not t:
        raise HTTPException(404)
    t.status = "active"
    db.commit()
    audit(db, action="admin.tenant_activate", actor_id=su.id, actor_role="SUPER_ADMIN", tenant_id=t.id,
          reason=body.reason, ip=client_ip(request))
    return {"status": t.status}


class ElevateIn(ReasonIn):
    tenant_id: UUID


@router.post("/elevate")
def elevate(body: ElevateIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Suporte: token de 10 min, somente leitura, restrito a UM tenant, com auditoria."""
    if not db.get(Tenant, body.tenant_id):
        raise HTTPException(404)
    audit(db, action="admin.elevate", actor_id=su.id, actor_role="SUPER_ADMIN", tenant_id=body.tenant_id,
          reason=body.reason, ip=client_ip(request))
    token = create_access_token(str(su.id), mfa=True, extra={"elev": str(body.tenant_id)}, minutes=10)
    return {"access_token": token, "expires_minutes": 10, "mode": "read_only"}


# ---------------- Planos ----------------
class PlanIn(BaseModel):
    public_name: str = Field(max_length=120)
    slug: str = Field(pattern="^[a-z0-9-]{2,60}$")
    description: str = ""


class VersionIn(BaseModel):
    billing_type: BillingType
    currency: str = Field(default="usd", pattern="^[a-z]{3}$")
    amount_cents: int = Field(ge=0, le=100_000_000)
    entitlements: dict = Field(default_factory=dict)


@router.get("/plans")
def list_plans(_: User = Depends(require_super), db: Session = Depends(get_db)):
    return [{"id": str(p.id), "name": p.public_name, "slug": p.slug, "status": p.status, "description": p.description,
             "versions": [{"id": str(v.id), "version": v.version, "amount_cents": v.amount_cents,
                           "billing_type": v.billing_type.value, "stripe_price_id": v.stripe_price_id, "currency": v.currency,
                           "entitlements": v.entitlements} for v in p.versions]}
            for p in db.scalars(select(Plan).order_by(Plan.created_at))]


@router.post("/plans", status_code=201)
def create_plan(body: PlanIn, su: User = Depends(require_super), db: Session = Depends(get_db)):
    if db.scalar(select(Plan).where(Plan.slug == body.slug)):
        raise HTTPException(409, "Slug já existe.")
    p = Plan(public_name=body.public_name, slug=body.slug, description=body.description)
    db.add(p)
    db.commit()
    audit(db, action="admin.plan_create", actor_id=su.id, actor_role="SUPER_ADMIN", target=str(p.id))
    return {"id": str(p.id)}


@router.patch("/plans/{plan_id}")
def update_plan(plan_id: UUID, status: str | None = None, public_name: str | None = None, description: str | None = None,
                su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Só metadados/estado. Preço e limites NÃO mudam aqui (use uma nova versão)."""
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404)
    if status:
        if status not in ("draft", "published", "archived"):
            raise HTTPException(422, "Status inválido.")
        p.status = status
    if public_name:
        p.public_name = public_name
    if description is not None:
        p.description = description
    db.commit()
    audit(db, action="admin.plan_update", actor_id=su.id, actor_role="SUPER_ADMIN", target=str(p.id))
    return {"ok": True}


@router.post("/plans/{plan_id}/versions", status_code=201)
def new_version(plan_id: UUID, body: VersionIn, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Cria NOVA versão imutável + novo preço no Stripe. Histórico de preços é preservado."""
    p = db.get(Plan, plan_id)
    if not p:
        raise HTTPException(404)
    try:
        ent = normalize(body.entitlements)
    except PlanError as e:
        raise HTTPException(422, str(e))
    n = (p.versions[-1].version + 1) if p.versions else 1
    price_id = get_stripe().create_price(f"{p.public_name} v{n}", body.amount_cents, body.currency,
                                         body.billing_type == BillingType.MONTHLY)
    v = PlanVersion(plan_id=p.id, version=n, stripe_price_id=price_id, billing_type=body.billing_type,
                    currency=body.currency, amount_cents=body.amount_cents, entitlements=ent)
    db.add(v)
    db.commit()
    audit(db, action="admin.plan_version_create", actor_id=su.id, actor_role="SUPER_ADMIN", target=f"{p.id}:v{n}")
    return {"id": str(v.id), "version": n, "stripe_price_id": price_id}


class MigrateIn(BaseModel):
    to_version_id: UUID
    tenant_ids: list[UUID]
    reason: str = Field(min_length=10)


@router.post("/plans/{plan_id}/migrate")
def migrate(plan_id: UUID, body: MigrateIn, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Migração DELIBERADA de assinantes para outra versão (grandfathering é o padrão)."""
    target = db.get(PlanVersion, body.to_version_id)
    if not target or target.plan_id != plan_id:
        raise HTTPException(404)
    n = 0
    for sub in db.scalars(select(TenantSubscription).where(TenantSubscription.tenant_id.in_(body.tenant_ids),
                                                            TenantSubscription.status == "active")):
        sub.plan_version_id = target.id
        n += 1
    db.commit()
    audit(db, action="admin.plan_migrate", actor_id=su.id, actor_role="SUPER_ADMIN", target=str(target.id),
          reason=body.reason, meta={"tenants": [str(t) for t in body.tenant_ids], "migrated": n})
    return {"migrated": n}


class CreditIn(ReasonIn):
    language_minutes: int = Field(ge=-100_000, le=100_000)


@router.post("/tenants/{tenant_id}/credits")
def add_credits(tenant_id: UUID, body: CreditIn, su: User = Depends(require_super), db: Session = Depends(get_db)):
    if not db.get(Tenant, tenant_id):
        raise HTTPException(404)
    db.add(CreditLedger(tenant_id=tenant_id, delta_language_minutes=body.language_minutes, reason=body.reason, actor_id=su.id))
    db.commit()
    audit(db, action="admin.credit", actor_id=su.id, actor_role="SUPER_ADMIN", tenant_id=tenant_id, reason=body.reason,
          meta={"delta": body.language_minutes})
    return {"ok": True}


# ---------------- Provedores / métricas / auditoria ----------------
@router.get("/providers")
async def providers(_: User = Depends(require_super)):
    out = []
    for name, p in registry.items():
        h: ProviderHealth = await p.health()
        out.append({"name": name, "healthy": h.ok, "detail": h.detail,
                    "configured": p.configured(), "streaming_implemented": p.streaming_implemented,
                    "languages": [{"language": c.language, "text": c.text_output, "speech": c.speech_output,
                                   "verified": c.verified, "discovered": c.discovered} for c in p.list_languages()]})
    return out


class OverrideIn(BaseModel):
    session_id: UUID
    language: str
    provider: str


@router.post("/providers/override")
def override(body: OverrideIn, su: User = Depends(require_super), db: Session = Depends(get_db)):
    if body.provider not in registry:
        raise HTTPException(422, "Provedor desconhecido.")
    failover_router.admin_override[(str(body.session_id), body.language)] = body.provider
    audit(db, action="admin.provider_override", actor_id=su.id, actor_role="SUPER_ADMIN",
          target=f"{body.session_id}:{body.language}->{body.provider}")
    return {"ok": True}


@router.get("/metrics")
def metrics(_: User = Depends(require_super), db: Session = Depends(get_db)):
    q = lambda m: db.scalar(select(func.count()).select_from(m)) or 0
    minutes = db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0))) or 0
    cost = db.scalar(select(func.coalesce(func.sum(UsageEvent.provider_cost_micros), 0))) or 0
    return {"tenants": q(Tenant), "events": q(Event), "language_minutes": float(minutes),
            "provider_cost_usd": cost / 1_000_000, "failovers": q(FailoverEvent)}


@router.get("/audit")
def audit_view(limit: int = 100, _: User = Depends(require_super), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [{"at": iso(r.created_at), "action": r.action, "actor": str(r.actor_id), "tenant": str(r.tenant_id),
             "reason": r.reason, "target": r.target} for r in rows]


# ---------------- Integrações (chaves de API editáveis no painel) ----------------
import httpx as _httpx
from ..services import secrets_store as _sec

_CONFIRM_LIVE = "CONFIRMO COBRANCA REAL"


class IntegrationIn(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)   # campo -> novo valor (vazio = manter o atual)
    clear: list[str] = Field(default_factory=list)          # campos a apagar
    enabled: bool | None = None
    confirm_live: str | None = None                          # exigido ao colocar o Stripe em modo live


@router.get("/integrations")
def integrations(_: User = Depends(require_super)):
    """Estado de cada integração. NUNCA devolve os valores das chaves (só 'configurada' + 4 últimos caracteres)."""
    return [_sec.describe(n) for n in _sec.CATALOG]


@router.put("/integrations/{name}")
def save_integration(name: str, body: IntegrationIn, request: Request, su: User = Depends(require_super),
                     db: Session = Depends(get_db)):
    if name not in _sec.CATALOG:
        raise HTTPException(404, "Integração desconhecida.")
    try:
        values = _sec.validate_values(name, body.values)
    except ValueError as e:
        raise HTTPException(422, str(e))
    if name == "stripe":
        # Trava anti-cobrança acidental: live exige chave sk_live_ E confirmação digitada;
        # e uma chave sk_live_ só é aceita junto do modo live.
        new_mode = values.get("mode") or _sec.get_secret("stripe", "mode")
        new_key = values.get("secret_key") or _sec.get_secret("stripe", "secret_key")
        if values.get("mode") == "live" and body.confirm_live != _CONFIRM_LIVE:
            raise HTTPException(422, f"Para ativar cobrança REAL digite exatamente: {_CONFIRM_LIVE}")
        if values.get("mode") == "live" and not new_key.startswith(("sk_live_", "rk_live_")):
            raise HTTPException(422, "Modo live exige uma chave sk_live_.")
        if values.get("secret_key", "").startswith(("sk_live_", "rk_live_")) and new_mode != "live":
            raise HTTPException(422, "Chave sk_live_ só é aceita junto do modo live (com confirmação).")
    if any(c not in _sec.CATALOG[name]["fields"] for c in body.clear):
        raise HTTPException(422, "Campo desconhecido.")
    changed = _sec.save(name, values, body.clear, body.enabled)
    # Auditoria: registra O QUE mudou, jamais os valores.
    audit(db, action="admin.integration_update", actor_id=su.id, actor_role="SUPER_ADMIN", target=name,
          ip=client_ip(request), meta={"changed": changed})
    return _sec.describe(name)


def _http_check(url: str, **kw) -> tuple[bool, str]:
    """GET de verificação. Nunca inclui a chave na mensagem devolvida."""
    try:
        r = _httpx.get(url, timeout=10, **kw)
    except _httpx.HTTPError:
        return False, "Não foi possível conectar ao serviço (rede/DNS/tempo esgotado)."
    if r.status_code in (200, 204):
        return True, "Conexão OK: a chave foi aceita."
    # O Google responde HTTP 400 (API_KEY_INVALID) para chave inválida, em vez de 401.
    if r.status_code in (401, 403) or (r.status_code == 400 and ("API_KEY_INVALID" in r.text or "API key not valid" in r.text)):
        return False, "A chave foi RECUSADA pelo serviço (inválida, sem permissão ou expirada)."
    return False, f"O serviço respondeu HTTP {r.status_code}."


@router.post("/integrations/{name}/test")
def test_integration(name: str, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Testa se a chave salva é ACEITA. Só valida autenticação — NÃO prova tradução em tempo real."""
    if name not in _sec.CATALOG:
        raise HTTPException(404, "Integração desconhecida.")
    g = _sec.get_secret
    if name == "gemini" and g("gemini", "api_key"):
        ok, msg = _http_check("https://generativelanguage.googleapis.com/v1beta/models",
                              headers={"x-goog-api-key": g("gemini", "api_key")})
    elif name == "azure" and g("azure", "key") and g("azure", "region"):
        ok, msg = _http_check(f"https://{g('azure', 'region')}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                              headers={"Ocp-Apim-Subscription-Key": g("azure", "key")})
    elif name == "deepgram" and g("deepgram", "api_key"):
        ok, msg = _http_check("https://api.deepgram.com/v1/projects",
                              headers={"Authorization": f"Token {g('deepgram', 'api_key')}"})
    elif name == "deepseek" and g("deepseek", "api_key"):
        ok, msg = _http_check("https://api.deepseek.com/models",
                              headers={"Authorization": f"Bearer {g('deepseek', 'api_key')}"})
    elif name == "resend" and g("resend", "api_key"):
        # Chave "somente envio" recebe 401 com name=restricted_api_key neste endpoint: é uma chave VÁLIDA.
        try:
            r = _httpx.get("https://api.resend.com/domains", timeout=10,
                           headers={"Authorization": f"Bearer {g('resend', 'api_key')}"})
            restricted = r.status_code == 401 and "restricted_api_key" in r.text
            ok = r.status_code == 200 or restricted
            msg = ("Conexão OK (chave somente de envio)." if restricted else "Conexão OK: a chave foi aceita.") if ok                 else ("A chave foi RECUSADA pelo serviço." if r.status_code in (401, 403) else f"O serviço respondeu HTTP {r.status_code}.")
        except _httpx.HTTPError:
            ok, msg = False, "Não foi possível conectar ao serviço."
        if ok and not g("resend", "from_email"):
            ok, msg = False, "Chave aceita, mas falta o e-mail remetente (domínio verificado no Resend)."
    elif name == "stripe" and g("stripe", "secret_key"):
        ok, msg = _http_check("https://api.stripe.com/v1/balance", auth=(g("stripe", "secret_key"), ""))
    else:
        ok, msg = False, "Preencha e salve as chaves antes de testar."
    audit(db, action="admin.integration_test", actor_id=su.id, actor_role="SUPER_ADMIN", target=name,
          ip=client_ip(request), meta={"ok": ok})
    return {"ok": ok, "detail": msg}


# ---------------- Teste grátis (configurável pelo dono) ----------------
from ..services.platform_settings import get_trial as _get_trial, set_trial as _set_trial


class TrialIn(BaseModel):
    enabled: bool
    days: int | None = Field(default=None, ge=1, le=3650)   # None = o teste não expira
    limits: dict = Field(default_factory=dict)


@router.get("/trial")
def trial_get(_: User = Depends(require_super), db: Session = Depends(get_db)):
    return _get_trial(db)


@router.put("/trial")
def trial_put(body: TrialIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Define o teste grátis das PRÓXIMAS contas (quem já tem teste não muda). Validação igual à de um plano."""
    try:
        cfg = _set_trial(db, enabled=body.enabled, days=body.days, limits=body.limits)
    except PlanError as e:
        raise HTTPException(422, str(e))
    audit(db, action="admin.trial_update", actor_id=su.id, actor_role="SUPER_ADMIN", ip=client_ip(request),
          meta={"enabled": cfg["enabled"], "days": cfg["days"]})
    return cfg
