"""Confirmação de e-mail no cadastro: conta nasce INATIVA, e-mail com link, uso único, reenvio, ativação manual pelo Super Admin."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.db import SessionLocal
from app.models import EmailVerification
from app.security import hash_token
from conftest import PW, register

S = get_settings()


@pytest.fixture()
def verify_on(monkeypatch):
    monkeypatch.setattr(S, "require_email_verification", True)
    yield


def _signup(client, email=None, name="Maria <b>"):
    email = email or f"{uuid.uuid4().hex[:8]}@t.com"
    r = client.post("/auth/register", json={"email": email, "password": PW, "name": name, "org_name": "Org Confirma"})
    return email, r


def test_signup_creates_inactive_account_and_blocks_login(client, verify_on):
    email, r = _signup(client)
    assert r.status_code == 201
    j = r.json()
    assert j["verification_required"] is True and not j["access_token"]            # nada de login automático
    assert "sv_refresh" not in r.headers.get("set-cookie", "")                      # nem cookie de sessão
    lg = client.post("/auth/login", json={"email": email, "password": PW})
    assert lg.status_code == 403 and "confirmado" in lg.json()["detail"]            # senha certa, mas conta inativa
    assert client.post("/auth/login", json={"email": email, "password": "errada-Errada-123"}).status_code == 401  # senha errada: genérico


def test_verify_link_activates_once_and_login_works(client, verify_on):
    email, r = _signup(client)
    tok = r.json()["dev_verify_token"]
    assert client.post("/auth/verify-email", json={"token": "lixo"}).status_code == 400
    assert client.post("/auth/verify-email", json={"token": tok}).status_code == 200
    assert client.post("/auth/verify-email", json={"token": tok}).status_code == 400      # uso único
    lg = client.post("/auth/login", json={"email": email, "password": PW})
    assert lg.status_code == 200 and lg.json()["access_token"]


def test_expired_token_rejected(client, verify_on):
    email, r = _signup(client)
    tok = r.json()["dev_verify_token"]
    with SessionLocal() as db:
        ev = db.query(EmailVerification).filter_by(token_hash=hash_token(tok)).one()
        ev.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post("/auth/verify-email", json={"token": tok}).status_code == 400
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 403


def test_resend_is_generic_has_cooldown_and_invalidates_old_link(client, verify_on, monkeypatch):
    email, r = _signup(client)
    old = r.json()["dev_verify_token"]
    sent = []
    import app.routers.auth as A
    monkeypatch.setattr(A, "send_verification", lambda to, name, token, lang="pt": sent.append((to, token)) or True)
    # dentro do intervalo de 1 minuto: não reenvia (mas responde igual)
    r1 = client.post("/auth/resend-verification", json={"email": email})
    assert r1.status_code == 202 and sent == []
    with SessionLocal() as db:   # simula que já passou 1 minuto
        for ev in db.query(EmailVerification).all():
            ev.created_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.commit()
    assert client.post("/auth/resend-verification", json={"email": email}).status_code == 202
    assert len(sent) == 1 and sent[0][0] == email
    assert client.post("/auth/verify-email", json={"token": old}).status_code == 400       # link antigo morreu
    assert client.post("/auth/verify-email", json={"token": sent[0][1]}).status_code == 200
    # e-mail inexistente: mesma resposta (não revela quem tem conta)
    assert client.post("/auth/resend-verification", json={"email": "ninguem@t.com"}).status_code == 202


def test_email_content_has_link_and_escapes_name(client, verify_on, monkeypatch):
    import app.services.email as E
    caught = {}
    monkeypatch.setattr(E, "send_email", lambda to, subject, h, t: caught.update(to=to, subject=subject, html=h, text=t) or (True, "sent"))
    email, r = _signup(client, name="<script>alert(1)</script>")
    assert caught["to"] == email and "/verificar?token=" in caught["text"] and "Confirme" in caught["subject"]
    assert "<script>" not in caught["html"]                                                  # nome escapado
    assert r.json()["email_sent"] is True


def test_production_never_exposes_token_in_response(client, verify_on, monkeypatch):
    monkeypatch.setattr(S, "app_env", "production")
    _, r = _signup(client)
    assert r.json()["verification_required"] is True and r.json()["dev_verify_token"] is None


def test_default_is_off_in_dev_and_on_in_production(monkeypatch):
    monkeypatch.setattr(S, "require_email_verification", None)
    monkeypatch.setattr(S, "app_env", "test")
    assert S.email_verification_required is False
    monkeypatch.setattr(S, "app_env", "production")
    assert S.email_verification_required is True


def test_invite_accept_confirms_email(client, tenant_a, verify_on):
    # convite: aceitar prova que é dono do e-mail => conta já nasce confirmada
    inv = client.post("/organizations/me/invitations", json={"email": f"{uuid.uuid4().hex[:6]}@t.com", "role": "MEMBER"}, headers=tenant_a).json()
    assert inv["invite_token"]
    mail = None
    with SessionLocal() as db:
        from app.models import Invitation
        mail = db.query(Invitation).order_by(Invitation.created_at.desc()).first().email
    assert client.post("/invitations/accept", json={"token": inv["invite_token"], "name": "Convidado", "password": PW}).status_code == 201
    assert client.post("/auth/login", json={"email": mail, "password": PW}).status_code == 200


def test_super_admin_sees_pending_and_can_activate_manually(client, superadmin, verify_on):
    email, _ = _signup(client)
    p = client.get("/admin/users/pending", headers=superadmin).json()
    mine = [u for u in p["users"] if u["email"] == email]
    assert mine and mine[0]["org"] == "Org Confirma" and "email_configured" in p
    uid = mine[0]["user_id"]
    assert client.post(f"/admin/users/{uid}/verify", json={"reason": "curto"}, headers=superadmin).status_code == 422
    assert client.post(f"/admin/users/{uid}/verify", json={"reason": "Resend ainda não configurado; ativação manual"}, headers=superadmin).status_code == 200
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 200
    assert not [u for u in client.get("/admin/users/pending", headers=superadmin).json()["users"] if u["email"] == email]
    assert client.get("/admin/users/pending").status_code in (401, 403)
