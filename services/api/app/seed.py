"""Dados iniciais: super admin, planos padrão e organização piloto UFC Church.

Rodar:  python -m app.seed
A senha do super admin vem de SUPER_ADMIN_PASSWORD; se vazia, é gerada ALEATÓRIA e impressa UMA vez.
Em produção NÃO cria tenants de demonstração (só super admin + planos).
"""
import secrets
from datetime import datetime, timezone

from sqlalchemy import select

from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import (BillingType, Membership, Plan, PlanVersion, Role, Tenant, User)
from .security import hash_password
from .services.billing import grant_trial

settings = get_settings()

PLANS = [
    ("avulso-evento", "Evento Avulso", BillingType.ONE_OFF, 14900,
     {"included_events": 1, "max_event_minutes": 180, "included_language_minutes": 600, "max_languages": 3,
      "listener_concurrency": 300, "max_concurrent_events": 1, "recordings": True, "pdf_booklets": True, "overage": "hard_stop"}),
    ("plano-mensal", "Plano Mensal", BillingType.MONTHLY, 29900,
     {"included_events": 8, "max_event_minutes": 180, "included_language_minutes": 2400, "max_languages": 5,
      "listener_concurrency": 500, "max_concurrent_events": 1, "recordings": True, "pdf_booklets": True,
      "admin_seats": 5, "overage": "topup"}),
    ("eventos-pro", "Eventos Pro", BillingType.MONTHLY, 89900,
     {"included_events": 30, "max_event_minutes": 600, "included_language_minutes": 12000, "max_languages": 10,
      "listener_concurrency": 3000, "max_concurrent_events": 3, "recordings": True, "pdf_booklets": True,
      "admin_seats": 15, "overage": "topup"}),
]


def run() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.email == settings.super_admin_email)):
            pw = settings.super_admin_password or secrets.token_urlsafe(18) + "Aa1"
            db.add(User(email=settings.super_admin_email, name="Super Admin", is_super_admin=True,
                        password_hash=hash_password(pw), email_verified_at=datetime.now(timezone.utc)))
            db.commit()
            if not settings.super_admin_password:
                print(f"[seed] Super admin: {settings.super_admin_email}  senha (única vez): {pw}")
        for slug, name, bt, cents, ent in PLANS:
            if not db.scalar(select(Plan).where(Plan.slug == slug)):
                p = Plan(slug=slug, public_name=name, status="published")
                db.add(p)
                db.flush()
                db.add(PlanVersion(plan_id=p.id, version=1, billing_type=bt, amount_cents=cents, entitlements=ent,
                                   stripe_price_id=None))
        db.commit()
        if not settings.is_prod and not db.scalar(select(Tenant).where(Tenant.slug == "ufc-church")):
            t = Tenant(name="UFC Church", slug="ufc-church", type="church", timezone="America/Los_Angeles")
            pw = secrets.token_urlsafe(14) + "Aa1"
            u = User(email="pastor@ufcchurch.local", name="Pastor Demo", password_hash=hash_password(pw),
                     email_verified_at=datetime.now(timezone.utc))
            db.add_all([t, u])
            db.flush()
            db.add(Membership(user_id=u.id, tenant_id=t.id, role=Role.TENANT_ADMIN))
            db.commit()
            grant_trial(db, t.id)
            print(f"[seed] Piloto UFC Church: pastor@ufcchurch.local  senha (única vez): {pw}")


if __name__ == "__main__":
    run()
