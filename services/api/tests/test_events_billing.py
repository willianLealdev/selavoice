"""Ciclo de vida de eventos (Fase 2) e cobrança/webhooks (Fase 7)."""
import json
import time

from app.config import get_settings
from app.services.billing import stripe_signature, verify_stripe_signature
from conftest import make_event

S = get_settings()


def test_lifecycle_and_invalid_transitions(client, tenant_a):
    ev = make_event(client, tenant_a)
    eid = ev["id"]
    assert ev["status"] == "SCHEDULED" and ev["join_url"].startswith("/e/")
    assert client.post(f"/events/{eid}/stop", headers=tenant_a).status_code == 409   # SCHEDULED -> ENDED inválido
    assert client.post(f"/events/{eid}/start", headers=tenant_a).status_code == 200  # trial cobre 1 evento
    assert client.patch(f"/events/{eid}", json={"original_language": "en"}, headers=tenant_a).status_code == 409   # após encerrar, idioma não muda
    assert client.post(f"/events/{eid}/cancel", headers=tenant_a).status_code == 409  # LIVE -> CANCELED inválido
    assert client.post(f"/events/{eid}/stop", headers=tenant_a).json()["status"] == "ENDED"
    assert client.post(f"/events/{eid}/start", headers=tenant_a).status_code == 409


def test_create_does_not_consume_quota(client, tenant_a):
    for i in range(3):
        make_event(client, tenant_a, f"E{i}")
    assert client.get("/usage", headers=tenant_a).json()["events_remaining"] == 1  # só o trial, intacto


def test_qr_join_resolves_correct_event_and_hides_canceled(client, tenant_a):
    e1, e2 = make_event(client, tenant_a, "Um"), make_event(client, tenant_a, "Dois")
    assert client.get(f"/public/join/{e2['join_code']}").json()["title"] == "Dois"
    client.post(f"/events/{e1['id']}/cancel", headers=tenant_a)
    assert client.get(f"/public/join/{e1['join_code']}").status_code == 404
    assert client.get("/public/join/naoexiste").status_code == 404


def test_search_filters(client, tenant_a):
    make_event(client, tenant_a, "Culto de Domingo", presenter="Pr. João")
    make_event(client, tenant_a, "Expo Fé", type="expo")
    assert len(client.get("/events", params={"q": "domingo"}, headers=tenant_a).json()) == 1
    assert len(client.get("/events", params={"type": "expo"}, headers=tenant_a).json()) == 1
    assert len(client.get("/events", params={"presenter": "joão"}, headers=tenant_a).json()) == 1


def test_no_entitlement_blocks_start(client, tenant_a):
    e1, e2 = make_event(client, tenant_a, "A"), make_event(client, tenant_a, "B")
    assert client.post(f"/events/{e1['id']}/start", headers=tenant_a).status_code == 200
    client.post(f"/events/{e1['id']}/stop", headers=tenant_a)
    assert client.post(f"/events/{e2['id']}/start", headers=tenant_a).status_code == 402  # trial esgotado


# ---------------- Stripe ----------------
def _webhook(client, event, secret=None, ts=None):
    payload = json.dumps(event).encode()
    sig = stripe_signature(payload, secret or S.stripe_webhook_secret, ts)
    return client.post("/billing/webhook/stripe", content=payload, headers={"Stripe-Signature": sig})


def _checkout_event(eid, session, tid, pv, paid=True):
    return {"id": eid, "type": "checkout.session.completed", "data": {"object": {
        "id": session, "payment_status": "paid" if paid else "unpaid",
        "metadata": {"tenant_id": tid, "plan_version_id": pv}}}}


def _tid(client, h):
    return client.get("/auth/me", headers=h).json()["memberships"][0]["tenant_id"]


def test_webhook_signature_required(client):
    assert client.post("/billing/webhook/stripe", content=b"{}").status_code == 400
    assert _webhook(client, {"id": "e1"}, secret="whsec_errado").status_code == 400
    assert _webhook(client, {"id": "e1"}, ts=int(time.time()) - 4000).status_code == 400  # replay antigo


def test_verified_webhook_grants_once_and_replay_is_ignored(client, tenant_a, paid_plan):
    tid = _tid(client, tenant_a)
    before = client.get("/usage", headers=tenant_a).json()["events_remaining"]
    ev = _checkout_event("evt_1", "cs_1", tid, paid_plan)
    assert _webhook(client, ev).json()["outcome"] == "granted"
    assert _webhook(client, ev).json()["outcome"] == "duplicate"          # mesmo evento: ignorado
    ev2 = _checkout_event("evt_2", "cs_1", tid, paid_plan)                # outro evento, mesma sessão
    assert _webhook(client, ev2).json()["outcome"] in ("duplicate_grant", "granted") 
    assert client.get("/usage", headers=tenant_a).json()["events_remaining"] == before + 1


