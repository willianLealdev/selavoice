"""Diretório PÚBLICO de igrejas/organizações (sem login): busca por nome e perfil com eventos.

Usado pelo site e pelos apps: o ouvinte pode (a) escanear o QR do evento, (b) escanear o QR do PERFIL da igreja,
ou (c) buscar a igreja pelo nome. Ouvintes nunca precisam de conta.

PRIVACIDADE: a busca só lista organizações que optaram por aparecer (`settings.listed`, padrão = sim) e que estão
ativas. O perfil por slug (QR da igreja) funciona mesmo se não listada, pois o QR é um compartilhamento explícito.
Só expõe: nome, tipo, logo e eventos AO VIVO/agendados — nunca e-mails, membros, uso ou eventos privados/encerrados.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.ratelimit import rate_limit
from ..core.timeutil import iso
from ..db import get_db
from ..models import Event, EventStatus, Tenant
from ..services.contact import social_links
from ..services.logo import logo_path

lang_router = APIRouter(prefix="/public", tags=["public"], dependencies=[Depends(rate_limit("publang", 60))])
router = APIRouter(prefix="/public/orgs", tags=["public"], dependencies=[Depends(rate_limit("pubdir", 60))])


@lang_router.get("/languages")
async def languages():
    """Idiomas de tradução disponíveis AGORA (vêm dos provedores configurados; nada fixo no código)."""
    from ..services.languages import available_languages
    return await available_languages()


def contact_out(t: Tenant) -> dict:
    """Contato público da organização (só o que ela preencheu) + links prontos das redes sociais."""
    c = (t.settings or {}).get("contact", {})
    return {**c, "links": social_links(c)}


def _org_out(t: Tenant) -> dict:
    b = t.branding or {}
    return {"slug": t.slug, "name": t.name, "type": t.type, "logo_url": b.get("logo_url", ""),
            "primary_color": b.get("primary_color", "")}


@router.get("")
def search_orgs(q: str = Query(min_length=2, max_length=60), db: Session = Depends(get_db)):
    """Busca por nome (parcial, sem diferenciar maiúsculas). Escapa % e _ para não virar curinga."""
    safe = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = db.scalars(select(Tenant).where(Tenant.status == "active", Tenant.name.ilike(f"%{safe}%", escape="\\"))
                      .order_by(Tenant.name).limit(50)).all()
    return [_org_out(t) for t in rows if (t.settings or {}).get("listed", True)][:20]


@router.get("/{slug}/logo")
def org_logo(slug: str, db: Session = Depends(get_db)):
    """Logo PÚBLICO da organização (sempre PNG já re-gravado pelo servidor). Cache longo: a URL muda a cada envio (?v=)."""
    t = db.scalar(select(Tenant).where(Tenant.slug == slug.lower()))
    if not t or t.status != "active":
        raise HTTPException(404)
    p = logo_path(str(t.id))
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png", headers={
        "Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff",
        "Cross-Origin-Resource-Policy": "cross-origin"})  # o site (outra porta/domínio) precisa poder exibir a imagem


@router.get("/{slug}")
def org_profile(slug: str, db: Session = Depends(get_db)):
    t = db.scalar(select(Tenant).where(Tenant.slug == slug.lower()))
    if not t or t.status != "active":
        raise HTTPException(404, "Organização não encontrada.")
    since = datetime.now(timezone.utc) - timedelta(hours=12)  # agendados que já passaram um pouco ainda aparecem
    evs = db.scalars(select(Event).where(
        Event.tenant_id == t.id, Event.status.in_([EventStatus.LIVE, EventStatus.SCHEDULED]), Event.starts_at >= since)
        .order_by(Event.status.desc(), Event.starts_at).limit(10)).all()
    live = [e for e in evs if e.status == EventStatus.LIVE]
    rest = [e for e in evs if e.status != EventStatus.LIVE]
    def _ev(e: Event) -> dict:
        return {"title": e.title, "type": e.type, "presenter": e.presenter, "theme": e.theme, "status": e.status.value,
                "starts_at": iso(e.starts_at), "join_code": e.join_code}

    # HISTÓRICO público: eventos ENCERRADOS (a organização pode desligar em Perfil -> "Mostrar histórico").
    # Só título/palestrante/data/código; a transcrição só é lida por quem abre o evento.
    history: list[dict] = []
    if (t.settings or {}).get("history_public", True):
        past = db.scalars(select(Event).where(Event.tenant_id == t.id, Event.status == EventStatus.ENDED)
                          .order_by(Event.starts_at.desc()).limit(40)).all()
        history = [_ev(e) for e in past]
    return {**_org_out(t), "contact": contact_out(t), "events": [_ev(e) for e in live + rest], "history": history}
