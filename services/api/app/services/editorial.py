"""Pipeline editorial da apostila: estrutura (DeepSeek ou fallback local) + PDF (ReportLab).

REGRAS DA SPEC
- DeepSeek SOMENTE para estruturar/editorar (capítulos, resumo). NUNCA para traduzir ou transcrever.
- Material adicionado pelo editor (resumo, reflexões) é marcado `editorial=True` e aparece
  rotulado no PDF; a fala literal NUNCA é alterada nem tem citações inventadas.
- Referências bíblicas são DETECTADAS e sinalizadas para revisão humana (não validamos o texto
  do versículo automaticamente — não inventamos escritura).
- Publicação exige aprovação humana (ver routers/documents.py).
"""
import re
from pathlib import Path

import httpx
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from ..config import get_settings
from .secrets_store import get_secret, is_enabled

settings = get_settings()
import os
# Pasta dos arquivos (PDFs, logos). Em produção aponte STORAGE_DIR para o disco PERSISTENTE (ex.: /data/storage).
STORAGE = Path(os.environ.get("STORAGE_DIR", "storage"))

# Livro + capítulo[:versículo]  (ex.: "João 3:16", "John 3", "1 Coríntios 13:4-7")
REF_RE = re.compile(r"\b((?:[1-3]\s)?[A-ZÀ-Ú][a-zà-ú]{2,})\s(\d{1,3})(?::(\d{1,3})(?:-(\d{1,3}))?)?\b")
BOOKS_HINT = ("João", "Mateus", "Marcos", "Lucas", "Atos", "Romanos", "Coríntios", "Gálatas", "Efésios", "Filipenses",
              "Salmos", "Provérbios", "Isaías", "Gênesis", "Êxodo", "Hebreus", "Tiago", "Pedro", "Apocalipse",
              "John", "Matthew", "Mark", "Luke", "Acts", "Romans", "Psalm", "Proverbs", "Genesis", "Exodus")


def detect_references(text: str) -> list[str]:
    """Lista referências encontradas (para revisão humana)."""
    found = []
    for m in REF_RE.finditer(text):
        if any(b in m.group(1) for b in BOOKS_HINT):
            found.append(m.group(0))
    return sorted(set(found))


def chunk_chapters(paragraphs: list[str], per_chapter: int = 8) -> list[dict]:
    """Estrutura LOCAL e determinística (fallback sem IA): agrupa a fala em capítulos numerados."""
    chapters = []
    for i in range(0, len(paragraphs), per_chapter):
        body = "\n\n".join(paragraphs[i:i + per_chapter])
        chapters.append({"title": f"Parte {len(chapters) + 1}", "body": body, "editorial": False})
    return chapters


def deepseek_outline(text: str) -> dict | None:
    """Pede à DeepSeek SOMENTE um esboço editorial (títulos/resumo). Retorna None se sem chave/erro."""
    key = get_secret("deepseek", "api_key")
    if not key or not is_enabled("deepseek"):
        return None
    try:
        r = httpx.post("https://api.deepseek.com/chat/completions", timeout=60,
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": "deepseek-chat", "messages": [
                           {"role": "system", "content": "Você é editor. Crie títulos de capítulos e um resumo curto. "
                            "NÃO traduza, NÃO invente citações nem versículos, NÃO altere a fala original."},
                           {"role": "user", "content": text[:20000]}]})
        r.raise_for_status()
        return {"summary": r.json()["choices"][0]["message"]["content"]}
    except Exception:
        return None


def build_draft(paragraphs: list[str]) -> tuple[dict, list[dict]]:
    full = "\n".join(paragraphs)
    chapters = chunk_chapters(paragraphs)
    outline = deepseek_outline(full)
    if outline:  # material editorial claramente marcado
        chapters.insert(0, {"title": "Resumo editorial", "body": outline["summary"], "editorial": True})
    refs = detect_references(full)
    flags = [{"ref": r, "reviewed": False} for r in refs]
    return {"chapters": chapters, "references": refs}, flags


def render_pdf(doc_id: str, tenant_id: str, title: str, subtitle: str, org_name: str, content: dict,
               primary_color: str = "#0B63CE") -> str:
    """Gera o PDF (capa, sumário, capítulos, apêndice). Salva em storage/<tenant>/docs/<id>.pdf."""
    key = f"{tenant_id}/docs/{doc_id}.pdf"
    path = STORAGE / key
    path.parent.mkdir(parents=True, exist_ok=True)
    brand = colors.HexColor(primary_color if re.fullmatch(r"#[0-9a-fA-F]{6}", primary_color or "") else "#0B63CE")
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], textColor=brand, fontSize=22, spaceAfter=12)
    cover = ParagraphStyle("cover", parent=ss["Title"], textColor=brand, fontSize=30, leading=36)
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=11, leading=16)
    note = ParagraphStyle("n", parent=body, textColor=colors.HexColor("#8A5A00"), fontSize=9)
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    story = [Spacer(1, 6 * cm), Paragraph(esc(title), cover), Spacer(1, 12), Paragraph(esc(subtitle), ss["Heading3"]),
             Spacer(1, 4 * cm), Paragraph(esc(org_name), ss["Heading2"]),
             Paragraph("Documento revisado e aprovado para publicação.", note), PageBreak(), Paragraph("Sumário", h1)]
    chapters = content.get("chapters", [])
    for i, c in enumerate(chapters, 1):
        story.append(Paragraph(f"{i}. {esc(c['title'])}", body))
    story.append(PageBreak())
    for c in chapters:
        story.append(Paragraph(esc(c["title"]), h1))
        if c.get("editorial"):
            story.append(Paragraph("Material editorial — não faz parte da fala original.", note))
        for para in (c.get("body") or "").split("\n\n"):
            story.append(Paragraph(esc(para), body))
            story.append(Spacer(1, 6))
        story.append(PageBreak())
    refs = content.get("references", [])
    story.append(Paragraph("Apêndice — Referências citadas", h1))
    for r in refs:
        story.append(Paragraph(esc(r), body))
    SimpleDocTemplate(str(path), pagesize=A4, title=title, author=org_name,
                      leftMargin=2.2 * cm, rightMargin=2.2 * cm).build(story)
    return key
