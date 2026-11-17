"""Dependências de autenticação/autorização (FastAPI).

PRINCÍPIO CENTRAL: o tenant NUNCA vem confiável do cliente. Ele é derivado das
memberships do usuário autenticado. O cabeçalho `X-Org-Slug` é só uma ESCOLHA entre
as organizações às quais o usuário já pertence; se não pertencer => 403.

Super admin: sem acesso automático a dados de tenants. Precisa de uma ELEVAÇÃO
auditada (POST /admin/elevate) com motivo; o token elevado é curto e SOMENTE LEITURA.
"""
from dataclasses import dataclass
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.ratelimit import client_ip
from .db import get_db, set_tenant_context
from .models import Membership, Role, Tenant, User
from .security import decode_token

_RANK = {Role.MEMBER: 1, Role.EVENT_OPERATOR: 2, Role.TENANT_ADMIN: 3}


@dataclass
class Ctx:
    user: User
    tenant_id: UUID | None
    role: Role | None
    elevated: bool  # super admin em modo suporte (somente leitura)
    ip: str

    def rank(self) -> int:
        return _RANK.get(self.role, 0) if self.role else 0


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Não autenticado.")
    return authorization.split(" ", 1)[1].strip()


def current_claims(authorization: str | None = Header(default=None)) -> dict:
    try:
        return decode_token(_bearer(authorization), "access")
    except jwt.PyJWTError:
        raise HTTPException(401, "Token inválido ou expirado.")


def current_user(claims: dict = Depends(current_claims), db: Session = Depends(get_db)) -> User:
    user = db.get(User, UUID(claims["sub"]))
    if not user or user.status != "active":
        raise HTTPException(401, "Usuário inativo.")
    return user


def get_ctx(
    request: Request,
    claims: dict = Depends(current_claims),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
    x_org_slug: str | None = Header(default=None),
) -> Ctx:
    """Resolve (usuário, tenant, papel) a partir das memberships — nunca de IDs enviados."""
    ip = client_ip(request)
    # 1) Modo suporte (super admin elevado): tenant vem do claim assinado, somente leitura.
    if claims.get("elev"):
        if not user.is_super_admin or not claims.get("mfa"):
            raise HTTPException(403, "Elevação inválida.")
        set_tenant_context(db, claims["elev"])
        return Ctx(user, UUID(claims["elev"]), Role.MEMBER, True, ip)
    # 2) Usuário comum: escolhe entre as próprias memberships.
    q = select(Membership).where(Membership.user_id == user.id)
    mems = db.scalars(q).all()
    if not mems:
        # Super admin sem membership: contexto global (sem tenant).
        return Ctx(user, None, None, False, ip)
    chosen = None
    if x_org_slug:
        tenant = db.scalar(select(Tenant).where(Tenant.slug == x_org_slug))
        chosen = next((m for m in mems if tenant and m.tenant_id == tenant.id), None)
        if not chosen:
            raise HTTPException(403, "Você não pertence a esta organização.")
    else:
        chosen = mems[0]
    tenant = db.get(Tenant, chosen.tenant_id)
    if tenant.status != "active":
        raise HTTPException(403, "Organização suspensa.")
    set_tenant_context(db, str(chosen.tenant_id))
    return Ctx(user, chosen.tenant_id, chosen.role, False, ip)


def require_role(min_role: Role):
    """Exige papel mínimo no tenant (e bloqueia modo suporte para escrita)."""
    def _dep(ctx: Ctx = Depends(get_ctx)) -> Ctx:
        if ctx.tenant_id is None or ctx.rank() < _RANK[min_role]:
            raise HTTPException(403, "Permissão insuficiente.")
        return ctx
    return _dep


require_member = require_role(Role.MEMBER)       # leitura (inclui modo suporte)
require_operator = require_role(Role.EVENT_OPERATOR)
require_admin = require_role(Role.TENANT_ADMIN)


def require_super(claims: dict = Depends(current_claims), user: User = Depends(current_user)) -> User:
    """Rotas /admin: super admin COM MFA verificado na sessão."""
    if not user.is_super_admin:
        raise HTTPException(403, "Apenas o super administrador.")
    if not claims.get("mfa"):
        raise HTTPException(403, "MFA obrigatório para o super administrador.")
    return user
