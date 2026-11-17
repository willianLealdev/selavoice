"""SÓ DESENVOLVIMENTO: cria dados de DEMONSTRAÇÃO (uso, custo e vendas) para o painel do Super Admin ter o que mostrar.

Tudo é marcado com idempotency_key/source_ref "demo-..." e pode ser apagado com:  python tools_seed_demo_usage.py --clear
Os valores NÃO são reais: são inventados para testar gráficos. Nunca rodar em produção (recusa se ENV=production).
Rodar:  .venv\\Scripts\\python tools_seed_demo_usage.py
"""
import random
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import OneOffPurchase, PlanVersion, Tenant, UsageEvent

if get_settings().is_prod:
    sys.exit("Recusado: ambiente de produção.")

with SessionLocal() as db:
    if "--clear" in sys.argv:
        db.execute(delete(UsageEvent).where(UsageEvent.idempotency_key.like("demo-%")))
        db.execute(delete(OneOffPurchase).where(OneOffPurchase.stripe_session_id.like("demo-%")))
        db.commit()
        sys.exit("Dados de demonstração removidos.")
    tenants = db.scalars(select(Tenant)).all()
    pv = db.scalar(select(PlanVersion).order_by(PlanVersion.amount_cents.desc()))
    rnd = random.Random(7)
    now = datetime.now(timezone.utc)
    n = 0
    for t in tenants[:4]:
        for d in range(30):
            if rnd.random() < 0.45:
                continue
            for prov, lang, per_min in (("azure", "en", 0.04), ("gemini", "es", 0.05), ("mock", "fr", 0.0)):
                m = round(rnd.uniform(8, 90), 1)
                db.add(UsageEvent(tenant_id=t.id, language=lang, provider=prov, kind="language_minute", quantity=m,
                                  provider_cost_micros=int(m * per_min * 1_000_000), idempotency_key=f"demo-{t.id}-{d}-{prov}",
                                  created_at=now - timedelta(days=d, hours=rnd.randint(0, 20))))
                n += 1
    if pv:
        for i, t in enumerate(tenants[:3]):
            db.add(OneOffPurchase(tenant_id=t.id, plan_version_id=pv.id, stripe_session_id=f"demo-{i}", status="paid",
                                  events_remaining=1, created_at=now - timedelta(days=3 + i * 6)))
    db.commit()
    print(f"{n} lançamentos de uso e algumas vendas de DEMONSTRAÇÃO criados.")
