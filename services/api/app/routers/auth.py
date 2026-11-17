"""Autenticação: registro (auto-onboarding), login, refresh com rotação, MFA, /me.

Segurança embutida:
- Senhas Argon2id + política de força; bloqueio após N falhas; mensagem de erro genérica.
- Refresh token em cookie httpOnly (web) — exige cabeçalho X-Requested-With (anti-CSRF);
  para mobile o token vai no corpo (header X-Client: mobile).
- Rotação: cada refresh invalida o anterior; reuso de token antigo revoga a família toda.
- Super admin: MFA (TOTP) obrigatório para rotas /admin.
"""
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import get_settings
from ..core.ratelimit import client_ip, rate_limit
from ..db import get_db
from ..deps import current_claims, current_user
from ..models import EmailVerification, Membership, PasswordReset, RefreshToken, Role, Tenant, User
from ..security import (create_access_token, decrypt_secret, encrypt_secret, hash_password,
                        hash_token, new_refresh_token, new_totp_secret, totp_uri,
                        validate_password_strength, verify_password, verify_totp)
from ..services.billing import grant_trial
from ..services.email import email_configured, send_password_reset, send_verification

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])
_auth_limit = rate_limit("auth", settings.auth_rate_limit_per_minute)
# Tolerância para corridas legítimas de refresh (ver ADR-010). Fora dela, reuso = suspeita de roubo.
REUSE_GRACE_SECONDS = 10


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=160)
    org_name: str = Field(min_length=2, max_length=160)
    org_type: str = Field(default="church", pattern="^(church|conference|expo|fair|corporate|education|association|other)$")


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)  # sem validar domínio: o seed usa .local
    password: str = Field(max_length=200)
    totp_code: str | None = None


class RegisterOut(BaseModel):
    """Cadastro: com confirmação de e-mail LIGADA não há login ainda (verification_required=True e sem tokens)."""
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    mfa_required_setup: bool = False
    verification_required: bool = False
    email_sent: bool = False
    dev_verify_token: str | None = None  # SÓ em desenvolvimento/teste (nunca em produção)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str | None = None  # só para clientes mobile
    token_type: str = "bearer"
    mfa_required_setup: bool = False


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:50] or "org"


def _issue(db: Session, user: User, response: Response, *, mobile: bool, mfa: bool,
           family: uuid.UUID | None = None) -> TokenOut:
    raw, h = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, family_id=family or uuid.uuid4(), token_hash=h, mfa=mfa,
                        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)))
    db.commit()
    access = create_access_token(str(user.id), mfa=mfa)
    if not mobile:
        response.set_cookie("sv_refresh", raw, httponly=True, secure=settings.is_prod, samesite="strict",
                            max_age=settings.refresh_token_days * 86400, path="/auth")
    need_setup = user.is_super_admin and not user.mfa_enabled
    return TokenOut(access_token=access, refresh_token=raw if mobile else None, mfa_required_setup=need_setup)


def _new_verification(db: Session, user: User) -> tuple[str, bool]:
    """Invalida links antigos, cria um novo token (24 h) e envia o e-mail. Retorna (token, enviado?)."""
    now = datetime.now(timezone.utc)
    for old in db.scalars(select(EmailVerification).where(EmailVerification.user_id == user.id, EmailVerification.used_at.is_(None))):
        old.used_at = now
    raw = secrets.token_urlsafe(32)
    db.add(EmailVerification(user_id=user.id, token_hash=hash_token(raw),
                             expires_at=now + timedelta(hours=settings.email_verification_hours)))
    db.commit()
    return raw, send_verification(user.email, user.name, raw)


@router.post("/register", response_model=RegisterOut, status_code=201, dependencies=[Depends(_auth_limit)])
def register(body: RegisterIn, response: Response, request: Request, db: Session = Depends(get_db),
             x_client: str | None = Header(default=None)):
    err = validate_password_strength(body.password)
    if err:
        raise HTTPException(422, err)
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        # Resposta neutra o suficiente; não confirma a existência (mas 409 é necessário para UX).
        raise HTTPException(409, "Não foi possível criar a conta com esses dados.")
    need_verify = settings.email_verification_required
    user = User(email=email, name=body.name, password_hash=hash_password(body.password),
                email_verified_at=None if need_verify else datetime.now(timezone.utc))
    slug = _slugify(body.org_name)
    if db.scalar(select(Tenant).where(Tenant.slug == slug)):
        slug = f"{slug}-{uuid.uuid4().hex[:5]}"
    tenant = Tenant(name=body.org_name, slug=slug, type=body.org_type)
    db.add_all([user, tenant])
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=Role.TENANT_ADMIN))
    db.commit()
    grant_trial(db, tenant.id)  # teste gratuito pequeno (não é pagamento)
    audit(db, action="auth.register", actor_id=user.id, tenant_id=tenant.id, ip=client_ip(request))
    if need_verify:   # conta criada, mas INATIVA até o dono do e-mail clicar no link
        raw, sent = _new_verification(db, user)
        return RegisterOut(verification_required=True, email_sent=sent,
                           dev_verify_token=None if settings.is_prod else raw)
    return RegisterOut(**_issue(db, user, response, mobile=x_client == "mobile", mfa=False).model_dump())


