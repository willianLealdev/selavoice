"""Ciclo de vida de eventos: criar, editar, agendar, cancelar, iniciar, encerrar, histórico.

REGRAS
- Criar/agendar NÃO ativa IA paga. Só `start` reserva cota e abre a sessão.
- Máquina de estados: SCHEDULED -> LIVE -> ENDED ; SCHEDULED -> CANCELED. Outras = 409.
- Toda consulta é filtrada pelo tenant da membership (`scoped`). Acesso a evento de outro
  tenant retorna 404 (não revela existência).
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..core.timeutil import iso
from ..db import get_db, scoped
from ..deps import Ctx, require_admin, require_member, require_operator
from ..models import Event, EventSession, EventStatus, Tenant
from ..security import create_ingest_token, gen_join_code, hash_password
from ..services.billing import QuotaError, reserve_event_start
from ..services import original_asr
from ..services.channels import manager
from ..services.event_clock import charge, charged_minutes, elapsed_minutes, event_entitlement, event_limits
from ..services.plan_schema import is_unlimited, limit as plan_limit, max_event_minutes

router = APIRouter(prefix="/events", tags=["events"])

TRANSITIONS = {
    EventStatus.SCHEDULED: {EventStatus.LIVE, EventStatus.CANCELED},
    EventStatus.LIVE: {EventStatus.ENDED},
    EventStatus.ENDED: set(),
    EventStatus.CANCELED: set(),
}


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: str = Field(default="service", pattern="^(service|conference|expo|fair|lecture|training|meeting|other)$")
    description: str = Field(default="", max_length=5000)
    starts_at: datetime
    timezone: str = Field(default="America/Los_Angeles", max_length=60)
    original_language: str = Field(default="pt", max_length=10)
    presenter: str = Field(default="", max_length=160)
    theme: str = Field(default="", max_length=200)
    scripture: str = Field(default="", max_length=200)
    recording_policy: str = Field(default="none", pattern="^(none|transcript_only|audio_and_transcript)$")
    rooms: list[str] = Field(default_factory=lambda: ["main"], max_length=20)
    private: bool = False                                   # evento privado: o ouvinte precisa da senha para entrar
    access_password: str | None = Field(default=None, min_length=4, max_length=60)


class EventUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    starts_at: datetime | None = None
    presenter: str | None = None
    theme: str | None = None
    scripture: str | None = None
    recording_policy: str | None = Field(default=None, pattern="^(none|transcript_only|audio_and_transcript)$")


def out(e: Event) -> dict:
    return {"id": str(e.id), "title": e.title, "type": e.type, "description": e.description,
            "starts_at": iso(e.starts_at), "timezone": e.timezone, "original_language": e.original_language,
            "status": e.status.value, "presenter": e.presenter, "theme": e.theme, "scripture": e.scripture,
            "recording_policy": e.recording_policy, "join_code": e.join_code, "private": bool(e.access_password_hash),
            "join_url": f"/e/{e.join_code}",
            "sessions": [{"id": str(s.id), "room": s.room, "state": s.state} for s in e.sessions]}


def get_event_or_404(db: Session, ctx: Ctx, event_id: UUID) -> Event:
    ev = db.scalar(scoped(db, Event, ctx.tenant_id).where(Event.id == event_id))
    if not ev:
        raise HTTPException(404, "Evento não encontrado.")
    return ev


@router.post("", status_code=201)
def create_event(body: EventIn, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    if body.private and not body.access_password:
        raise HTTPException(422, "Evento privado precisa de uma senha (mínimo 4 caracteres).")
    ev = Event(tenant_id=ctx.tenant_id, title=body.title, type=body.type, description=body.description,
               starts_at=body.starts_at, timezone=body.timezone, original_language=body.original_language,
               presenter=body.presenter, theme=body.theme, scripture=body.scripture,
               recording_policy=body.recording_policy, join_code=gen_join_code(),
               access_password_hash=hash_password(body.access_password) if body.private and body.access_password else None)
    ev.sessions = [EventSession(tenant_id=ctx.tenant_id, room=r) for r in body.rooms]
    db.add(ev)
    db.commit()
    audit(db, action="event.create", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(ev.id), ip=ctx.ip)
    return out(ev)


@router.get("")
def list_events(ctx: Ctx = Depends(require_member), db: Session = Depends(get_db),
                q: str | None = None, status: EventStatus | None = None, type: str | None = None,
                presenter: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
                limit: int = Query(50, le=200), offset: int = 0):
    """Histórico pesquisável por data/título/palestrante/tipo (somente do tenant)."""
    stmt = scoped(db, Event, ctx.tenant_id)
    if q:
        stmt = stmt.where(Event.title.ilike(f"%{q}%"))
    if status:
        stmt = stmt.where(Event.status == status)
    if type:
        stmt = stmt.where(Event.type == type)
    if presenter:
        stmt = stmt.where(Event.presenter.ilike(f"%{presenter}%"))
    if date_from:
        stmt = stmt.where(Event.starts_at >= date_from)
    if date_to:
        stmt = stmt.where(Event.starts_at <= date_to)
    rows = db.scalars(stmt.order_by(Event.starts_at.desc()).limit(limit).offset(offset)).all()
    return [out(e) for e in rows]


@router.get("/{event_id}")
def get_event(event_id: UUID, ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    return out(get_event_or_404(db, ctx, event_id))


@router.patch("/{event_id}")
def update_event(event_id: UUID, body: EventUpdate, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    ev = get_event_or_404(db, ctx, event_id)
    if ev.status != EventStatus.SCHEDULED:
        raise HTTPException(409, "Só eventos agendados podem ser editados.")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ev, k, v)
    db.commit()
    audit(db, action="event.update", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(ev.id), ip=ctx.ip)
    return out(ev)


def _transition(ev: Event, to: EventStatus) -> None:
    if to not in TRANSITIONS[ev.status]:
        raise HTTPException(409, f"Transição inválida: {ev.status.value} -> {to.value}.")


@router.post("/{event_id}/cancel")
def cancel_event(event_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    ev = get_event_or_404(db, ctx, event_id)
    _transition(ev, EventStatus.CANCELED)
    ev.status = EventStatus.CANCELED
    db.commit()
    audit(db, action="event.cancel", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(ev.id), ip=ctx.ip)
    return out(ev)


@router.post("/{event_id}/start")
def start_event(event_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    """Inicia o evento: reserva cota (atômica) e abre as sessões. É aqui que o consumo começa."""
    ev = get_event_or_404(db, ctx, event_id)
    _transition(ev, EventStatus.LIVE)
    try:
        ent = reserve_event_start(db, ctx.tenant_id)
    except QuotaError as e:
        db.rollback()
        raise HTTPException(402 if e.code == "no_entitlement" else 409, e.msg)
    if ev.recording_policy != "none" and plan_limit(ent.limits, "recordings", True) is False:
        db.rollback()
        raise HTTPException(409, "Seu plano não inclui gravação. Escolha \"Não gravar\" ou mude de plano.")
    ev.entitlement_id = ent.id  # daqui saem os limites deste evento (horas, ouvintes, idiomas...)
    ev.status, ev.started_at = EventStatus.LIVE, datetime.now(timezone.utc)  # AQUI começa a contar as horas
    for s in ev.sessions:
        s.state = "live"
    db.commit()
    audit(db, action="event.start", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(ev.id), ip=ctx.ip)
    return out(ev)


@router.post("/{event_id}/stop")
async def stop_event(event_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    ev = get_event_or_404(db, ctx, event_id)
    _transition(ev, EventStatus.ENDED)
    ev.status, ev.ended_at = EventStatus.ENDED, datetime.now(timezone.utc)
    charge(db, ev, final=True)  # fecha a conta de horas (minuto parcial arredonda para cima)
    for s in ev.sessions:
        s.state = "ended"
        await manager.close_session(s.id)  # fecha canais e lança o consumo final
        await original_asr.close(s.id)
    db.commit()
    audit(db, action="event.stop", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(ev.id), ip=ctx.ip)
    return out(ev)


@router.get("/{event_id}/usage")
def event_usage(event_id: UUID, ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    """Horas de transmissão deste evento (começam a contar no INÍCIO da transmissão) e limites do plano."""
    ev = get_event_or_404(db, ctx, event_id)
    ent = event_entitlement(db, ev)
    lim = event_limits(db, ev)
    rem = ent.event_minutes_remaining if ent else None
    cap = max_event_minutes(lim)
    el = elapsed_minutes(ev)
    return {"status": ev.status.value, "started_at": iso(ev.started_at) if ev.started_at else None,
            "elapsed_minutes": round(el, 1), "charged_minutes": charged_minutes(db, ev),
            "plan_minutes_remaining": None if rem is None or is_unlimited(rem) else int(rem),
            "event_cap_minutes": cap, "event_minutes_left": None if cap is None else max(0, round(cap - el, 1)),
            "listener_concurrency": plan_limit(lim, "listener_concurrency", None),
            "max_languages": plan_limit(lim, "max_languages", None),
            "allowed_languages": lim.get("allowed_languages", [])}


@router.get("/{event_id}/history")
def event_history(event_id: UUID, ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    """Resumo pós-evento: idiomas com transcrição e quantidade de segmentos finais."""
    from sqlalchemy import func
    from ..models import TranscriptSegment
    ev = get_event_or_404(db, ctx, event_id)
    sids = [s.id for s in ev.sessions]
    rows = db.execute(select(TranscriptSegment.language, func.count()).where(
        TranscriptSegment.tenant_id == ctx.tenant_id, TranscriptSegment.session_id.in_(sids),
        TranscriptSegment.is_final.is_(True)).group_by(TranscriptSegment.language)).all()
    return {"event": out(ev), "languages": [{"language": l, "final_segments": n} for l, n in rows]}


@router.get("/sessions/{session_id}/audio-token")
def audio_token(session_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    """Token efêmero para o utilitário de captura (X32/navegador) enviar áudio desta sessão."""
    s = db.scalar(scoped(db, EventSession, ctx.tenant_id).where(EventSession.id == session_id))
    if not s:
        raise HTTPException(404, "Sessão não encontrada.")
    audit(db, action="session.audio_token", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(s.id), ip=ctx.ip)
    return {"token": create_ingest_token(str(s.id), str(ctx.tenant_id)), "expires_minutes": 240}
