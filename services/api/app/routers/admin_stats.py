"""Super Admin — painel de gestão: visão geral, controle de acessos, custos de IA e receita.

HONESTIDADE DOS NÚMEROS (regra do projeto):
 - ACESSOS: "online agora" = usuário que fez login ou renovou a sessão nos últimos 15 min (o access token dura 15 min).
   É uma aproximação; não há "heartbeat" por usuário.
 - CUSTO DE IA: minutos-idioma medidos × TARIFA do provedor. A tarifa é configurada pelo Super Admin
   (Financeiro -> Tarifas). Sem tarifa configurada o valor é uma ESTIMATIVA de placeholder e a tela avisa.
   Quando houver fatura real do provedor, ela prevalece.
 - RECEITA: vendas confirmadas por webhook assinado (compras avulsas pagas + assinaturas ativas). É receita
   ESTIMADA do sistema, não conciliação contábil com o Stripe.
Todas as rotas exigem Super Admin + MFA (require_super).
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..core.ratelimit import client_ip
from ..core.timeutil import iso
from ..db import get_db
from ..deps import require_super
from ..models import (AuditLog, BillingType, Event, EventStatus, FailoverEvent, Membership, OneOffPurchase,
                      Plan, PlanVersion, ProviderConfig, RefreshToken, Tenant, TenantSubscription, UsageEvent, User)
from ..services.channels import manager, registry

router = APIRouter(prefix="/admin", tags=["admin-stats"], dependencies=[Depends(require_super)])

ONLINE_WINDOW = timedelta(minutes=15)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(d: datetime | None) -> datetime | None:
    """SQLite devolve datas sem fuso; trata como UTC."""
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


def _days(n: int) -> list[str]:
    today = _now().date()
    return [(today - timedelta(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _rates(db: Session) -> dict[str, float | None]:
    """Tarifa (USD por minuto-idioma) configurada por provedor; None = ainda não configurada."""
    out: dict[str, float | None] = {n: None for n in registry}
    for pc in db.scalars(select(ProviderConfig)).all():
        r = (pc.capabilities or {}).get("rate_usd_per_min")
        if pc.name in out and r is not None:
            out[pc.name] = float(r)
    return out


def _sale_cents(pv: PlanVersion | None) -> int:
    return int(pv.amount_cents) if pv else 0


def _revenue_rows(db: Session, since: datetime) -> list[tuple[datetime, int, str]]:
    """(data, centavos, plano) de cada venda confirmada na janela."""
    rows: list[tuple[datetime, int, str]] = []
    for o in db.scalars(select(OneOffPurchase).where(OneOffPurchase.status == "paid", OneOffPurchase.created_at >= since)).all():
        pv = db.get(PlanVersion, o.plan_version_id)
        rows.append((_aware(o.created_at), _sale_cents(pv), pv.plan.public_name if pv else "—"))
    for s in db.scalars(select(TenantSubscription).where(TenantSubscription.status == "active", TenantSubscription.created_at >= since)).all():
        pv = db.get(PlanVersion, s.plan_version_id)
        rows.append((_aware(s.created_at), _sale_cents(pv), pv.plan.public_name if pv else "—"))
    return rows


def _mrr_cents(db: Session) -> int:
    total = 0
    for s in db.scalars(select(TenantSubscription).where(TenantSubscription.status == "active")).all():
        pv = db.get(PlanVersion, s.plan_version_id)
        if pv and pv.billing_type == BillingType.MONTHLY:
            total += pv.amount_cents
    return total


# ---------------------------------------------------------------- visão geral
@router.get("/overview")
def overview(days: int = Query(30, ge=7, le=180), db: Session = Depends(get_db)):
    now = _now()
    since = now - timedelta(days=days)
    labels = _days(days)
    minutes_d: dict[str, float] = defaultdict(float)
    cost_d: dict[str, float] = defaultdict(float)
    by_prov: dict[str, dict] = defaultdict(lambda: {"minutes": 0.0, "cost": 0.0})
    by_tenant: dict[str, dict] = defaultdict(lambda: {"minutes": 0.0, "cost": 0.0})
    by_lang: dict[str, float] = defaultdict(float)
    for u in db.execute(select(UsageEvent).where(UsageEvent.created_at >= since, UsageEvent.kind == "language_minute")).scalars():
        d = _aware(u.created_at).date().isoformat()
        q, c = float(u.quantity), u.provider_cost_micros / 1_000_000
        minutes_d[d] += q; cost_d[d] += c
        by_prov[u.provider or "—"]["minutes"] += q; by_prov[u.provider or "—"]["cost"] += c
        by_tenant[str(u.tenant_id)]["minutes"] += q; by_tenant[str(u.tenant_id)]["cost"] += c
        by_lang[u.language] += q
    rev_d: dict[str, float] = defaultdict(float)
    rev_total = 0.0
    for at, cents, _plan in _revenue_rows(db, since):
        rev_d[at.date().isoformat()] += cents / 100
        rev_total += cents / 100
    cost_total = sum(cost_d.values())

    names = {str(t.id): t.name for t in db.scalars(select(Tenant)).all()}
    top = sorted(by_tenant.items(), key=lambda kv: kv[1]["minutes"], reverse=True)[:6]

    t_total = db.scalar(select(func.count()).select_from(Tenant)) or 0
    t_susp = db.scalar(select(func.count()).select_from(Tenant).where(Tenant.status != "active")) or 0
    live_events = db.scalar(select(func.count()).select_from(Event).where(Event.status == EventStatus.LIVE)) or 0
    listeners_now = sum(c.listeners for c in manager.channels.values())
    online = db.scalar(select(func.count(func.distinct(RefreshToken.user_id))).where(
        RefreshToken.created_at >= now - ONLINE_WINDOW, RefreshToken.revoked.is_(False))) or 0
    rates = _rates(db)
    return {
        "days": days,
        "kpis": {
            "tenants": t_total, "tenants_suspended": t_susp,
            "users": db.scalar(select(func.count()).select_from(User)) or 0,
            "events_total": db.scalar(select(func.count()).select_from(Event)) or 0,
            "live_events": live_events, "listeners_now": listeners_now, "online_users": online,
            "language_minutes": round(sum(minutes_d.values()), 1),
            "ai_cost_usd": round(cost_total, 4), "revenue_usd": round(rev_total, 2),
            "mrr_usd": round(_mrr_cents(db) / 100, 2), "margin_usd": round(rev_total - cost_total, 2),
            "failovers": db.scalar(select(func.count()).select_from(FailoverEvent).where(FailoverEvent.created_at >= since)) or 0,
        },
        "series": {"labels": labels, "minutes": [round(minutes_d[d], 2) for d in labels],
                   "cost_usd": [round(cost_d[d], 4) for d in labels], "revenue_usd": [round(rev_d[d], 2) for d in labels]},
        "cost_by_provider": [{"provider": k, "minutes": round(v["minutes"], 1), "cost_usd": round(v["cost"], 4)} for k, v in by_prov.items()],
        "top_tenants": [{"name": names.get(k, "—"), "minutes": round(v["minutes"], 1), "cost_usd": round(v["cost"], 4)} for k, v in top],
        "top_languages": sorted(({"language": k, "minutes": round(v, 1)} for k, v in by_lang.items()), key=lambda x: -x["minutes"])[:8],
        "cost_is_estimate": any(r is None for n, r in rates.items() if n != "mock"),  # algum provedor real sem tarifa configurada
    }


# ---------------------------------------------------------------- acessos
@router.get("/access")
def access(db: Session = Depends(get_db)):
    now = _now()
    # sessões válidas = refresh token vigente (não usado/revogado/expirado)
    valid = db.scalars(select(RefreshToken).where(RefreshToken.revoked.is_(False), RefreshToken.used_at.is_(None),
                                                   RefreshToken.expires_at > now)).all()
    last_seen: dict = {}
    for tkn in db.scalars(select(RefreshToken).where(RefreshToken.created_at >= now - timedelta(days=1)).order_by(RefreshToken.created_at)).all():
        last_seen[tkn.user_id] = _aware(tkn.created_at)
    sessions_by_user: dict = defaultdict(int)
    for tkn in valid:
        sessions_by_user[tkn.user_id] += 1
    # último IP de login de cada usuário (da auditoria)
    last_ip: dict = {}
    for a in db.scalars(select(AuditLog).where(AuditLog.action == "auth.login").order_by(AuditLog.created_at)).all():
        if a.actor_id:
            last_ip[a.actor_id] = a.ip
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(list(sessions_by_user) or [None]))).all()}
    mem = {}
    for m, t in db.execute(select(Membership, Tenant).join(Tenant, Tenant.id == Membership.tenant_id)).all():
        mem.setdefault(m.user_id, (t.name, m.role.value))
    online = []
    for uid, n in sessions_by_user.items():
        u = users.get(uid)
        if not u:
            continue
        seen = last_seen.get(uid)
        online.append({"user_id": str(uid), "email": u.email, "name": u.name, "super": u.is_super_admin,
                       "org": mem.get(uid, ("—", ""))[0], "role": "SUPER_ADMIN" if u.is_super_admin else mem.get(uid, ("", ""))[1],
                       "sessions": n, "last_seen": iso(seen) if seen else None, "ip": last_ip.get(uid, ""),
                       "active_now": bool(seen and seen >= now - ONLINE_WINDOW)})
    online.sort(key=lambda x: x["last_seen"] or "", reverse=True)

    week = now - timedelta(days=7)
    counts = dict(db.execute(select(AuditLog.action, func.count()).where(
        AuditLog.created_at >= week, AuditLog.action.in_(["auth.login", "auth.lockout", "auth.refresh_reuse", "auth.password_reset", "auth.register"]))
        .group_by(AuditLog.action)).all())
    emails = {u.id: u.email for u in db.scalars(select(User)).all()}
    recent = db.scalars(select(AuditLog).where(AuditLog.action.like("auth.%")).order_by(AuditLog.created_at.desc()).limit(40)).all()
    locked = db.scalars(select(User).where(User.locked_until.is_not(None))).all()
    return {
        "online_now": sum(1 for o in online if o["active_now"]), "active_sessions": len(valid),
        "events_week": {k: int(v) for k, v in counts.items()},
        "locked": [{"email": u.email, "until": iso(u.locked_until)} for u in locked if _aware(u.locked_until) > now],
        "sessions": online,
        "recent": [{"at": iso(a.created_at), "action": a.action, "email": emails.get(a.actor_id, "—"), "ip": a.ip, "reason": a.reason} for a in recent],
    }


class RevokeIn(BaseModel):
    reason: str = Field(min_length=10, max_length=300)


@router.post("/users/{user_id}/revoke-sessions")
def revoke_sessions(user_id: UUID, body: RevokeIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Derruba TODAS as sessões do usuário (o access token atual expira em até 15 min). Motivo obrigatório + auditoria."""
    if not db.get(User, user_id):
        raise HTTPException(404)
    n = 0
    for tkn in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked.is_(False))).all():
        tkn.revoked = True
        n += 1
    db.commit()
    audit(db, action="admin.revoke_sessions", actor_id=su.id, actor_role="SUPER_ADMIN", target=str(user_id),
          reason=body.reason, ip=client_ip(request), meta={"revoked": n})
    return {"revoked": n}


