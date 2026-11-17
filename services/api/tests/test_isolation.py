"""Isolamento entre tenants (Fase 1): REST, WebSocket, PDF, elevação auditada do super admin."""
import pytest
from starlette.websockets import WebSocketDisconnect
from conftest import make_event


def test_tenant_cannot_read_or_write_other_tenant_event(client, tenant_a, tenant_b):
    ev = make_event(client, tenant_a, "Segredo A")
    eid = ev["id"]
    assert client.get(f"/events/{eid}", headers=tenant_b).status_code == 404
    assert client.patch(f"/events/{eid}", json={"title": "hack"}, headers=tenant_b).status_code == 404
    assert client.post(f"/events/{eid}/cancel", headers=tenant_b).status_code == 404
    assert client.get(f"/events/{eid}/history", headers=tenant_b).status_code == 404
    assert [e["id"] for e in client.get("/events", headers=tenant_b).json()] == []
    assert len(client.get("/events", headers=tenant_a).json()) == 1


def test_cannot_pick_foreign_org_via_header(client, tenant_a, tenant_b):
    me = client.get("/auth/me", headers=tenant_a).json()
    slug_a = me["memberships"][0]["slug"]
    r = client.get("/events", headers={**tenant_b, "X-Org-Slug": slug_a})
    assert r.status_code == 403  # tenant vem da membership, não do cliente


def test_websocket_cross_tenant_denied(client, tenant_a, tenant_b):
    sid = make_event(client, tenant_a)["sessions"][0]["id"]
    tok_b = tenant_b["Authorization"].split()[1]  # membro de OUTRO tenant
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:
        ws.send_json({"type": "auth", "token": tok_b, "lang": "en", "last_seq": 0})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4403


def test_transcripts_rest_cross_tenant_denied(client, tenant_a, tenant_b):
    sid = make_event(client, tenant_a)["sessions"][0]["id"]
    tok_b = tenant_b["Authorization"].split()[1]
    r = client.get(f"/sessions/{sid}/transcripts", params={"language": "en"}, headers={"X-Token": tok_b})
    assert r.status_code == 404


def test_listener_token_is_scoped_to_one_session(client, tenant_a):
    e1, e2 = make_event(client, tenant_a, "E1"), make_event(client, tenant_a, "E2")
    tok = client.post(f"/public/join/{e1['join_code']}/token").json()["token"]
    sid2 = e2["sessions"][0]["id"]
    r = client.get(f"/sessions/{sid2}/transcripts", params={"language": "en"}, headers={"X-Token": tok})
    assert r.status_code == 404
    # listener token não serve como login de API
    assert client.get("/events", headers={"Authorization": f"Bearer {tok}"}).status_code == 401


def test_super_admin_elevation_is_audited_and_readonly(client, tenant_a, superadmin):
    eid = make_event(client, tenant_a, "Visível ao suporte")["id"]
    tid = client.get("/auth/me", headers=tenant_a).json()["memberships"][0]["tenant_id"]
    # sem elevação o super admin não enxerga eventos de tenant
    assert client.get("/events", headers=superadmin).status_code == 403
    # motivo curto é recusado
    assert client.post("/admin/elevate", json={"tenant_id": tid, "reason": "oi"}, headers=superadmin).status_code == 422
    r = client.post("/admin/elevate", json={"tenant_id": tid, "reason": "Chamado de suporte #123 do cliente"}, headers=superadmin)
    elev = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert any(e["id"] == eid for e in client.get("/events", headers=elev).json())  # lê
    assert client.post(f"/events/{eid}/cancel", headers=elev).status_code == 403    # não escreve
    log = client.get("/admin/audit", headers=superadmin).json()
    assert any(l["action"] == "admin.elevate" and "suporte" in l["reason"] for l in log)


def test_suspended_tenant_blocked(client, tenant_a, superadmin):
    tid = client.get("/auth/me", headers=tenant_a).json()["memberships"][0]["tenant_id"]
    client.post(f"/admin/tenants/{tid}/suspend", json={"reason": "Pagamento em disputa aberta"}, headers=superadmin)
    assert client.get("/events", headers=tenant_a).status_code == 403
