"""Pipeline editorial da apostila: estrutura pela DeepSeek (ou plano B local) + PDF profissional (ReportLab).

COMO A APOSTILA É FEITA
- A DeepSeek lê TODA a transcrição do evento e escreve os PONTOS da palestra/pregação (resumo, pontos principais com
  explicação, frases marcantes, referências citadas, perguntas para refletir e conclusão), no idioma original da fala.
- Transcrições longas passam por duas etapas ("mapa e resumo"): primeiro notas de cada trecho, depois o texto final.
- A apostila é gerada e publicada AUTOMATICAMENTE quando o evento termina (ver services/auto_book.py). A organização pode
  editar, despublicar ou excluir depois.

REGRAS (da spec) QUE CONTINUAM VALENDO
- DeepSeek SOMENTE para estruturar/editorar. NUNCA para traduzir ou transcrever.
- Nada de citação inventada: só entram frases e referências que realmente aparecem na transcrição (filtro automático abaixo).
- O PDF informa, no fim, que foi gerado automaticamente com apoio de IA e que citações devem ser conferidas na fonte.
- Sem chave da DeepSeek, o plano B local organiza a transcrição em partes numeradas (sem texto escrito por IA).
"""
import io
import json
import logging
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (BaseDocTemplate, Frame, HRFlowable, ListFlowable, ListItem, NextPageTemplate, PageBreak,
                                PageTemplate, Paragraph, Spacer)
from reportlab.platypus import Image as RLImage

from ..config import get_settings
from .secrets_store import get_secret, is_enabled

settings = get_settings()
log = logging.getLogger("selavoice.book")
# Pasta dos arquivos (PDFs, logos). Em produção aponte STORAGE_DIR para o disco PERSISTENTE (ex.: /data/storage).
STORAGE = Path(os.environ.get("STORAGE_DIR", "storage"))

# Livro + capítulo[:versículo]  (ex.: "João 3:16", "John 3", "1 Coríntios 13:4-7")
REF_RE = re.compile(r"\b((?:[1-3]\s)?[A-ZÀ-Ú][a-zà-ú]{2,})\s(\d{1,3})(?::(\d{1,3})(?:-(\d{1,3}))?)?\b")
BOOKS_HINT = ("João", "Mateus", "Marcos", "Lucas", "Atos", "Romanos", "Coríntios", "Gálatas", "Efésios", "Filipenses",
              "Salmos", "Provérbios", "Isaías", "Gênesis", "Êxodo", "Hebreus", "Tiago", "Pedro", "Apocalipse",
              "John", "Matthew", "Mark", "Luke", "Acts", "Romans", "Psalm", "Proverbs", "Genesis", "Exodus")

LANG_NAMES = {"pt": "Português", "en": "English", "es": "Español", "fr": "Français", "de": "Deutsch", "it": "Italiano",
              "zh": "中文", "ja": "日本語", "ko": "한국어", "nl": "Nederlands", "pl": "Polski", "tr": "Türkçe", "id": "Indonesia"}
# Idiomas que o PDF consegue escrever hoje: alfabeto latino (fontes padrão) e chinês/japonês/coreano (fontes CID embutidas).
CJK_FONTS = {"zh": "STSong-Light", "ja": "HeiseiMin-W3", "ko": "HYSMyeongJo-Medium"}
LATIN = {"pt", "en", "es", "fr", "de", "it", "nl", "pl", "tr", "id", "sv", "da", "no", "fi", "cs", "ro", "hu", "ca", "ms", "vi", "hr", "sk", "sl"}

LABELS = {
    "pt": {"summary": "Resumo", "toc": "Sumário", "quotes": "Frases marcantes", "refs": "Referências citadas", "reflect": "Para refletir",
           "conclusion": "Conclusão", "page": "Página", "by": "Com", "auto": "Documento gerado automaticamente com apoio de inteligência artificial a partir da transcrição da fala. Pode conter imprecisões; confira as citações e referências na fonte."},
    "en": {"summary": "Summary", "toc": "Contents", "quotes": "Key quotes", "refs": "References cited", "reflect": "For reflection",
           "conclusion": "Conclusion", "page": "Page", "by": "With", "auto": "Document generated automatically with the support of artificial intelligence from the transcript of the talk. It may contain inaccuracies; please verify quotations and references at the source."},
    "es": {"summary": "Resumen", "toc": "Contenido", "quotes": "Frases destacadas", "refs": "Referencias citadas", "reflect": "Para reflexionar",
           "conclusion": "Conclusión", "page": "Página", "by": "Con", "auto": "Documento generado automáticamente con apoyo de inteligencia artificial a partir de la transcripción del discurso. Puede contener imprecisiones; verifique las citas y referencias en la fuente."},
}
MONTHS = {"pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"],
          "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
          "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]}


