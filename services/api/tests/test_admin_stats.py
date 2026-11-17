"""Super Admin: visão geral, acessos, financeiro, tarifas. Só o Super Admin com MFA acessa."""
from datetime import datetime, timezone

from app.db import SessionLocal
from app.models import UsageEvent
from conftest import register


def test_stats_require_super_admin(client, tenant_a):
    for path in ("/admin/overview", "/admin/access", "/admin/finance"):
        assert client.get(path, headers=tenant_a).status_code == 403
        assert client.get(path).status_code in (401, 403)
    assert client.put("/admin/providers/mock/rate", json={"usd_per_min": 1}, headers=tenant_a).status_code == 403


def test_overview_counts_usage_and_cost(client, superadmin, tenant_a):
    h, _ = register(client, "Org Custo")
    tid = client.get("/organizations/me", headers=h).json()["id"]
    with SessionLocal() as db:
        db.add(UsageEvent(tenant_id=__import__("uuid").UUID(tid), language="en", provider="azure", kind="language_minute", quantity=10,
                          provider_cost_micros=400_000, idempotency_key="t-ov-1", created_at=datetime.now(timezone.utc)))
        db.commit()
    o = client.get("/admin/overview?days=7", headers=superadmin).json()
    assert o["kpis"]["language_minutes"] >= 10 and o["kpis"]["ai_cost_usd"] >= 0.4
    assert len(o["series"]["labels"]) == 7 and len(o["series"]["minutes"]) == 7
    assert any(p["provider"] == "azure" and p["cost_usd"] >= 0.4 for p in o["cost_by_provider"])
    assert any(t["name"] == "Org Custo" for t in o["top_tenants"])
    assert o["kpis"]["online_users"] >= 1   # o próprio super admin acabou de entrar


def test_access_lists_online_and_revoke(client, superadmin):
    h, email = register(client, "Org Acesso")
    a = client.get("/admin/access", headers=superadmin).json()
    mine = [s for s in a["sessions"] if s["email"] == email]
    assert mine and mine[0]["active_now"] and mine[0]["org"] == "Org Acesso"
    assert a["events_week"].get("auth.register", 0) >= 1
    uid = mine[0]["user_id"]
    assert client.post(f"/admin/users/{uid}/revoke-sessions", json={"reason": "curto"}, headers=superadmin).status_code == 422
    r = client.post(f"/admin/users/{uid}/revoke-sessions", json={"reason": "teste de segurança do suporte"}, headers=superadmin)
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    assert not [s for s in client.get("/admin/access", headers=superadmin).json()["sessions"] if s["email"] == email]


def test_rate_and_finance(client, superadmin):
    assert client.put("/admin/providers/azure/rate", json={"usd_per_min": 0.12}, headers=superadmin).status_code == 200
    f = client.get("/admin/finance", headers=superadmin).json()
    assert [r for r in f["rates"] if r["provider"] == "azure"][0]["usd_per_min"] == 0.12
    assert client.put("/admin/providers/azure/rate", json={"usd_per_min": None}, headers=superadmin).status_code == 200
    assert [r for r in client.get("/admin/finance", headers=superadmin).json()["rates"] if r["provider"] == "azure"][0]["configured"] is False
    assert client.put("/admin/providers/naoexiste/rate", json={"usd_per_min": 1}, headers=superadmin).status_code == 404
    assert client.put("/admin/providers/azure/rate", json={"usd_per_min": -1}, headers=superadmin).status_code == 422
