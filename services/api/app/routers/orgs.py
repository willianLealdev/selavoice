"""Organização (perfil/branding), membros e convites. Escopo: SEMPRE o tenant da membership."""
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db, scoped
from ..deps import Ctx, require_admin, require_member
from ..models import Invitation, Membership, Role, Tenant, User
from ..services.email import send_invite
from ..services.event_clock import tenant_limits
from ..services.plan_schema import limit as plan_limit
from ..services.audio_gate import clean_audio, get_audio
from ..services.contact import ContactError, clean_contact
from ..services.logo import LogoError, logo_path, process_logo
from ..security import hash_password, hash_token, validate_password_strength

router = APIRouter(tags=["organization"])


@router.get("/organizations/me")
def my_org(ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    t = db.get(Tenant, ctx.tenant_id)
    return {"id": str(t.id), "name": t.name, "slug": t.slug, "type": t.type, "locale": t.locale,
            "timezone": t.timezone, "branding": t.branding, "role": ctx.role.value,
            "listed": (t.settings or {}).get("listed", True),
            "history_public": (t.settings or {}).get("history_public", True),
            "contact": (t.settings or {}).get("contact", {}), "audio": get_audio(t.settings)}


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    locale: str | None = Field(default=None, max_length=10)
    timezone: str | None = Field(default=None, max_length=60)
    branding: dict | None = None  # {"logo_url","primary_color"}
    audio: dict | None = None     # filtro de voz / ruído / só idioma do evento
    contact: dict | None = None   # endereço, site, redes sociais (públicos)
    history_public: bool | None = None   # mostrar o histórico de eventos encerrados no perfil público
    listed: bool | None = None    # aparecer na busca pública de igrejas


@router.patch("/organizations/me")
def update_org(body: OrgUpdate, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(Tenant, ctx.tenant_id)
    data = body.model_dump(exclude_none=True)
    if "branding" in data:  # só chaves permitidas, valores curtos (evita lixo/XSS armazenado)
        allowed = {"primary_color"}  # logo_url só é definido pelo servidor (upload)
        data["branding"] = {k: str(v)[:300] for k, v in data["branding"].items() if k in allowed}
    if "audio" in data:
        try:
            a = clean_audio(data.pop("audio"))
        except ValueError as e:
            raise HTTPException(422, str(e))
        t.settings = {**(t.settings or {}), "audio": {**get_audio(t.settings), **a}}
    if "contact" in data:
        try:
            c = clean_contact(data.pop("contact"))
        except ContactError as e:
            raise HTTPException(422, str(e))
        t.settings = {**(t.settings or {}), "contact": c}
    if "history_public" in data:
        t.settings = {**(t.settings or {}), "history_public": bool(data.pop("history_public"))}
    if "listed" in data:  # vai para settings (JSON); reatribui o dict para o SQLAlchemy detectar a mudança
        t.settings = {**(t.settings or {}), "listed": bool(data.pop("listed"))}
    if "branding" in data:  # mescla preservando o logo que o servidor definiu
        data["branding"] = {**(t.branding or {}), **data["branding"]}
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    audit(db, action="org.update", actor_id=ctx.user.id, tenant_id=t.id, ip=ctx.ip)
    return {"ok": True}


@router.post("/organizations/me/logo")
async def upload_logo(file: UploadFile = File(...), ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    """Envia o logo da organização (aparece para todo o público). Só administrador.
    SEGURANÇA: lê no máximo 2 MB; o arquivo é DECODIFICADO e RE-GRAVADO como PNG (descarta metadados e qualquer
    conteúdo escondido); SVG é recusado (pode carregar script). O arquivo fica em pasta do próprio tenant."""
    raw = await file.read(2 * 1024 * 1024 + 1)
    try:
        png = process_logo(raw)
    except LogoError as e:
        raise HTTPException(422, str(e))
    path = logo_path(str(ctx.tenant_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    t = db.get(Tenant, ctx.tenant_id)
    # ?v= muda a cada envio para os navegadores não ficarem com o logo antigo em cache
    t.branding = {**(t.branding or {}), "logo_url": f"/public/orgs/{t.slug}/logo?v={int(datetime.now(timezone.utc).timestamp())}"}
    db.commit()
    audit(db, action="org.logo_upload", actor_id=ctx.user.id, tenant_id=t.id, ip=ctx.ip)
    return {"logo_url": t.branding["logo_url"]}


@router.delete("/organizations/me/logo")
def delete_logo(ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    t = db.get(Tenant, ctx.tenant_id)
    logo_path(str(ctx.tenant_id)).unlink(missing_ok=True)
    t.branding = {k: v for k, v in (t.branding or {}).items() if k != "logo_url"}
    db.commit()
    audit(db, action="org.logo_delete", actor_id=ctx.user.id, tenant_id=t.id, ip=ctx.ip)
    return {"ok": True}


@router.get("/organizations/me/members")
def members(ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.execute(select(Membership, User).join(User, User.id == Membership.user_id)
                      .where(Membership.tenant_id == ctx.tenant_id)).all()
    return [{"user_id": str(u.id), "email": u.email, "name": u.name, "role": m.role.value} for m, u in rows]


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER
    lang: str = Field(default="pt", pattern="^(pt|en|es)$")   # idioma do e-mail (o mesmo da interface)


@router.post("/organizations/me/invitations", status_code=201)
def invite(body: InviteIn, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    """Cria convite e ENVIA por e-mail (Resend). Se o e-mail não estiver configurado, devolve o token UMA vez
    para o admin repassar manualmente. Quando enviado por e-mail, o token NÃO é devolvido."""
    seats = plan_limit(tenant_limits(db, ctx.tenant_id), "admin_seats", None)  # None = ilimitado
    if seats is not None:
        used = (db.scalar(select(func.count()).select_from(Membership).where(Membership.tenant_id == ctx.tenant_id)) or 0) + \
               (db.scalar(select(func.count()).select_from(Invitation).where(
                   Invitation.tenant_id == ctx.tenant_id, Invitation.accepted_at.is_(None),
                   Invitation.expires_at > datetime.now(timezone.utc))) or 0)
        if used >= int(seats):
            raise HTTPException(409, f"Seu plano permite {seats} pessoa(s) na equipe. Mude de plano para convidar mais.")
    raw = secrets.token_urlsafe(32)
    db.add(Invitation(tenant_id=ctx.tenant_id, email=body.email.lower(), role=body.role, token_hash=hash_token(raw),
                      expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
    db.commit()
    audit(db, action="org.invite", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=body.email, ip=ctx.ip)
    org = db.get(Tenant, ctx.tenant_id)
    emailed = send_invite(body.email.lower(), org.name, raw, body.lang)
    return {"emailed": emailed, "invite_token": None if emailed else raw, "expires_days": 7}


class AcceptIn(BaseModel):
    token: str
    name: str = Field(max_length=160)
    password: str = Field(max_length=200)


@router.post("/invitations/accept", status_code=201)
def accept(body: AcceptIn, db: Session = Depends(get_db)):
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(body.token)))
    now = datetime.now(timezone.utc)
    if not inv or inv.accepted_at or inv.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(400, "Convite inválido ou expirado.")
    user = db.scalar(select(User).where(User.email == inv.email))
    if not user:
        err = validate_password_strength(body.password)
        if err:
            raise HTTPException(422, err)
        user = User(email=inv.email, name=body.name, password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    user.email_verified_at = user.email_verified_at or now   # o convite foi enviado ao e-mail dele: provou ser o dono
    db.add(Membership(user_id=user.id, tenant_id=inv.tenant_id, role=inv.role))
    inv.accepted_at = now
    db.commit()
    return {"ok": True}


class RoleIn(BaseModel):
    role: Role


@router.patch("/organizations/me/members/{user_id}")
def set_role(user_id: UUID, body: RoleIn, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    m = db.scalar(scoped(db, Membership, ctx.tenant_id).where(Membership.user_id == user_id))
    if not m:
        raise HTTPException(404)
    if m.role == Role.TENANT_ADMIN and body.role != Role.TENANT_ADMIN:
        admins = db.scalar(select(func.count()).select_from(Membership).where(
            Membership.tenant_id == ctx.tenant_id, Membership.role == Role.TENANT_ADMIN))
        if admins <= 1:
            raise HTTPException(409, "A organização precisa de pelo menos um administrador.")
    m.role = body.role
    db.commit()
    audit(db, action="org.role_change", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(user_id), ip=ctx.ip)
    return {"ok": True}
