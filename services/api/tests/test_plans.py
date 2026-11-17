"""Planos completos: mensal/por evento, horas desde o início da transmissão, ilimitado, pessoas, idiomas, equipe."""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db import SessionLocal
from app.models import Entitlement, Event
from app.services.event_clock import tick
from app.services.plan_schema import PlanError, UNLIM, grant_amounts, limit, max_event_minutes, normalize
from conftest import make_event, register


def give_plan(client, h, **limits):
    """Troca o plano da organização por um com os limites dados (substitui o teste grátis)."""
    tid = client.get("/organizations/me", headers=h).json()["id"]
    g = grant_amounts(limits)
    with SessionLocal() as db:
        for e in db.query(Entitlement).filter(Entitlement.tenant_id == uuid.UUID(tid)).all():
            e.active = False
        db.add(Entitlement(tenant_id=uuid.UUID(tid), source="manual", source_ref=uuid.uuid4().hex, limits=limits,
                           events_remaining=g["events"], language_minutes_remaining=g["language_minutes"],
                           event_minutes_remaining=g["event_minutes"]))
        db.commit()


def backdate_start(event_id: str, minutes: float):
    """Simula que a transmissão começou há `minutes` minutos (sem esperar de verdade)."""
    with SessionLocal() as db:
        ev = db.get(Event, uuid.UUID(event_id))
        ev.started_at = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        ev.active_seconds = minutes * 60   # horas do plano contam só o tempo com fala: simula que houve fala todo o período
        db.commit()


def run_tick() -> int:
    return asyncio.run(tick())


# ---------------- esquema ----------------
def test_schema_unlimited_validation_and_amounts():
    n = normalize({"included_hours": None, "listener_concurrency": None, "max_languages": 5, "allowed_languages": ["EN", "es"],
                   "recordings": 1, "overage": "topup", "lixo": 1})
    assert n["included_hours"] is None and n["listener_concurrency"] is None and n["max_languages"] == 5
    assert n["allowed_languages"] == ["en", "es"] and n["recordings"] is True and "lixo" not in n
    for bad in ({"max_languages": -1}, {"included_hours": "x"}, {"overage": "x"}, {"allowed_languages": ["<b>"]}):
        with pytest.raises(PlanError):
            normalize(bad)
    g = grant_amounts({"included_events": None, "included_language_minutes": None, "included_hours": 2.5})
    assert g == {"events": UNLIM, "language_minutes": UNLIM, "event_minutes": 150}
    assert grant_amounts({"included_events": 3})["event_minutes"] is None        # plano antigo: sem limite de horas
    assert limit({"a": None}, "a", 7) is None and limit({}, "a", 7) == 7          # null = ilimitado; ausente = padrão
    assert max_event_minutes({"max_event_hours": 1.5}) == 90 and max_event_minutes({"max_event_hours": None}) is None


# ---------------- horas de transmissão ----------------
def test_hours_count_from_broadcast_start_and_stop_event_when_exhausted(client):
    h, _ = register(client, "Org Horas")
    give_plan(client, h, included_events=1, included_hours=1, max_event_hours=None, included_language_minutes=None)
    ev = make_event(client, h)
    backdate_start  # (mantém o import usado)
    # agendar NÃO conta horas: o relógio só corre depois do início
    assert client.get(f"/events/{ev['id']}/usage", headers=h).json()["elapsed_minutes"] == 0
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 200
    backdate_start(ev["id"], 30)
    assert run_tick() == 0                                                          # 30 min de 60: segue ao vivo
    u = client.get(f"/events/{ev['id']}/usage", headers=h).json()
    assert 29 <= u["charged_minutes"] <= 31 and 29 <= u["plan_minutes_remaining"] <= 31
    assert run_tick() == 0 and client.get(f"/events/{ev['id']}/usage", headers=h).json()["charged_minutes"] == u["charged_minutes"]  # sem cobrança em dobro
    backdate_start(ev["id"], 61)
    assert run_tick() == 1                                                          # estourou a hora incluída: encerra sozinho
    assert client.get(f"/events/{ev['id']}", headers=h).json()["status"] == "ENDED"
    assert client.get("/usage", headers=h).json()["events_remaining"] == 0


def test_no_hours_left_blocks_new_event(client):
    h, _ = register(client, "Org Sem Horas")
    give_plan(client, h, included_events=5, included_hours=0.0)
    ev = make_event(client, h)
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 402


def test_max_event_hours_cap_with_unlimited_plan_hours(client):
    h, _ = register(client, "Org Teto")
    give_plan(client, h, included_events=None, included_hours=None, max_event_hours=0.5)
    ev = make_event(client, h)
    client.post(f"/events/{ev['id']}/start", headers=h)
    backdate_start(ev["id"], 20)
    assert run_tick() == 0
    backdate_start(ev["id"], 31)
    assert run_tick() == 1
    assert client.get("/usage", headers=h).json()["events_remaining"] >= UNLIM // 2   # ilimitado continua ilimitado


