"""Teste grátis CONFIGURÁVEL pelo dono (Super Admin): vale para contas novas, aparece na API pública e tem validação de plano."""
import uuid
from datetime import datetime, timezone

import pytest

from app.db import SessionLocal
from app.models import Entitlement
from app.services.platform_settings import DEFAULT_TRIAL, set_trial
from conftest import PW, make_event, register


@pytest.fixture(autouse=True)
def _restore_default_trial():
    yield
    with SessionLocal() as db:   # outros testes assumem o teste padrão ligado
        set_trial(db, enabled=DEFAULT_TRIAL["enabled"], days=DEFAULT_TRIAL["days"], limits=DEFAULT_TRIAL["limits"])


def _put(client, h, **body):
    return client.put("/admin/trial", json=body, headers=h)


def test_public_trial_reflects_defaults_and_is_open(client):
    j = client.get("/public/trial").json()                           # sem login: a landing precisa ler
    assert j["enabled"] is True and j["limits"]["included_events"] == 1 and j["limits"]["included_hours"] == 1


def test_only_super_admin_can_read_or_change(client, tenant_a):
    assert client.get("/admin/trial", headers=tenant_a).status_code == 403
    assert _put(client, tenant_a, enabled=True, limits={}).status_code == 403
    assert client.put("/admin/trial", json={"enabled": True, "limits": {}}).status_code in (401, 403)


def test_owner_config_applies_to_new_accounts_only(client, superadmin):
    old_h, _ = register(client, "Org Antiga")                       # criada com o teste padrão
    cfg = {"included_events": 3, "included_hours": 5, "max_event_hours": 2, "included_language_minutes": None,   # None = ilimitado
           "max_languages": 4, "listener_concurrency": None, "recordings": True, "pdf_booklets": True}
    r = _put(client, superadmin, enabled=True, days=14, limits=cfg)
    assert r.status_code == 200 and r.json()["days"] == 14
    pub = client.get("/public/trial").json()                         # a landing enxerga o que o dono configurou
    assert pub["limits"]["included_events"] == 3 and pub["limits"]["listener_concurrency"] is None and pub["days"] == 14
    new_h, _ = register(client, "Org Nova")
    tid = client.get("/organizations/me", headers=new_h).json()["id"]
    with SessionLocal() as db:
        e = db.query(Entitlement).filter_by(tenant_id=uuid.UUID(tid), source="trial").one()
        assert e.events_remaining == 3 and e.event_minutes_remaining == 300 and e.language_minutes_remaining >= 10**8   # ilimitado
        assert e.limits["recordings"] is True
        exp = e.expires_at.replace(tzinfo=timezone.utc)
        assert 13 <= (exp - datetime.now(timezone.utc)).days <= 14                                                       # validade em dias
    assert client.get("/usage", headers=old_h).json()["events_remaining"] == 1                                         # conta antiga intacta
    assert client.get("/usage", headers=new_h).json()["events_remaining"] == 3


def test_disabled_trial_gives_nothing_and_blocks_start(client, superadmin):
    assert _put(client, superadmin, enabled=False, limits=DEFAULT_TRIAL["limits"]).status_code == 200
    assert client.get("/public/trial").json()["enabled"] is False
    h, _ = register(client, "Org Sem Teste")
    assert client.get("/usage", headers=h).json()["events_remaining"] == 0
    ev = make_event(client, h)
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 402          # precisa contratar um plano


def test_trial_limits_are_validated_like_a_plan(client, superadmin):
    for bad in ({"max_languages": -1}, {"included_hours": "x"}, {"overage": "x"}, {"allowed_languages": ["<b>"]}):
        assert _put(client, superadmin, enabled=True, limits=bad).status_code == 422, bad
    assert _put(client, superadmin, enabled=True, days=0, limits={}).status_code == 422     # dias >= 1
    assert client.get("/public/trial").json()["limits"]["included_events"] == 1               # nada foi gravado


def test_trial_is_used_by_listener_and_language_limits(client, superadmin):
    """O teste usa as mesmas regras de plano: restringir idiomas no teste vale para o ouvinte."""
    _put(client, superadmin, enabled=True, limits={"included_events": 1, "included_hours": 1, "allowed_languages": ["en"]})
    h, _ = register(client, "Org Idioma Teste")
    ev = make_event(client, h)
    client.post(f"/events/{ev['id']}/start", headers=h)
    codes = {l["code"] for l in client.get(f"/public/join/{ev['join_code']}").json()["languages"]}
    assert codes == {"en"}
