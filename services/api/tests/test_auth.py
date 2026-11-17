"""Autenticação: senha forte, lockout, rotação/reuso de refresh, MFA do super admin, JWT forjado."""
import jwt
from conftest import PW, register


def test_weak_password_rejected(client):
    r = client.post("/auth/register", json={"email": "a@b.com", "password": "curta", "name": "x", "org_name": "Org"})
    assert r.status_code == 422


def test_login_generic_error_and_lockout(client):
    _, email = register(client)
    for _ in range(5):
        assert client.post("/auth/login", json={"email": email, "password": "errada-errada-1A"}).status_code == 401
    # após 5 falhas a conta bloqueia, mesmo com a senha certa
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 423
    # e-mail inexistente devolve a MESMA mensagem
    r = client.post("/auth/login", json={"email": "nao@existe.com", "password": "qualquer-coisa-1A"})
    assert r.status_code == 401 and "incorretos" in r.json()["detail"]


def test_refresh_rotation_and_reuse_detection(client):
    email = "rot@t.com"
    r = client.post("/auth/register", json={"email": email, "password": PW, "name": "x", "org_name": "Rot"},
                    headers={"X-Client": "mobile"})
    old = r.json()["refresh_token"]
    h = {"X-Client": "mobile"}
    r2 = client.post("/auth/refresh", json={"refresh_token": old}, headers=h)
    assert r2.status_code == 200
    new = r2.json()["refresh_token"]
    # Dentro da janela de tolerância (corrida legítima) o token antigo ainda é aceito, sem revogar.
    assert client.post("/auth/refresh", json={"refresh_token": old}, headers=h).status_code == 200
    # Fora da janela: "envelhece" o uso do token antigo e tenta reutilizar => 401 e revoga a família inteira.
    from datetime import datetime, timedelta, timezone
    from app.db import SessionLocal
    from app.models import RefreshToken
    from app.security import hash_token
    with SessionLocal() as db:
        t = db.query(RefreshToken).filter_by(token_hash=hash_token(old)).one()
        t.used_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        db.commit()
    assert client.post("/auth/refresh", json={"refresh_token": old}, headers=h).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": new}, headers=h).status_code == 401


def test_refresh_cookie_requires_csrf_header(client):
    client.post("/auth/register", json={"email": "c@t.com", "password": PW, "name": "x", "org_name": "Igreja C"})
    assert client.post("/auth/refresh", json={}).status_code == 403
    assert client.post("/auth/refresh", json={}, headers={"X-Requested-With": "selavoice"}).status_code == 200


def test_forged_and_none_alg_tokens_rejected(client):
    forged = jwt.encode({"sub": "x", "typ": "access", "iss": "selavoice"}, "outra-chave" * 5, algorithm="HS256")
    assert client.get("/events", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    none_tok = jwt.encode({"sub": "x", "typ": "access", "iss": "selavoice"}, None, algorithm="none")
    assert client.get("/events", headers={"Authorization": f"Bearer {none_tok}"}).status_code == 401
    assert client.get("/events").status_code == 401


def test_admin_routes_need_super_with_mfa(client, tenant_a, superadmin):
    assert client.get("/admin/tenants", headers=tenant_a).status_code == 403
    assert client.get("/admin/tenants", headers=superadmin).status_code == 200


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