def test_failed_payment_does_not_grant(client, tenant_a, paid_plan):
    tid = _tid(client, tenant_a)
    before = client.get("/usage", headers=tenant_a).json()["events_remaining"]
    _webhook(client, _checkout_event("evt_u", "cs_u", tid, paid_plan, paid=False))
    assert client.get("/usage", headers=tenant_a).json()["events_remaining"] == before


def test_frontend_redirect_alone_grants_nothing(client, tenant_a, paid_plan):
    r = client.post("/checkout", json={"plan_version_id": paid_plan}, headers=tenant_a)
    assert r.status_code == 200 and "fake-checkout" in r.json()["checkout_url"]
    assert client.get("/usage", headers=tenant_a).json()["events_remaining"] == 1  # nada concedido ainda
    # só o webhook (via caminho verificado) concede
    assert client.post("/billing/fake/complete", params={"session_id": r.json()["session_id"]}, headers=tenant_a).json()["outcome"] == "granted"
    assert client.get("/usage", headers=tenant_a).json()["events_remaining"] == 2


def test_one_off_cannot_start_two_simultaneous_events(client, tenant_a, paid_plan):
    tid = _tid(client, tenant_a)
    _webhook(client, _checkout_event("evt_p", "cs_p", tid, paid_plan))  # agora 2 eventos disponíveis (trial + avulso)
    a, b = make_event(client, tenant_a, "A"), make_event(client, tenant_a, "B")
    assert client.post(f"/events/{a['id']}/start", headers=tenant_a).status_code == 200
    assert client.post(f"/events/{b['id']}/start", headers=tenant_a).status_code == 409  # limite de 1 simultâneo


def test_cross_tenant_billing_denied(client, tenant_a, tenant_b, paid_plan):
    r = client.post("/checkout", json={"plan_version_id": paid_plan}, headers=tenant_a)
    # tenant B não consegue completar a sessão de checkout do tenant A
    assert client.post("/billing/fake/complete", params={"session_id": r.json()["session_id"]}, headers=tenant_b).status_code == 404


def test_plan_versions_are_immutable_history(client, superadmin):
    pid = client.post("/admin/plans", json={"public_name": "P", "slug": "p-imut"}, headers=superadmin).json()["id"]
    v1 = client.post(f"/admin/plans/{pid}/versions", headers=superadmin,
                     json={"billing_type": "MONTHLY", "amount_cents": 1000}).json()
    v2 = client.post(f"/admin/plans/{pid}/versions", headers=superadmin,
                     json={"billing_type": "MONTHLY", "amount_cents": 2000}).json()
    assert (v1["version"], v2["version"]) == (1, 2) and v1["stripe_price_id"] != v2["stripe_price_id"]
    versions = [p for p in client.get("/admin/plans", headers=superadmin).json() if p["id"] == pid][0]["versions"]
    assert [v["amount_cents"] for v in versions] == [1000, 2000]  # v1 preservada


def test_signature_verifier_unit():
    p = b'{"a":1}'
    h = stripe_signature(p, "s")
    assert verify_stripe_signature(p, h, "s", 300)
    assert not verify_stripe_signature(p + b" ", h, "s", 300)
    assert not verify_stripe_signature(p, "lixo", "s", 300)


def test_datetimes_are_returned_with_timezone(client, tenant_a):
    """Sem fuso o navegador mostraria a hora errada (bug visto em SQLite)."""
    ev = make_event(client, tenant_a)
    assert ev["starts_at"].endswith(("Z", "+00:00"))
    assert client.get(f"/public/join/{ev['join_code']}").json()["starts_at"].endswith(("Z", "+00:00"))


def test_webhook_refused_in_production_without_real_secret(client, monkeypatch):
    """Produção sem segredo de webhook salvo no painel: recusa tudo (nada de aceitar o segredo padrão de desenvolvimento)."""
    from app.services import billing as B
    payload = json.dumps({"id": "evt_x", "type": "checkout.session.completed", "data": {"object": {}}}).encode()
    monkeypatch.setattr(B.settings, "app_env", "production")
    assert B.webhook_secret() == ""                                                   # padrão de dev ignorado em produção
    assert not verify_stripe_signature(payload, stripe_signature(payload, ""), "", 300)  # chave vazia nunca valida
    r = client.post("/billing/webhook/stripe", content=payload, headers={"Stripe-Signature": stripe_signature(payload, S.stripe_webhook_secret)})
    assert r.status_code == 400                                                       # assinatura forjada com o padrão: recusada
