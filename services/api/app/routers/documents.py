"""Apostilas/relatórios: rascunho -> revisão -> aprovação humana -> PDF -> publicação.

- Documento NÃO publicado é inacessível para ouvintes (só membros do tenant).
- Aprovar exige que todas as referências bíblicas sinalizadas tenham sido revisadas.
- O PDF é servido por rota autenticada (nunca expõe caminho do disco; prefixo por tenant verificado).
"""
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db, scoped
from ..deps import Ctx, require_admin, require_member, require_operator
from ..models import DocStatus, Document, Event, PublicationApproval, Tenant, TranscriptSegment
from ..services.event_clock import tenant_limits
from ..services.plan_schema import limit as plan_limit
from ..services.editorial import STORAGE, build_draft, detect_references, render_pdf

router = APIRouter(prefix="/documents", tags=["documents"])


def dout(d: Document) -> dict:
    return {"id": str(d.id), "event_id": str(d.event_id), "title": d.title, "language": d.language,
            "status": d.status.value, "content": d.content, "flags": d.flags, "version": d.version}


def _get(db: Session, ctx: Ctx, doc_id: UUID) -> Document:
    d = db.scalar(scoped(db, Document, ctx.tenant_id).where(Document.id == doc_id))
    if not d:
        raise HTTPException(404, "Documento não encontrado.")
    return d


class OriginalIn(BaseModel):
    paragraphs: list[str] = Field(min_length=1, max_length=5000)