@router.post("/login", response_model=TokenOut, dependencies=[Depends(_auth_limit)])
def login(body: LoginIn, response: Response, request: Request, db: Session = Depends(get_db),
          x_client: str | None = Header(default=None)):
    generic = HTTPException(401, "E-mail ou senha incorretos.")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(423, "Conta temporariamente bloqueada. Tente mais tarde.")
    ok = verify_password(body.password, user.password_hash if user else None)  # sempre gasta tempo
    if not user or not ok or user.status != "active":
        if user:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_login_failures:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
                audit(db, action="auth.lockout", actor_id=user.id, ip=client_ip(request), commit=False)
            db.commit()
        raise generic
    if settings.email_verification_required and not user.email_verified_at:
        # Só chega aqui com a SENHA CORRETA, então avisar não revela nada a terceiros.
        raise HTTPException(403, "E-mail ainda não confirmado. Abra o link que enviamos para ativar a conta.")
    mfa_ok = False
    if user.is_super_admin and user.mfa_enabled:
        if not body.totp_code or not verify_totp(decrypt_secret(user.mfa_secret_enc), body.totp_code):
            raise HTTPException(401, "Código MFA obrigatório ou incorreto.")
        mfa_ok = True
    user.failed_logins = 0
    db.commit()
    audit(db, action="auth.login", actor_id=user.id, ip=client_ip(request))
    return _issue(db, user, response, mobile=x_client == "mobile", mfa=mfa_ok)


class RefreshIn(BaseModel):
    refresh_token: str | None = None


@router.post("/refresh", response_model=TokenOut, dependencies=[Depends(_auth_limit)])
def refresh(body: RefreshIn, response: Response, db: Session = Depends(get_db),
            sv_refresh: str | None = Cookie(default=None),
            x_client: str | None = Header(default=None),
            x_requested_with: str | None = Header(default=None)):
    mobile = x_client == "mobile"
    if not mobile and x_requested_with != "selavoice":
        raise HTTPException(403, "Requisição não permitida (CSRF).")
    raw = body.refresh_token if mobile else sv_refresh
    if not raw:
        raise HTTPException(401, "Sessão ausente.")
    tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw)))
    if not tok or tok.revoked:
        raise HTTPException(401, "Sessão inválida.")
    now = datetime.now(timezone.utc)
    reuse = tok.used_at is not None
    if reuse and (now - tok.used_at.replace(tzinfo=timezone.utc)).total_seconds() > REUSE_GRACE_SECONDS:
        # REUSO fora da janela de tolerância: possível roubo -> revoga toda a família.
        for t in db.scalars(select(RefreshToken).where(RefreshToken.family_id == tok.family_id)):
            t.revoked = True
        db.commit()
        audit(db, action="auth.refresh_reuse", actor_id=tok.user_id, reason="reuso de refresh token")
        raise HTTPException(401, "Sessão inválida.")
    # Dentro da tolerância (corrida legítima: 2 abas/requisições simultâneas): emite novo token
    # na mesma família sem revogar.
    if tok.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(401, "Sessão expirada.")
    user = db.get(User, tok.user_id)
    if not user or user.status != "active":
        raise HTTPException(401, "Usuário inativo.")
    if not reuse:
        tok.used_at = now
        db.commit()
    return _issue(db, user, response, mobile=mobile, mfa=tok.mfa, family=tok.family_id)


@router.post("/logout", status_code=204)
def logout(response: Response, db: Session = Depends(get_db), sv_refresh: str | None = Cookie(default=None)):
    if sv_refresh:
        tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(sv_refresh)))
        if tok:
            for t in db.scalars(select(RefreshToken).where(RefreshToken.family_id == tok.family_id)):
                t.revoked = True
            db.commit()
    response.delete_cookie("sv_refresh", path="/auth")


