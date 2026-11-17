"""Configurações DA PLATAFORMA editáveis pelo Super Admin (guardadas no banco, não no código).

Hoje: o TESTE GRÁTIS que toda organização nova recebe ao criar a conta. O dono decide TUDO no painel:
  enabled  liga/desliga o teste (desligado = conta nova não recebe nada e precisa contratar um plano)
  days     validade do teste em dias (None = não expira)
  limits   os MESMOS limites de um plano (horas, pessoas, idiomas, eventos, equipe, recursos...) — ver plan_schema.py
Valem para as contas criadas DEPOIS da mudança; quem já recebeu o teste continua com o que recebeu.
A landing e o cadastro leem a configuração pela API pública (/public/trial) e mostram exatamente o que está aqui.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PlatformSetting
from .plan_schema import PlanError, normalize

TRIAL_KEY = "trial"

# Valor INICIAL (antes de o dono mexer no painel). É só ponto de partida, não uma promessa de produto.
DEFAULT_TRIAL = {
    "enabled": True,
    "days": None,
    "limits": {"included_events": 1, "included_hours": 1, "max_event_hours": 1, "included_language_minutes": 60,
               "max_languages": 2, "listener_concurrency": 25, "max_concurrent_events": 1, "admin_seats": 2,
               "recordings": False, "pdf_booklets": True, "overage": "hard_stop"},
}


def get_trial(db: Session) -> dict:
    row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == TRIAL_KEY))
    raw = dict(row.value) if row and row.value else {}
    limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else DEFAULT_TRIAL["limits"]
    try:
        limits = normalize(limits)   # defesa: nunca devolve lixo mesmo que o banco tenha sido editado à mão
    except PlanError:
        limits = dict(DEFAULT_TRIAL["limits"])
    days = raw.get("days", DEFAULT_TRIAL["days"])
    return {"enabled": bool(raw.get("enabled", DEFAULT_TRIAL["enabled"])), "days": int(days) if days else None, "limits": limits}


def set_trial(db: Session, *, enabled: bool, days: int | None, limits: dict) -> dict:
    """Valida (PlanError se inválido) e grava. Retorna a configuração efetiva."""
    clean = normalize(limits)
    value = {"enabled": bool(enabled), "days": int(days) if days else None, "limits": clean}
    row = db.scalar(select(PlatformSetting).where(PlatformSetting.key == TRIAL_KEY))
    if row is None:
        db.add(PlatformSetting(key=TRIAL_KEY, value=value))
    else:
        row.value = value   # reatribui o dict para o SQLAlchemy detectar a mudança
    db.commit()
    return get_trial(db)