# ---------------------------------------------------------------- financeiro
@router.get("/finance")
def finance(days: int = Query(30, ge=7, le=180), db: Session = Depends(get_db)):
    now = _now()
    since = now - timedelta(days=days)
    rates = _rates(db)
    prov: dict[str, dict] = defaultdict(lambda: {"minutes": 0.0, "cost": 0.0})
    for u in db.scalars(select(UsageEvent).where(UsageEvent.created_at >= since, UsageEvent.kind == "language_minute")).all():
        prov[u.provider or "—"]["minutes"] += float(u.quantity)
        prov[u.provider or "—"]["cost"] += u.provider_cost_micros / 1_000_000
    by_plan: dict[str, dict] = defaultdict(lambda: {"sales": 0, "revenue": 0.0})
    for _at, cents, plan in _revenue_rows(db, since):
        by_plan[plan]["sales"] += 1
        by_plan[plan]["revenue"] += cents / 100
    subs = defaultdict(lambda: {"active": 0, "mrr": 0.0})
    for s in db.scalars(select(TenantSubscription).where(TenantSubscription.status == "active")).all():
        pv = db.get(PlanVersion, s.plan_version_id)
        if pv:
            subs[pv.plan.public_name]["active"] += 1
            subs[pv.plan.public_name]["mrr"] += pv.amount_cents / 100
    revenue = sum(v["revenue"] for v in by_plan.values())
    cost = sum(v["cost"] for v in prov.values())
    return {
        "days": days, "revenue_usd": round(revenue, 2), "ai_cost_usd": round(cost, 4),
        "margin_usd": round(revenue - cost, 2), "margin_pct": round((revenue - cost) / revenue * 100, 1) if revenue else None,
        "mrr_usd": round(_mrr_cents(db) / 100, 2),
        "providers": [{"provider": k, "minutes": round(v["minutes"], 1), "cost_usd": round(v["cost"], 4),
                       "cost_per_min": round(v["cost"] / v["minutes"], 4) if v["minutes"] else None} for k, v in prov.items()],
        "rates": [{"provider": n, "usd_per_min": r, "configured": r is not None, "is_mock": n == "mock"} for n, r in rates.items()],
        "plans": [{"plan": k, "sales": v["sales"], "revenue_usd": round(v["revenue"], 2),
                   "active_subs": subs[k]["active"], "mrr_usd": round(subs[k]["mrr"], 2)}
                  for k, v in {**{p: {"sales": 0, "revenue": 0.0} for p in subs}, **by_plan}.items()],
    }


