"""APOSTILA AUTOMÁTICA: quando o evento termina, a DeepSeek lê a transcrição e a apostila é criada e PUBLICADA sozinha.

Sem fila de revisão e sem aprovação humana (decisão do dono). A organização continua podendo editar, despublicar ou excluir
a apostila na tela do evento. Proteções: só entram citações/referências que existem na fala (filtro em editorial.py) e o PDF
traz, no fim, o aviso de que foi gerado automaticamente com apoio de IA.

Quando NÃO gera (e por quê):
  - a organização desligou (Perfil > "Gerar apostila automaticamente");
  - o plano não inclui apostilas (limite `pdf_booklets`);
  - já existe apostila automática deste evento (evita duplicar se o evento for encerrado duas vezes);
  - quase não houve fala (menos de MIN_CHARS caracteres);
  - o idioma da fala ainda não é suportado no PDF (russo, árabe, hindi…).
"""
import asyncio
import logging
import time
from collections import Counter
from uuid import UUID

from sqlalchemy import select

from ..audit import audit
from ..db import SessionLocal
from ..models import DocStatus, Document, Event, Tenant, TranscriptSegment
from .editorial import STORAGE, book_supported, build_auto_content, fmt_date, render_book
from .event_clock import tenant_limits
from .plan_schema import limit as plan_limit

log = logging.getLogger("selavoice.book")
MIN_CHARS = 300          # menos que isso não vira apostila (ninguém falou de verdade)
DELAY_S = 3.0            # espera os últimos trechos da fala serem gravados antes de ler a transcrição
_tasks: set = set()      # guarda as tarefas em segundo plano (senão o Python pode descartá-las no meio)


def auto_enabled(settings: dict | None) -> bool:
    return bool((settings or {}).get("auto_booklet", True))


def _source_segments(db, ev: Event):
    """Transcrição original; se não houve (sem reconhecimento da fala original), usa o idioma traduzido com mais texto."""
    sid = ev.sessions[0].id
    base = select(TranscriptSegment).where(TranscriptSegment.tenant_id == ev.tenant_id, TranscriptSegment.session_id == sid,
                                           TranscriptSegment.is_final.is_(True)).order_by(TranscriptSegment.seq)
    orig = db.scalars(base.where(TranscriptSegment.kind == "original")).all()
    if orig:
        return orig, ev.original_language
    tr = db.scalars(base.where(TranscriptSegment.kind == "translated")).all()
    if not tr:
        return [], ev.original_language
    top: Counter = Counter()
    for s in tr:
        top[s.language] += len(s.text or "")
    lang = top.most_common(1)[0][0]
    return [s for s in tr if s.language == lang], lang


def run_sync(event_id: UUID, *, force: bool = False) -> str:
    """Gera e publica a apostila do evento. Devolve um código do resultado (usado nos testes e no registro)."""
    time.sleep(DELAY_S)
    with SessionLocal() as db:
        ev = db.get(Event, event_id)
        if not ev or not ev.sessions:
            return "no_event"
        t = db.get(Tenant, ev.tenant_id)
        if not force and not auto_enabled(t.settings):
            return "disabled"
        if plan_limit(tenant_limits(db, ev.tenant_id), "pdf_booklets", True) is False:
            return "not_in_plan"
        if not force and any((d.content or {}).get("auto") for d in db.scalars(select(Document).where(Document.event_id == ev.id))):
            return "exists"
        segs, lang = _source_segments(db, ev)
        paragraphs = [s.text.strip() for s in segs if (s.text or "").strip()]
        if sum(len(p) for p in paragraphs) < MIN_CHARS:
            return "no_transcript"
        if not book_supported(lang):
            log.info("apostila automática: idioma %s ainda não suportado no PDF (evento %s)", lang, ev.id)
            return "unsupported_language"
        subtitle = " · ".join(x for x in (ev.presenter, ev.theme) if x)
        content = build_auto_content(paragraphs, lang, ev.title, ev.presenter, ev.theme)
        d = Document(tenant_id=ev.tenant_id, event_id=ev.id, language=lang, title=f"{ev.title} — Apostila", status=DocStatus.PUBLISHED,
                     content=content, flags=[])
        db.add(d)
        db.flush()
        d.pdf_key = render_book(str(d.id), str(ev.tenant_id), d.title, subtitle, t.name, content,
                                primary_color=(t.branding or {}).get("primary_color", "#0B63CE"), lang=lang,
                                date_str=fmt_date(ev.starts_at, lang), auto_note=True)
        db.commit()
        audit(db, action="doc.auto_publish", tenant_id=ev.tenant_id, target=str(d.id),
              meta={"event": str(ev.id), "fallback": bool(content.get("fallback")), "lang": lang})
        return "published_fallback" if content.get("fallback") else "published"


def schedule(event_id: UUID) -> None:
    """Dispara a geração em segundo plano a partir de código assíncrono (ex.: encerramento automático pelo relógio)."""
    async def _go():
        try:
            log.info("apostila automática: %s", await asyncio.to_thread(run_sync, event_id))
        except Exception:
            log.exception("falha ao gerar a apostila automática")
    t = asyncio.get_event_loop().create_task(_go())
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def run_safe(event_id: UUID) -> None:
    """Versão para BackgroundTasks do FastAPI (função comum, roda em thread): nunca deixa a exceção subir."""
    try:
        log.info("apostila automática: %s", run_sync(event_id))
    except Exception:
        log.exception("falha ao gerar a apostila automática")
