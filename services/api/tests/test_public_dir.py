"""Diretório público: busca por nome, perfil/QR da igreja, privacidade."""
from conftest import make_event, register


def test_search_finds_listed_org_and_hides_unlisted(client):
    h, _ = register(client, "Igreja Busca Alfa")
    h2, _ = register(client, "Igreja Busca Beta")
    assert {o["name"] for o in client.get("/public/orgs", params={"q": "busca"}).json()} >= {"Igreja Busca Alfa", "Igreja Busca Beta"}
    client.patch("/organizations/me", json={"listed": False}, headers=h2)
    names = {o["name"] for o in client.get("/public/orgs", params={"q": "busca"}).json()}
    assert "Igreja Busca Alfa" in names and "Igreja Busca Beta" not in names
    assert client.get("/organizations/me", headers=h2).json()["listed"] is False
    # o perfil por slug (QR) continua acessível mesmo não listada
    slug = client.get("/auth/me", headers=h2).json()["memberships"][0]["slug"]
    assert client.get(f"/public/orgs/{slug}").status_code == 200


def test_search_validation_and_wildcards(client):
    register(client, "Igreja Curinga")
    assert client.get("/public/orgs", params={"q": "a"}).status_code == 422          # mínimo 2 letras
    assert client.get("/public/orgs", params={"q": "%%"}).json() == []                # % não vira curinga
    assert client.get("/public/orgs", params={"q": "_____"}).json() == []


def test_profile_shows_only_live_and_scheduled_public_fields(client):
    h, _ = register(client, "Igreja Perfil")
    slug = client.get("/auth/me", headers=h).json()["memberships"][0]["slug"]
    live = make_event(client, h, "Ao vivo", starts_at="2030-01-01T10:00:00Z")
    client.post(f"/events/{live['id']}/start", headers=h)
    canceled = make_event(client, h, "Cancelado")
    client.post(f"/events/{canceled['id']}/cancel", headers=h)
    p = client.get(f"/public/orgs/{slug}").json()
    assert [e["title"] for e in p["events"]] == ["Ao vivo"] and p["events"][0]["status"] == "LIVE"
    assert "email" not in str(p).lower() and "members" not in p
    assert client.get("/public/orgs/nao-existe").status_code == 404


def test_suspended_org_hidden(client, superadmin):
    h, _ = register(client, "Igreja Suspensa Zeta")
    me = client.get("/auth/me", headers=h).json()["memberships"][0]
    client.post(f"/admin/tenants/{me['tenant_id']}/suspend", json={"reason": "Teste de suspensão pública"}, headers=superadmin)
    assert client.get(f"/public/orgs/{me['slug']}").status_code == 404
    assert all(o["slug"] != me["slug"] for o in client.get("/public/orgs", params={"q": "Suspensa Zeta"}).json())