@router.post("/events/{event_id}/original-transcript", status_code=201)
def import_original(event_id: UUID, body: OriginalIn, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    """Importa/cola a transcrição ORIGINAL (saída do faster-whisper/Deepgram ou texto revisado).
    Cada parágrafo vira um segmento FINAL imutável (kind=original)."""
    ev = db.scalar(scoped(db, Event, ctx.tenant_id).where(Event.id == event_id))
    if not ev or not ev.sessions:
        raise HTTPException(404)
    sid = ev.sessions[0].id
    for i, p in enumerate(body.paragraphs, 1):
        db.add(TranscriptSegment(tenant_id=ctx.tenant_id, session_id=sid, language=ev.original_language, seq=i,
                                 is_final=True, kind="original", text=p[:5000], provider="import"))
    db.commit()
    return {"imported": len(body.paragraphs)}


@router.post("/events/{event_id}/generate", status_code=201)
def generate(event_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    ev = db.scalar(scoped(db, Event, ctx.tenant_id).where(Event.id == event_id))
    if not ev or not ev.sessions:
        raise HTTPException(404)
    if plan_limit(tenant_limits(db, ctx.tenant_id), "pdf_booklets", True) is False:
        raise HTTPException(403, "Seu plano não inclui o documento pós-evento.")
    segs = db.scalars(select(TranscriptSegment).where(
        TranscriptSegment.tenant_id == ctx.tenant_id, TranscriptSegment.session_id == ev.sessions[0].id,
        TranscriptSegment.kind == "original", TranscriptSegment.is_final.is_(True))
        .order_by(TranscriptSegment.seq)).all()
    if not segs:
        raise HTTPException(409, "Não há transcrição original para este evento.")
    content, flags = build_draft([s.text for s in segs])
    d = Document(tenant_id=ctx.tenant_id, event_id=ev.id, language=ev.original_language,
                 title=f"{ev.title} — Documento", content=content, flags=flags)
    db.add(d)
    db.commit()
    audit(db, action="doc.generate", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(d.id), ip=ctx.ip)
    return dout(d)


@router.get("/{doc_id}")
def get_doc(doc_id: UUID, ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    return dout(_get(db, ctx, doc_id))


class DocEdit(BaseModel):
    content: dict


@router.put("/{doc_id}")
def edit_doc(doc_id: UUID, body: DocEdit, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    if d.status in (DocStatus.APPROVED, DocStatus.PUBLISHED):
        raise HTTPException(409, "Documento aprovado não pode ser editado; crie uma nova versão.")
    d.content = body.content
    reviewed = {f["ref"] for f in d.flags if f.get("reviewed")}
    text = "\n".join(c.get("body", "") for c in body.content.get("chapters", []))
    d.flags = [{"ref": r, "reviewed": r in reviewed} for r in detect_references(text)]  # novas citações voltam a exigir revisão
    d.status = DocStatus.DRAFT
    d.version += 1
    db.commit()
    return dout(d)


class FlagReview(BaseModel):
    ref: str


@router.post("/{doc_id}/review-flag")
def review_flag(doc_id: UUID, body: FlagReview, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    d.flags = [{**f, "reviewed": True} if f["ref"] == body.ref else f for f in d.flags]
    db.commit()
    return dout(d)


@router.post("/{doc_id}/submit")
def submit(doc_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    if d.status != DocStatus.DRAFT:
        raise HTTPException(409, "Estado inválido.")
    d.status = DocStatus.IN_REVIEW
    db.commit()
    return dout(d)


class ApproveIn(BaseModel):
    note: str = ""


@router.post("/{doc_id}/approve")
def approve(doc_id: UUID, body: ApproveIn, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    """Aprovação HUMANA (administrador). Gera o PDF só agora."""
    d = _get(db, ctx, doc_id)
    if d.status != DocStatus.IN_REVIEW:
        raise HTTPException(409, "Envie para revisão antes de aprovar.")
    if any(not f.get("reviewed") for f in d.flags):
        raise HTTPException(409, "Revise todas as referências sinalizadas antes de aprovar.")
    t, ev = db.get(Tenant, ctx.tenant_id), db.get(Event, d.event_id)
    d.pdf_key = render_pdf(str(d.id), str(ctx.tenant_id), d.title, f"{ev.presenter} · {ev.theme}".strip(" ·"), t.name,
                           d.content, (t.branding or {}).get("primary_color", "#0B63CE"))
    d.status = DocStatus.APPROVED
    db.add(PublicationApproval(tenant_id=ctx.tenant_id, document_id=d.id, approved_by=ctx.user.id, note=body.note))
    db.commit()
    audit(db, action="doc.approve", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(d.id), ip=ctx.ip)
    return dout(d)


@router.post("/{doc_id}/publish")
def publish(doc_id: UUID, ctx: Ctx = Depends(require_admin), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    if d.status != DocStatus.APPROVED:
        raise HTTPException(409, "Só documentos aprovados podem ser publicados.")
    d.status = DocStatus.PUBLISHED
    db.commit()
    audit(db, action="doc.publish", actor_id=ctx.user.id, tenant_id=ctx.tenant_id, target=str(d.id), ip=ctx.ip)
    return dout(d)


@router.get("/{doc_id}/pdf")
def pdf(doc_id: UUID, ctx: Ctx = Depends(require_member), db: Session = Depends(get_db)):
    d = _get(db, ctx, doc_id)
    if d.status not in (DocStatus.APPROVED, DocStatus.PUBLISHED) or not d.pdf_key:
        raise HTTPException(404, "PDF indisponível.")
    path = (STORAGE / d.pdf_key).resolve()
    # Defesa extra: o arquivo TEM de estar sob o prefixo do tenant (anti path traversal/cross-tenant).
    if not str(path).startswith(str((STORAGE / str(ctx.tenant_id)).resolve())) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf", filename=f"{d.title}.pdf")


# ---------------- Público: apenas documentos PUBLICADOS ----------------
public_router = APIRouter(prefix="/public/booklets", tags=["public"])


@public_router.get("/{code}")
def public_list(code: str, db: Session = Depends(get_db)):
    """Lista apostilas PUBLICADAS do evento (rascunho/aprovado-não-publicado nunca aparece)."""
    ev = db.scalar(select(Event).where(Event.join_code == code.lower(), Event.deleted_at.is_(None)))
    if not ev or ev.access_password_hash:   # privado: sem apostilas públicas
        raise HTTPException(404)
    docs = db.scalars(select(Document).where(Document.event_id == ev.id, Document.status == DocStatus.PUBLISHED)).all()
    return [{"id": str(d.id), "title": d.title, "language": d.language} for d in docs]


@public_router.get("/{code}/{doc_id}/pdf")
def public_pdf(code: str, doc_id: UUID, db: Session = Depends(get_db)):
    ev = db.scalar(select(Event).where(Event.join_code == code.lower()))
    d = db.get(Document, doc_id)
    if not ev or ev.access_password_hash or not d or d.event_id != ev.id or d.status != DocStatus.PUBLISHED or not d.pdf_key:
        raise HTTPException(404)
    path = (STORAGE / d.pdf_key).resolve()
    if not str(path).startswith(str((STORAGE / str(d.tenant_id)).resolve())) or not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf", filename=f"{d.title}.pdf")