# ---------------- MFA ----------------
@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Gera segredo TOTP (mostrar QR com a URI). Só vira ativo após /mfa/verify."""
    if user.mfa_enabled:
        raise HTTPException(409, "MFA já ativo.")
    secret = new_totp_secret()
    user.mfa_secret_enc = encrypt_secret(secret)
    db.commit()
    return {"secret": secret, "otpauth_uri": totp_uri(secret, user.email)}


class MfaVerifyIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


@router.post("/mfa/verify", response_model=TokenOut, dependencies=[Depends(_auth_limit)])
def mfa_verify(body: MfaVerifyIn, response: Response, user: User = Depends(current_user),
               db: Session = Depends(get_db), x_client: str | None = Header(default=None)):
    if not user.mfa_secret_enc or not verify_totp(decrypt_secret(user.mfa_secret_enc), body.code):
        raise HTTPException(401, "Código incorreto.")
    user.mfa_enabled = True
    db.commit()
    audit(db, action="auth.mfa_enabled", actor_id=user.id)
    return _issue(db, user, response, mobile=x_client == "mobile", mfa=True)


# ---------------- /me ----------------
@router.get("/me")
def me(user: User = Depends(current_user), claims: dict = Depends(current_claims),
       db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, Tenant).join(Tenant, Tenant.id == Membership.tenant_id)
                      .where(Membership.user_id == user.id)).all()
    return {
        "id": str(user.id), "email": user.email, "name": user.name,
        "is_super_admin": user.is_super_admin, "mfa_enabled": user.mfa_enabled,
        "mfa_session": bool(claims.get("mfa")),
        "memberships": [{"tenant_id": str(t.id), "slug": t.slug, "name": t.name, "role": m.role.value,
                         "branding": t.branding} for m, t in rows],
    }


# ---------------- Esqueci / redefinir senha (e-mail via Resend) ----------------
class ForgotIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


@router.post("/forgot", status_code=202, dependencies=[Depends(rate_limit("forgot", 5))])
def forgot(body: ForgotIn, request: Request, db: Session = Depends(get_db)):
    """Sempre responde 202 igual, exista o e-mail ou não (não permite descobrir quem tem conta)."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.status == "active" and user.password_hash:
        raw = secrets.token_urlsafe(32)
        db.add(PasswordReset(user_id=user.id, token_hash=hash_token(raw),
                             expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
        db.commit()
        send_password_reset(user.email, raw)
        audit(db, action="auth.forgot", actor_id=user.id, ip=client_ip(request))
    return {"detail": "Se o e-mail existir, enviaremos as instruções."}


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=200)


@router.post("/reset", dependencies=[Depends(_auth_limit)])
def reset(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    err = validate_password_strength(body.password)
    if err:
        raise HTTPException(422, err)
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_token(body.token)))
    now = datetime.now(timezone.utc)
    if not pr or pr.used_at or pr.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(400, "Link inválido ou expirado.")
    user = db.get(User, pr.user_id)
    user.password_hash = hash_password(body.password)
    user.failed_logins, user.locked_until = 0, None
    user.email_verified_at = user.email_verified_at or now   # quem redefine pelo link do e-mail provou ser dono dele
    pr.used_at = now
    for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == user.id)):
        t.revoked = True  # derruba todas as sessões antigas
    db.commit()
    audit(db, action="auth.password_reset", actor_id=user.id, ip=client_ip(request))
    return {"ok": True}


# ---------------- Confirmação de e-mail ----------------
class VerifyIn(BaseModel):
    token: str = Field(max_length=200)


@router.post("/verify-email", dependencies=[Depends(_auth_limit)])
def verify_email(body: VerifyIn, request: Request, db: Session = Depends(get_db)):
    """Ativa a conta com o token do e-mail (uso único, expira). O token só existe no link enviado ao dono do e-mail."""
    ev = db.scalar(select(EmailVerification).where(EmailVerification.token_hash == hash_token(body.token)))
    now = datetime.now(timezone.utc)
    if not ev or ev.used_at or ev.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(400, "Link inválido ou expirado. Peça um novo e-mail de confirmação.")
    user = db.get(User, ev.user_id)
    user.email_verified_at = user.email_verified_at or now
    ev.used_at = now
    db.commit()
    audit(db, action="auth.email_verified", actor_id=user.id, ip=client_ip(request))
    return {"ok": True}


class ResendIn(BaseModel):
    email: str = Field(min_length=3, max_length=254)


RESEND_COOLDOWN_S = 60


@router.post("/resend-verification", status_code=202, dependencies=[Depends(rate_limit("resendverify", 5))])
def resend_verification(body: ResendIn, request: Request, db: Session = Depends(get_db)):
    """Reenvia o e-mail de confirmação. Resposta SEMPRE igual (não revela se o e-mail tem conta); no máx. 1 envio por minuto."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user and user.status == "active" and not user.email_verified_at and settings.email_verification_required:
        last = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id).order_by(EmailVerification.created_at.desc()))
        recent = last and (datetime.now(timezone.utc) - last.created_at.replace(tzinfo=timezone.utc)).total_seconds() < RESEND_COOLDOWN_S
        if not recent:
            _new_verification(db, user)
            audit(db, action="auth.verification_resent", actor_id=user.id, ip=client_ip(request))
    return {"detail": "Se a conta existir e ainda não estiver confirmada, enviamos um novo e-mail."}