def labels(lang: str) -> dict:
    return LABELS.get(lang, LABELS["en"])


def book_supported(lang: str) -> bool:
    """O PDF só sai para idiomas que sabemos escrever (latino + CJK). Os demais (russo, árabe, hindi…) ficam para depois."""
    return lang in LATIN or lang in CJK_FONTS


def fmt_date(d: datetime | None, lang: str) -> str:
    if not d:
        return ""
    m = MONTHS.get(lang)
    if lang == "pt":
        return f"{d.day} de {m[d.month - 1]} de {d.year}"
    if lang == "es":
        return f"{d.day} de {m[d.month - 1]} de {d.year}"
    if lang == "en":
        return f"{m[d.month - 1]} {d.day}, {d.year}"
    return d.strftime("%Y-%m-%d")


def detect_references(text: str) -> list[str]:
    """Lista referências encontradas (para conferência)."""
    found = []
    for m in REF_RE.finditer(text):
        if any(b in m.group(1) for b in BOOKS_HINT):
            found.append(m.group(0))
    return sorted(set(found))


def chunk_chapters(paragraphs: list[str], per_chapter: int = 8) -> list[dict]:
    """Plano B LOCAL e determinístico (sem IA): agrupa a fala em capítulos numerados."""
    chapters = []
    for i in range(0, len(paragraphs), per_chapter):
        body = "\n\n".join(paragraphs[i:i + per_chapter])
        chapters.append({"title": f"Parte {len(chapters) + 1}", "body": body, "editorial": False})
    return chapters