class RateIn(BaseModel):
    usd_per_min: float | None = Field(default=None, ge=0, le=100)  # None = remover tarifa


@router.put("/providers/{name}/rate")
def set_rate(name: str, body: RateIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Define a tarifa (USD por minuto-idioma) usada para calcular o custo dos NOVOS minutos medidos."""
    if name not in registry:
        raise HTTPException(404, "Provedor desconhecido.")
    pc = db.scalar(select(ProviderConfig).where(ProviderConfig.name == name))
    if not pc:
        pc = ProviderConfig(name=name, enabled=False, capabilities={})
        db.add(pc)
    caps = dict(pc.capabilities or {})
    if body.usd_per_min is None:
        caps.pop("rate_usd_per_min", None)
    else:
        caps["rate_usd_per_min"] = body.usd_per_min
    pc.capabilities = caps  # reatribui o dict para o SQLAlchemy detectar a mudança
    db.commit()
    audit(db, action="admin.provider_rate", actor_id=su.id, actor_role="SUPER_ADMIN", target=name, ip=client_ip(request),
          meta={"usd_per_min": body.usd_per_min})
    return {"ok": True}


# ---------------------------------------------------------------- contas aguardando confirmação de e-mail
@router.get("/users/pending")
def pending_users(db: Session = Depends(get_db)):
    """Contas criadas que ainda NÃO confirmaram o e-mail (não conseguem entrar)."""
    from ..services.email import email_configured
    rows = db.scalars(select(User).where(User.email_verified_at.is_(None)).order_by(User.created_at.desc()).limit(200)).all()
    orgs = {m.user_id: t.name for m, t in db.execute(select(Membership, Tenant).join(Tenant, Tenant.id == Membership.tenant_id)).all()}
    return {"email_configured": email_configured(),
            "users": [{"user_id": str(u.id), "email": u.email, "name": u.name, "org": orgs.get(u.id, "—"), "created_at": iso(u.created_at)} for u in rows]}


@router.post("/users/{user_id}/verify")
def verify_user(user_id: UUID, body: RevokeIn, request: Request, su: User = Depends(require_super), db: Session = Depends(get_db)):
    """Ativa a conta MANUALMENTE (ex.: o e-mail ainda não está configurado ou não chegou). Motivo obrigatório + auditoria."""
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404)
    u.email_verified_at = u.email_verified_at or datetime.now(timezone.utc)
    db.commit()
    audit(db, action="admin.verify_user", actor_id=su.id, actor_role="SUPER_ADMIN", target=str(u.id), reason=body.reason, ip=client_ip(request))
    return {"ok": True}