def test_stop_rounds_partial_minute_up(client):
    h, _ = register(client, "Org Arredonda")
    give_plan(client, h, included_events=1, included_hours=2)
    ev = make_event(client, h)
    client.post(f"/events/{ev['id']}/start", headers=h)
    backdate_start(ev["id"], 10.2)
    client.post(f"/events/{ev['id']}/stop", headers=h)
    assert client.get(f"/events/{ev['id']}/usage", headers=h).json()["charged_minutes"] == 11


# ---------------- equipe, recursos, idiomas ----------------
def test_admin_seats_limit_and_unlimited(client):
    h, _ = register(client, "Org Equipe")
    give_plan(client, h, included_events=1, admin_seats=1)          # só o dono já ocupa a vaga
    assert client.post("/organizations/me/invitations", json={"email": "a@t.com", "role": "MEMBER"}, headers=h).status_code == 409
    give_plan(client, h, included_events=1, admin_seats=None)       # ilimitado
    assert client.post("/organizations/me/invitations", json={"email": "a@t.com", "role": "MEMBER"}, headers=h).status_code == 201


def test_plan_without_booklets_or_recording_is_blocked(client):
    h, _ = register(client, "Org Recursos")
    give_plan(client, h, included_events=2, pdf_booklets=False, recordings=False)
    ev = make_event(client, h, recording_policy="audio_and_transcript")
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 409           # plano sem gravação
    ev2 = make_event(client, h, "Sem gravar")
    assert client.post(f"/events/{ev2['id']}/start", headers=h).status_code == 200
    assert client.post(f"/documents/events/{ev2['id']}/generate", headers=h).status_code == 403   # plano sem documento


def test_allowed_languages_filter_for_listeners(client):
    h, _ = register(client, "Org Idiomas")
    give_plan(client, h, included_events=1, allowed_languages=["en", "es"])
    ev = make_event(client, h)
    client.post(f"/events/{ev['id']}/start", headers=h)
    codes = {l["code"] for l in client.get(f"/public/join/{ev['join_code']}").json()["languages"]}
    assert codes == {"en", "es"}


def test_admin_plan_version_validates_and_stores_unlimited(client, superadmin):
    pid = client.post("/admin/plans", json={"public_name": "Teste Ilimitado", "slug": f"ti-{uuid.uuid4().hex[:6]}"}, headers=superadmin).json()["id"]
    body = {"billing_type": "ONE_OFF", "amount_cents": 5000, "entitlements": {"included_events": 1, "included_hours": 4, "listener_concurrency": None, "allowed_languages": []}}
    assert client.post(f"/admin/plans/{pid}/versions", json=body, headers=superadmin).status_code == 201
    v = [p for p in client.get("/admin/plans", headers=superadmin).json() if p["id"] == pid][0]["versions"][0]
    assert v["entitlements"]["listener_concurrency"] is None and v["entitlements"]["included_hours"] == 4
    bad = {**body, "entitlements": {"max_languages": -5}}
    assert client.post(f"/admin/plans/{pid}/versions", json=bad, headers=superadmin).status_code == 422


# ---------------- ouvintes: lotação e idiomas simultâneos ----------------
def _listener_token(client, ev):
    return client.post(f"/public/join/{ev['join_code']}/token").json()["token"]


def test_listener_capacity_and_language_limit_enforced_on_websocket(client):
    from starlette.websockets import WebSocketDisconnect
    h, _ = register(client, "Org Lotacao")
    give_plan(client, h, included_events=1, listener_concurrency=1, max_languages=1)
    ev = make_event(client, h)
    client.post(f"/events/{ev['id']}/start", headers=h)
    sid, tok = ev["sessions"][0]["id"], _listener_token(client, ev)
    with client.websocket_connect(f"/sessions/{sid}/live") as w1:
        w1.send_json({"type": "auth", "token": tok, "lang": "en", "last_seq": 0})
        assert w1.receive_json()["type"] == "replay"
        with client.websocket_connect(f"/sessions/{sid}/live") as w2:          # 2º ouvinte: plano permite só 1
            w2.send_json({"type": "auth", "token": tok, "lang": "en", "last_seq": 0})
            assert w2.receive_json() == {"type": "error", "code": "event_full"}
            with pytest.raises(WebSocketDisconnect):
                w2.receive_json()
    client.post(f"/events/{ev['id']}/stop", headers=h)
    give_plan(client, h, included_events=1, listener_concurrency=None, max_languages=1)   # sem limite de pessoas, 1 idioma
    ev2 = make_event(client, h, "Dois")
    client.post(f"/events/{ev2['id']}/start", headers=h)
    sid2, tok2 = ev2["sessions"][0]["id"], _listener_token(client, ev2)
    with client.websocket_connect(f"/sessions/{sid2}/live") as a, client.websocket_connect(f"/sessions/{sid2}/live") as b:
        a.send_json({"type": "auth", "token": tok2, "lang": "en", "last_seq": 0})
        assert a.receive_json()["type"] == "replay"
        b.send_json({"type": "auth", "token": tok2, "lang": "es", "last_seq": 0})    # 2º idioma: acima do plano
        assert b.receive_json() == {"type": "error", "code": "language_limit"}
