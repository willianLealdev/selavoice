"""Ativar plano MANUAL (Super Admin) e EVENTO PRIVADO com senha."""
import pytest

from app.db import SessionLocal
from app.models import Entitlement
from app.services.platform_settings import DEFAULT_TRIAL, set_trial
from conftest import make_event, register


@pytest.fixture(autouse=True)
def _restore_trial():
    yield
    with SessionLocal() as db:
        set_trial(db, enabled=DEFAULT_TRIAL["enabled"], days=DEFAULT_TRIAL["days"], limits=DEFAULT_TRIAL["limits"])


def _no_trial(client, su):
    assert client.put("/admin/trial", json={"enabled": False, "days": None, "limits": {}}, headers=su).status_code == 200


def _tenant_id(client, su, h):
    me = client.get("/organizations/me", headers=h).json()
    return next(t["id"] for t in client.get("/admin/tenants", headers=su).json() if t["slug"] == me["slug"])


def test_manual_lifetime_plan_unblocks_start_and_is_audited(client, superadmin):
    _no_trial(client, superadmin)
    h, _ = register(client, "Sem Plano")
    tid = _tenant_id(client, superadmin, h)
    ev = make_event(client, h)
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 402          # sem plano: recusa
    assert client.get(f"/admin/tenants/{tid}/entitlements", headers=superadmin).json() == []
    assert client.post(f"/admin/tenants/{tid}/grant-plan", json={"unlimited": True, "reason": "curto"}, headers=superadmin).status_code == 422
    r = client.post(f"/admin/tenants/{tid}/grant-plan", json={"unlimited": True, "reason": "parceria com a igreja"}, headers=superadmin)
    assert r.status_code == 201 and r.json()["unlimited"] and r.json()["expires_at"] is None and r.json()["source"] == "manual"
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 200            # agora libera
    client.post(f"/events/{ev['id']}/stop", headers=h)
    ent = client.get(f"/admin/tenants/{tid}/entitlements", headers=superadmin).json()[0]
    assert client.post(f"/admin/entitlements/{ent['id']}/deactivate", json={"reason": "fim da parceria"}, headers=superadmin).status_code == 200
    ev2 = make_event(client, h, "Outro")
    assert client.post(f"/events/{ev2['id']}/start", headers=h).status_code == 402          # desativado: volta a recusar


def test_grant_requires_super_admin_and_valid_choice(client, superadmin, tenant_a):
    tid = _tenant_id(client, superadmin, tenant_a)
    assert client.post(f"/admin/tenants/{tid}/grant-plan", json={"unlimited": True, "reason": "x" * 12}, headers=tenant_a).status_code == 403
    assert client.get(f"/admin/tenants/{tid}/entitlements", headers=tenant_a).status_code == 403
    assert client.post(f"/admin/tenants/{tid}/grant-plan", json={"reason": "x" * 12}, headers=superadmin).status_code == 422   # nem plano nem vitalício


def test_manual_grant_with_days_expires(client, superadmin, tenant_a):
    tid = _tenant_id(client, superadmin, tenant_a)
    r = client.post(f"/admin/tenants/{tid}/grant-plan", json={"unlimited": True, "days": 30, "reason": "cortesia de 30 dias"}, headers=superadmin)
    assert r.status_code == 201 and r.json()["expires_at"]


# ---------------------------------------------------------------- evento privado
def test_private_event_needs_password_and_is_hidden(client, tenant_a):
    assert client.post("/events", json={"title": "X", "starts_at": "2030-01-01T18:00:00Z", "private": True}, headers=tenant_a).status_code == 422
    ev = make_event(client, tenant_a, "Secreto", private=True, access_password="senha123")
    assert ev["private"] is True and "senha123" not in str(ev)
    code = ev["join_code"]
    j = client.get(f"/public/join/{code}").json()
    assert j["private"] is True and "languages" not in j and "presenter" not in j                # sem senha: só o mínimo
    assert client.get(f"/public/join/{code}", headers={"X-Event-Password": "errada"}).json()["private"] is True
    assert client.get(f"/public/join/{code}", headers={"X-Event-Password": "senha123"}).json()["private"] is False
    assert client.post(f"/public/join/{code}/token").status_code == 403
    assert client.post(f"/public/join/{code}/token", json={"password": "errada"}).status_code == 403
    assert client.post(f"/public/join/{code}/token", json={"password": "senha123"}).status_code == 200
    assert client.get(f"/public/booklets/{code}").status_code == 404                              # apostilas não vazam pelo código


def test_private_event_not_listed_but_public_is(client, tenant_a):
    slug = client.get("/organizations/me", headers=tenant_a).json()["slug"]
    make_event(client, tenant_a, "Aberto")
    make_event(client, tenant_a, "Fechado", private=True, access_password="abcd1234")
    titles = [e["title"] for e in client.get(f"/public/orgs/{slug}").json()["events"]]
    assert "Fechado" not in titles
    ev = make_event(client, tenant_a, "Publico2")
    assert client.get(f"/public/join/{ev['join_code']}").json()["private"] is False              # público segue sem senha
    assert client.post(f"/public/join/{ev['join_code']}/token").status_code == 200


# ---------------------------------------------------------------- horas só com fala
def test_event_hours_count_only_speech_not_silence(client, superadmin, monkeypatch):
    import time
    import uuid
    from app.models import Event
    from app.services import channels as C
    from app.services.event_clock import tick
    import asyncio
    _no_trial(client, superadmin)
    h, _ = register(client, "So Fala")
    tid = _tenant_id(client, superadmin, h)
    with SessionLocal() as db:   # plano com 60 min de transmissão
        pass
    client.post(f"/admin/tenants/{tid}/grant-plan", json={"unlimited": True, "reason": "teste de horas"}, headers=superadmin)
    ev = make_event(client, h)
    client.post(f"/events/{ev['id']}/start", headers=h)
    with SessionLocal() as db:   # evento "ao vivo" há 30 min, mas SEM nenhuma fala
        e = db.get(Event, uuid.UUID(ev["id"]))
        from datetime import datetime, timedelta, timezone
        e.started_at = datetime.now(timezone.utc) - timedelta(minutes=30)
        db.commit()
    asyncio.run(tick())
    u = client.get(f"/events/{ev['id']}/usage", headers=h).json()
    assert u["charged_minutes"] == 0 and u["elapsed_minutes"] >= 29            # 30 min de relógio, 0 min de fala
    ch = C._Chan(tenant_id=None, event_id=uuid.UUID(ev["id"]), session_id="s", lang="en", source_lang="pt")
    now = [100.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    C.manager._touch_active(ch)
    for _ in range(90):                                                         # 90 s de tradução contínua
        now[0] += 1.0
        C.manager._touch_active(ch)
    asyncio.run(tick())
    assert client.get(f"/events/{ev['id']}/usage", headers=h).json()["charged_minutes"] == 1


def test_tenants_list_shows_current_plan(client, superadmin):
    _no_trial(client, superadmin)
    h, _ = register(client, "Mostra Plano")
    tid = _tenant_id(client, superadmin, h)
    plan = lambda: next(t["plan"] for t in client.get("/admin/tenants", headers=superadmin).json() if t["id"] == tid)
    assert plan() == "Sem plano"
    client.post(f"/admin/tenants/{tid}/grant-plan", json={"unlimited": True, "reason": "teste de rótulo"}, headers=superadmin)
    assert plan() == "Vitalício (manual)"
