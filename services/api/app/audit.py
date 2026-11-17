"""Registro de auditoria (quem fez o quê, quando, de onde e por quê)."""
from sqlalchemy.orm import Session
from .models import AuditLog


def audit(db: Session, *, action: str, actor_id=None, actor_role: str = "", tenant_id=None,
          target: str = "", reason: str = "", ip: str = "", meta: dict | None = None,
          commit: bool = True) -> AuditLog:
    row = AuditLog(action=action, actor_id=actor_id, actor_role=actor_role, tenant_id=tenant_id,
                   target=target[:200], reason=reason[:300], ip=ip, meta=meta or {})
    db.add(row)
    if commit:
        db.commit()
    return row
