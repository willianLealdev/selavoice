"""Transcrição ao vivo ACUMULADA: armazenamento + hub de distribuição em tempo real.

Garantias:
- `seq` monotônico por (sessão, idioma); (sessão, idioma, seq) é UNIQUE no banco.
- Provisórios: mesmo seq, `revision` crescente. Ao finalizar (`is_final`), o texto é IMUTÁVEL.
- Replay: cliente informa `last_seq` e recebe tudo que perdeu (finais + provisório mais recente).
- Hub em memória (1 processo). Para várias réplicas: trocar por Redis pub/sub (ADR-006).
"""
import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import TranscriptSegment

_locks: dict[tuple, asyncio.Lock] = defaultdict(asyncio.Lock)


def seg_to_dict(s: TranscriptSegment) -> dict:
    return {"seq": s.seq, "rev": s.revision, "final": s.is_final, "lang": s.language, "text": s.text,
            "start_ms": s.start_ms, "end_ms": s.end_ms, "provider": s.provider, "kind": s.kind}


class Hub:
    """Pub/sub por (sessão, idioma). Filas limitadas: ouvinte lento é desconectado e re-sincroniza."""

    def __init__(self) -> None:
        self._subs: dict[tuple, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, sid: str, lang: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[(sid, lang)].add(q)
        return q

    def unsubscribe(self, sid: str, lang: str, q: asyncio.Queue) -> None:
        self._subs[(sid, lang)].discard(q)

    def publish(self, sid: str, lang: str, msg: dict) -> None:
        for q in list(self._subs[(sid, lang)]):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                q.put_nowait({"type": "resync"}) if q.empty() else None  # cliente pede replay

    def count(self, sid: str, lang: str) -> int:
        return len(self._subs[(sid, lang)])


hub = Hub()


async def write_segment(tenant_id, session_id, lang: str, text: str, *, is_final: bool, seq: int | None = None,
                        start_ms: int = 0, end_ms: int = 0, provider: str = "mock",
                        kind: str = "translated", publish: bool = True) -> dict | None:
    """Cria (seq=None) ou revisa um segmento e o publica no hub. Retorna o dict publicado,
    ou None se tentou alterar segmento já FINAL (rejeitado)."""
    session_id = UUID(str(session_id))  # aceita str ou UUID
    tenant_id = UUID(str(tenant_id))
    async with _locks[(str(session_id), lang, kind)]:
        with SessionLocal() as db:
            if seq is None:
                cur = db.scalar(select(func.max(TranscriptSegment.seq)).where(
                    TranscriptSegment.session_id == session_id, TranscriptSegment.language == lang,
                    TranscriptSegment.kind == kind))
                seq = (cur or 0) + 1
                row = TranscriptSegment(tenant_id=tenant_id, session_id=session_id, language=lang, seq=seq,
                                        revision=0, is_final=is_final, text=text, start_ms=start_ms,
                                        end_ms=end_ms, provider=provider, kind=kind)
                db.add(row)
            else:
                row = db.scalar(select(TranscriptSegment).where(
                    TranscriptSegment.session_id == session_id, TranscriptSegment.language == lang,
                    TranscriptSegment.seq == seq, TranscriptSegment.kind == kind))
                if row is None or row.is_final:
                    return None  # final é imutável
                row.revision += 1
                row.text, row.is_final = text, is_final
                row.start_ms, row.end_ms = start_ms or row.start_ms, end_ms or row.end_ms
            db.commit()
            out = seg_to_dict(row)
    if publish:  # o texto ORIGINAL não vai aos ouvintes (serve à equipe e ao documento pós-evento)
        hub.publish(str(session_id), lang, {"type": "segment", **out})
    return out


def fetch_since(db: Session, session_id, lang: str, last_seq: int, kind: str = "translated") -> list[dict]:
    """Replay: tudo com seq > last_seq (ordenado)."""
    rows = db.scalars(select(TranscriptSegment).where(
        TranscriptSegment.session_id == session_id, TranscriptSegment.language == lang,
        TranscriptSegment.kind == kind, TranscriptSegment.seq > last_seq).order_by(TranscriptSegment.seq)).all()
    return [seg_to_dict(r) for r in rows]


def fetch_page(db: Session, session_id, lang: str, before_seq: int | None, limit: int = 50,
               kind: str = "translated") -> list[dict]:
    """Scrollback: página dos `limit` segmentos anteriores a `before_seq` (ordem crescente)."""
    q = select(TranscriptSegment).where(TranscriptSegment.session_id == session_id,
                                        TranscriptSegment.language == lang, TranscriptSegment.kind == kind)
    if before_seq:
        q = q.where(TranscriptSegment.seq < before_seq)
    rows = db.scalars(q.order_by(TranscriptSegment.seq.desc()).limit(min(limit, 200))).all()
    return [seg_to_dict(r) for r in reversed(rows)]