# ------------------------------------------------------------------ DeepSeek
def _norm(s: str) -> str:
    """Minúsculas, sem acentos e sem pontuação: serve para conferir se uma frase realmente existe na transcrição."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _chat_json(system: str, user: str, *, max_tokens: int = 4000) -> dict | None:
    """Chama a DeepSeek pedindo JSON. None = sem chave, desligada ou erro (quem chama usa o plano B)."""
    key = get_secret("deepseek", "api_key")
    if not key or not is_enabled("deepseek"):
        return None
    for tentativa in range(2):
        try:
            r = httpx.post("https://api.deepseek.com/chat/completions", timeout=180,
                           headers={"Authorization": f"Bearer {key}"},
                           json={"model": "deepseek-chat", "temperature": 0.3, "max_tokens": max_tokens,
                                 "response_format": {"type": "json_object"},
                                 "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
            r.raise_for_status()
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except Exception as e:  # rede, limite, JSON quebrado: tenta de novo uma vez
            log.warning("deepseek falhou (tentativa %s): %s", tentativa + 1, type(e).__name__)
    return None


RULES = (
    "REGRAS OBRIGATÓRIAS: escreva SOMENTE com base no que foi dito na transcrição; NÃO invente fatos, histórias, números, "
    "citações nem versículos; NÃO traduza (escreva no idioma da transcrição); corrija apenas erros evidentes de transcrição "
    "(pontuação, palavras cortadas); tom profissional, claro e sóbrio, como uma apostila de estudo; nunca mencione 'IA', "
    "'transcrição' ou 'modelo'."
)


def deepseek_book(text: str, lang: str, title: str, presenter: str, theme: str) -> dict | None:
    """Pede à DeepSeek os PONTOS da palestra/pregação. Devolve o JSON validado ou None."""
    idioma = LANG_NAMES.get(lang, lang)
    ctx = f"Evento: {title}. Palestrante: {presenter or 'não informado'}. Tema: {theme or 'não informado'}. Idioma de escrita: {idioma}."
    material = text
    if len(text) > 24000:  # trecho a trecho: notas fiéis de cada parte e depois o texto final
        notas = []
        for i in range(0, len(text), 14000):
            parte = _chat_json(
                f"Você é um editor de apostilas. {RULES} Leia o trecho e devolva JSON {{\"notas\": [\"...\"]}} com notas objetivas e "
                "fiéis dos pontos tratados (ideias, argumentos, exemplos, referências citadas e frases marcantes literais), na ordem em que aparecem.",
                f"{ctx}\n\nTRECHO {i // 14000 + 1}:\n{text[i:i + 14000]}", max_tokens=2500)
            if parte and isinstance(parte.get("notas"), list):
                notas += [str(n) for n in parte["notas"]]
        if not notas:
            return None
        material = "NOTAS (na ordem da fala):\n- " + "\n- ".join(notas)
    d = _chat_json(
        f"Você é um editor profissional de apostilas de palestras e pregações. {RULES}\n"
        "Devolva SOMENTE JSON neste formato:\n"
        '{"summary": "resumo executivo em 2 a 3 parágrafos",\n'
        ' "sections": [{"heading": "título curto do ponto", "paragraphs": ["explicação do ponto em 1 a 3 parágrafos"], "bullets": ["ideias-chave deste ponto"]}],\n'
        ' "quotes": ["até 5 frases marcantes, COPIADAS literalmente da fala"],\n'
        ' "references": ["referências bíblicas ou fontes que o palestrante CITOU"],\n'
        ' "questions": ["3 a 5 perguntas para reflexão ou aplicação, baseadas no conteúdo"],\n'
        ' "conclusion": "parágrafo de conclusão fiel à mensagem"}\n'
        "Use de 3 a 8 'sections' na ordem em que o tema foi desenvolvido.",
        f"{ctx}\n\n{material}", max_tokens=5000)
    if not d or not isinstance(d.get("sections"), list) or not d["sections"]:
        return None
    return d


def _clean_book(d: dict, source_text: str) -> dict:
    """Filtro anti-invenção: só ficam frases e referências que realmente aparecem na transcrição."""
    base = _norm(source_text)
    quotes = [q.strip() for q in d.get("quotes", []) if isinstance(q, str) and len(_norm(q)) > 12 and _norm(q) in base][:5]
    refs = []
    for r in d.get("references", []):
        if isinstance(r, str) and r.strip() and _norm(r) in base and r.strip() not in refs:
            refs.append(r.strip())
    d["quotes"], d["references"] = quotes, refs
    return d


def build_auto_content(paragraphs: list[str], lang: str, title: str, presenter: str, theme: str) -> dict:
    """Monta o conteúdo da apostila (capítulos editáveis). Com DeepSeek = pontos escritos; sem = plano B local."""
    text = "\n".join(paragraphs)
    lb = labels(lang)
    d = deepseek_book(text, lang, title, presenter, theme)
    if not d:
        return {"auto": True, "fallback": True, "chapters": chunk_chapters(paragraphs), "references": detect_references(text)}
    d = _clean_book(d, text)
    ch: list[dict] = []
    if d.get("summary"):
        ch.append({"title": lb["summary"], "body": str(d["summary"]).strip(), "editorial": False, "kind": "summary"})
    for s in d["sections"][:10]:
        if not isinstance(s, dict) or not s.get("heading"):
            continue
        body = "\n\n".join(str(p).strip() for p in s.get("paragraphs", []) if str(p).strip())
        bullets = [str(b).strip() for b in s.get("bullets", []) if str(b).strip()]
        if bullets:
            body += ("\n\n" if body else "") + "\n".join(f"• {b}" for b in bullets)
        ch.append({"title": str(s["heading"]).strip(), "body": body, "editorial": False, "kind": "section"})
    if d["quotes"]:
        ch.append({"title": lb["quotes"], "body": "\n".join(d["quotes"]), "editorial": False, "kind": "quotes"})
    qs = [str(q).strip() for q in d.get("questions", []) if str(q).strip()]
    if qs:
        ch.append({"title": lb["reflect"], "body": "\n".join(f"• {q}" for q in qs[:6]), "editorial": False, "kind": "questions"})
    if d.get("conclusion"):
        ch.append({"title": lb["conclusion"], "body": str(d["conclusion"]).strip(), "editorial": False, "kind": "conclusion"})
    return {"auto": True, "fallback": False, "chapters": ch, "references": d["references"]}


def build_draft(paragraphs: list[str]) -> tuple[dict, list[dict]]:
    """Fluxo MANUAL antigo (rascunho + revisão): organiza a fala em partes e sinaliza as referências para conferência."""
    full = "\n".join(paragraphs)
    chapters = chunk_chapters(paragraphs)
    outline = _chat_json("Você é editor. Crie um resumo curto em JSON {\"summary\": \"...\"}. " + RULES, full[:20000], max_tokens=1200)
    if outline and outline.get("summary"):  # material editorial claramente marcado
        chapters.insert(0, {"title": "Resumo editorial", "body": str(outline["summary"]), "editorial": True})
    refs = detect_references(full)
    flags = [{"ref": r, "reviewed": False} for r in refs]
    return {"chapters": chapters, "references": refs}, flags


# ------------------------------------------------------------------ PDF
def _fonts(lang: str) -> tuple[str, str, str]:
    """(corpo, negrito, itálico) para o idioma. CJK usa fonte CID embutida; latino usa Times (corpo) e Helvetica (títulos)."""
    if lang in CJK_FONTS:
        f = CJK_FONTS[lang]
        try:
            pdfmetrics.getFont(f)
        except KeyError:
            pdfmetrics.registerFont(UnicodeCIDFont(f))
        return f, f, f
    return "Times-Roman", "Helvetica-Bold", "Times-Italic"


def _logo_reader(tenant_id: str):
    """Logo da organização (PNG já higienizado no upload). None se a organização não enviou."""
    p = STORAGE / tenant_id / "branding" / "logo.png"
    if not p.exists():
        return None, 0.0
    try:
        from PIL import Image
        with Image.open(p) as im:
            return p, im.width / max(im.height, 1)
    except Exception:
        return None, 0.0


def render_book(doc_id: str, tenant_id: str, title: str, subtitle: str, org_name: str, content: dict, *,
                primary_color: str = "#0B63CE", lang: str = "pt", date_str: str = "", auto_note: bool = False) -> str:
    """Gera o PDF profissional: capa com a logo da organização, sumário, cabeçalho e rodapé com número de página,
    capítulos, frases marcantes em destaque, referências e aviso final. Salva em storage/<tenant>/docs/<id>.pdf."""
    key = f"{tenant_id}/docs/{doc_id}.pdf"
    path = STORAGE / key
    path.parent.mkdir(parents=True, exist_ok=True)
    brand = colors.HexColor(primary_color if re.fullmatch(r"#[0-9a-fA-F]{6}", primary_color or "") else "#0B63CE")
    ink, gray = colors.HexColor("#1C2536"), colors.HexColor("#6B7585")
    fb, fh, fi = _fonts(lang)
    lb = labels(lang)
    cjk = lang in CJK_FONTS
    just = TA_LEFT if cjk else TA_JUSTIFY
    st = {
        "cover_t": ParagraphStyle("ct", fontName=fh, fontSize=30, leading=36, textColor=brand, alignment=TA_CENTER),
        "cover_s": ParagraphStyle("cs", fontName=fb, fontSize=14, leading=20, textColor=ink, alignment=TA_CENTER),
        "cover_o": ParagraphStyle("co", fontName=fh, fontSize=12, leading=16, textColor=gray, alignment=TA_CENTER),
        "h1": ParagraphStyle("h1", fontName=fh, fontSize=18, leading=23, textColor=brand, spaceBefore=6, spaceAfter=8),
        "toc": ParagraphStyle("toc", fontName=fb, fontSize=12, leading=22, textColor=ink),
        "body": ParagraphStyle("b", fontName=fb, fontSize=11.5, leading=17.5, textColor=ink, alignment=just, spaceAfter=7),
        "quote": ParagraphStyle("q", fontName=fi, fontSize=12.5, leading=19, textColor=ink, leftIndent=16, rightIndent=10, spaceAfter=10,
                                borderPadding=(4, 4, 4, 10), backColor=colors.HexColor("#F3F6FB")),
        "small": ParagraphStyle("s", fontName=fb, fontSize=8.5, leading=12, textColor=gray, alignment=just),
    }
    esc = lambda s: (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    logo_path, ratio = _logo_reader(tenant_id)

    def header_footer(c, d):
        c.saveState()
        W, H = A4
        if logo_path:  # cabeçalho: logo pequena à esquerda, título do evento à direita
            h = 0.9 * cm
            c.drawImage(str(logo_path), 2.2 * cm, H - 1.75 * cm, width=h * ratio, height=h, mask="auto", preserveAspectRatio=True)
        else:
            c.setFont(fh, 9); c.setFillColor(brand); c.drawString(2.2 * cm, H - 1.45 * cm, org_name[:60])
        c.setFont(fb, 8.5); c.setFillColor(gray)
        c.drawRightString(W - 2.2 * cm, H - 1.45 * cm, title[:70])
        c.setStrokeColor(colors.HexColor("#D9DFEA")); c.setLineWidth(0.6)
        c.line(2.2 * cm, H - 2.0 * cm, W - 2.2 * cm, H - 2.0 * cm)
        c.line(2.2 * cm, 1.75 * cm, W - 2.2 * cm, 1.75 * cm)
        c.drawString(2.2 * cm, 1.2 * cm, org_name[:70])
        c.drawRightString(W - 2.2 * cm, 1.2 * cm, f"{lb['page']} {d.page}")
        c.restoreState()

    def cover_page(c, d):
        c.saveState()
        W, H = A4
        c.setFillColor(brand); c.rect(0, H - 0.9 * cm, W, 0.9 * cm, stroke=0, fill=1)   # faixa da cor da organização no topo
        c.rect(0, 0, W, 0.5 * cm, stroke=0, fill=1)
        c.restoreState()

    doc = BaseDocTemplate(str(path), pagesize=A4, title=title, author=org_name, leftMargin=2.2 * cm, rightMargin=2.2 * cm,
                          topMargin=2.6 * cm, bottomMargin=2.3 * cm)
    frame_body = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height - 0.2 * cm, id="body")
    frame_cover = Frame(doc.leftMargin, 2 * cm, doc.width, A4[1] - 4 * cm, id="cover")
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame_cover], onPage=cover_page),
                          PageTemplate(id="body", frames=[frame_body], onPage=header_footer)])

    story: list = [Spacer(1, 0.8 * cm)]
    if logo_path:                                  # LOGO NO TOPO DA CAPA
        h = 3.2 * cm
        w = min(h * ratio, doc.width * 0.7)
        story.append(RLImage(str(logo_path), width=w, height=w / max(ratio, 0.01), hAlign="CENTER"))
    else:
        story.append(Paragraph(esc(org_name), st["cover_o"]))
    story += [Spacer(1, 2.6 * cm), HRFlowable(width="40%", thickness=2.5, color=brand, hAlign="CENTER"), Spacer(1, 0.7 * cm),
              Paragraph(esc(title), st["cover_t"]), Spacer(1, 0.6 * cm)]
    if subtitle:
        story.append(Paragraph(esc(subtitle), st["cover_s"]))
    if date_str:
        story += [Spacer(1, 0.3 * cm), Paragraph(esc(date_str), st["cover_o"])]
    story += [Spacer(1, 5.5 * cm), Paragraph(esc(org_name), st["cover_o"]), NextPageTemplate("body"), PageBreak()]

    chapters = [c for c in content.get("chapters", []) if (c.get("title") or c.get("body"))]
    story.append(Paragraph(lb["toc"], st["h1"]))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#D9DFEA")))
    for i, c in enumerate(chapters, 1):
        story.append(Paragraph(f"{i}. {esc(c.get('title', ''))}", st["toc"]))
    refs = content.get("references", [])
    if refs:
        story.append(Paragraph(f"{len(chapters) + 1}. {esc(lb['refs'])}", st["toc"]))
    story.append(PageBreak())

    def render_body(text: str, kind: str):
        out: list = []
        bullets: list[str] = []

        def flush():
            if bullets:
                out.append(ListFlowable([ListItem(Paragraph(esc(b), st["body"]), leftIndent=14) for b in bullets], bulletType="bullet",
                                        bulletFontSize=11, start="•", leftIndent=14))
                bullets.clear()
        for line in (text or "").split("\n"):
            ln = line.strip()
            if not ln:
                flush(); continue
            if ln.startswith(("• ", "- ")):
                bullets.append(ln[2:].strip()); continue
            flush()
            out.append(Paragraph(("“" + esc(ln) + "”") if kind == "quotes" else esc(ln), st["quote"] if kind == "quotes" else st["body"]))
        flush()
        return out

    for c in chapters:
        story.append(Paragraph(esc(c.get("title", "")), st["h1"]))
        story.append(HRFlowable(width="18%", thickness=2, color=brand, hAlign="LEFT", spaceAfter=8))
        if c.get("editorial"):
            story.append(Paragraph("Material editorial — não faz parte da fala original.", st["small"]))
        story += render_body(c.get("body", ""), c.get("kind", ""))
        story.append(Spacer(1, 10))
    if refs:
        story += [Paragraph(esc(lb["refs"]), st["h1"]), HRFlowable(width="18%", thickness=2, color=brand, hAlign="LEFT", spaceAfter=8)]
        story.append(ListFlowable([ListItem(Paragraph(esc(r), st["body"]), leftIndent=14) for r in refs], bulletType="bullet", start="•", leftIndent=14))
    story += [Spacer(1, 22), HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#D9DFEA")), Spacer(1, 6)]
    story.append(Paragraph(esc(lb["auto"] if auto_note else "Documento revisado e aprovado para publicação."), st["small"]))
    doc.build(story)
    return key


def render_pdf(doc_id: str, tenant_id: str, title: str, subtitle: str, org_name: str, content: dict,
               primary_color: str = "#0B63CE") -> str:
    """Compatível com o fluxo manual (aprovação humana): usa o mesmo layout profissional."""
    return render_book(doc_id, tenant_id, title, subtitle, org_name, content, primary_color=primary_color, lang="pt")
