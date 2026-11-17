"""RELÓGIO DO EVENTO: conta as HORAS DE TRANSMISSÃO desde o momento em que o evento é INICIADO (status AO VIVO).

- Cada minuto inteiro transmitido vira um lançamento `event_minute` no livro-razão (append-only, idempotente por
  evento+minuto, então reiniciar o servidor ou rodar o relógio duas vezes não cobra em dobro) e abate do saldo
  de horas do direito (plano/compra) ao qual o evento está preso (`Event.entitlement_id`).
- Ao parar manualmente, o minuto parcial é arredondado PARA CIMA (`final=True`).
- Limites aplicados pelo relógio (ENCERRA o evento sozinho e avisa os ouvintes):
    * horas do plano esgotadas (saldo chegou a 0);
    * teto de duração de UM evento (`max_event_hours`).
- O relógio roda em segundo plano a cada `event_clock_seconds` (padrão 30 s). `tick()` é chamável nos testes.
"""
import asyncio
import logging
import math
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import SessionLocal
from ..models import Entitlement, Event, EventStatus, UsageEvent
from . import original_asr
from .channels import manager
from .plan_schema import limit, max_event_minutes
from .transcripts import hub

log = logging.getLogger("selavoice.clock")


def _aware(d: datetime) -> datetime:
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d


def event_entitlement(db: Session, ev: Event) -> Entitlement | None:
    return db.get(Entitlement, ev.entitlement_id) if ev.entitlement_id else None


def event_limits(db: Session, ev: Event) -> dict:
    """Limites do plano que este evento está usando ({} = sem plano registrado => sem limites extras)."""
    ent = event_entitlement(db, ev)
    return dict(ent.limits or {}) if ent else {}


def tenant_limits(db: Session, tenant_id) -> dict:
    """Limites 'atuais' da organização (direito ativo mais recente). {} se não houver."""
    ent = db.scalar(select(Entitlement).where(Entitlement.tenant_id == tenant_id, Entitlement.active.is_(True))
                    .order_by(Entitlement.created_at.desc()))
    return dict(ent.limits or {}) if ent else {}


def elapsed_minutes(ev: Event, now: datetime | None = None) -> float:
    if not ev.started_at:
        return 0.0
    end = _aware(ev.ended_at) if ev.ended_at else (now or datetime.now(timezone.utc))
    return max(0.0, (end - _aware(ev.started_at)).total_seconds() / 60)


def charged_minutes(db: Session, ev: Event) -> int:
    return int(db.scalar(select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
        UsageEvent.event_id == ev.id, UsageEvent.kind == "event_minute")) or 0)


def charge(db: Session, ev: Event, now: datetime | None = None, *, final: bool = False) -> int:
    """Lança os minutos de transmissão ainda não cobrados. Retorna quantos minutos foram lançados agora."""
    if not ev.started_at:
        return 0
    el = elapsed_minutes(ev, now)
    due = math.ceil(el) if final else math.floor(el)
    done = charged_minutes(db, ev)
    if due <= done:
        return 0
    for i in range(done, due):
        db.add(UsageEvent(tenant_id=ev.tenant_id, event_id=ev.id, language="", provider="clock", kind="event_minute",
                          quantity=1, provider_cost_micros=0, idempotency_key=f"evmin:{ev.id}:{i}"))
    ent = event_entitlement(db, ev)
    if ent is not None and ent.event_minutes_remaining is not None:
        ent.event_minutes_remaining = max(0, ent.event_minutes_remaining - (due - done))
    try:
        db.commit()
    except IntegrityError:  # outro processo lançou os mesmos minutos primeiro: tudo bem, não cobra em dobro
        db.rollback()
        return 0
    return due - done


def limit_reached(db: Session, ev: Event, now: datetime | None = None) -> str | None:
    """Motivo (texto para o ouvinte) se o evento deve ser encerrado agora; None se pode continuar."""
    ent = event_entitlement(db, ev)
    if ent is not None and ent.event_minutes_remaining is not None and ent.event_minutes_remaining <= 0:
        return "As horas de transmissão do plano acabaram."
    cap = max_event_minutes(event_limits(db, ev))
    if cap is not None and elapsed_minutes(ev, now) >= cap:
        return "O limite de duração deste evento foi atingido."
    return None


async def end_event(db: Session, ev: Event, reason: str) -> None:
    """Encerra o evento por limite do plano: avisa os ouvintes, fecha canais e registra na auditoria."""
    for (sid, lang) in list(manager.channels):
        if sid in {str(s.id) for s in ev.sessions}:
            hub.publish(sid, lang, {"type": "status", "state": "ended", "message": reason})
    ev.status, ev.ended_at = EventStatus.ENDED, datetime.now(timezone.utc)
    for s in ev.sessions:
        s.state = "ended"
        await manager.close_session(s.id)
        await original_asr.close(s.id)
    db.commit()
    audit(db, action="event.auto_stop", tenant_id=ev.tenant_id, target=str(ev.id), reason=reason)


async def tick() -> int:
    """Uma rodada do relógio: cobra minutos e encerra eventos que estouraram o plano. Retorna quantos encerrou."""
    ended = 0
    with SessionLocal() as db:
        for ev in db.scalars(select(Event).where(Event.status == EventStatus.LIVE)).all():
            charge(db, ev)
            reason = limit_reached(db, ev)
            if reason:
                await end_event(db, ev, reason)
                ended += 1
    return ended


async def run_forever(every: int) -> None:
    while True:
        await asyncio.sleep(every)
        try:
            await tick()
        except Exception:  # o relógio nunca pode morrer por um erro isolado
            log.exception("falha no relógio de eventos")
