"""Apostila AUTOMÁTICA: ao encerrar o evento a DeepSeek escreve os pontos e o PDF (com logo) é publicado sozinho."""
import io
from uuid import UUID

import pytest

from app.services import auto_book, editorial
from conftest import make_event

FALA = [
    "Irmãos, hoje quero falar sobre a fé que persevera nos momentos difíceis, porque a fé não é ausência de dúvida.",
    "Em Hebreus 11 vemos homens e mulheres que confiaram sem ver o resultado, e isso nos ensina a esperar com paciência.",
    "A esperança não envergonha, e quando o povo de Deus ora unido, as portas se abrem de maneira inesperada.",
    "Portanto, nesta semana, escolha uma pessoa para encorajar e uma oração para fazer todos os dias sem falta.",
]
LIVRO = {
    "summary": "A mensagem trata da fé que persevera. Mostra que a fé convive com a dúvida e se sustenta pela esperança.",
    "sections": [
        {"heading": "A fé que persevera", "paragraphs": ["A fé não é ausência de dúvida."], "bullets": ["Confiar sem ver o resultado"]},
        {"heading": "Esperança e oração unida", "paragraphs": ["Quando o povo ora unido, portas se abrem."], "bullets": []},
    ],
    "quotes": ["a fé não é ausência de dúvida", "frase que o palestrante nunca disse nesta fala"],
    "references": ["Hebreus 11", "Salmos 23"],           # "Salmos 23" NÃO foi citado: deve ser descartado
    "questions": ["Quem você pode encorajar esta semana?"],
    "conclusion": "Persevere na fé e na oração.",
}


@pytest.fixture()
def deepseek(monkeypatch):
    chamadas = []
    monkeypatch.setattr(editorial, "_chat_json", lambda s, u, max_tokens=4000: (chamadas.append(u) or LIVRO))
    return chamadas


def _evento_com_fala(client, h, paragrafos=FALA, **kw):
    ev = make_event(client, h, "Culto de Domingo", presenter="Pr. João", theme="Fé", **kw)
    client.post(f"/documents/events/{ev['id']}/original-transcript", json={"paragraphs": paragrafos}, headers=h)
    return ev


def test_stop_creates_and_publishes_book_automatically(client, tenant_a, deepseek):
    ev = _evento_com_fala(client, tenant_a)
    client.post(f"/events/{ev['id']}/start", headers=tenant_a)
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)                      # encerrar => apostila nasce sozinha
    docs = client.get(f"/documents/events/{ev['id']}", headers=tenant_a).json()
    assert len(docs) == 1 and docs[0]["status"] == "PUBLISHED"
    titulos = [c["title"] for c in docs[0]["content"]["chapters"]]
    assert titulos[0] == "Resumo" and "A fé que persevera" in titulos and "Frases marcantes" in titulos and titulos[-1] == "Conclusão"
    quotes = next(c for c in docs[0]["content"]["chapters"] if c.get("kind") == "quotes")["body"]
    assert "ausência de dúvida" in quotes and "nunca disse" not in quotes           # frase inventada é descartada
    assert docs[0]["content"]["references"] == ["Hebreus 11"]                        # referência não citada é descartada
    pub = client.get(f"/public/booklets/{ev['join_code']}").json()                   # já aparece para o público
    assert len(pub) == 1
    pdf = client.get(f"/public/booklets/{ev['join_code']}/{pub[0]['id']}/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 3000


def test_does_not_duplicate_unless_forced(client, tenant_a, deepseek):
    ev = _evento_com_fala(client, tenant_a)
    assert auto_book.run_sync(UUID(ev["id"])) == "published"
    assert auto_book.run_sync(UUID(ev["id"])) == "exists"                            # não duplica
    assert client.post(f"/documents/events/{ev['id']}/auto", headers=tenant_a).status_code == 202   # refazer de propósito
    assert len(client.get(f"/documents/events/{ev['id']}", headers=tenant_a).json()) == 2


def test_no_book_without_speech_or_when_disabled_or_unsupported(client, tenant_a, deepseek):
    vazio = make_event(client, tenant_a, "Vazio")
    assert auto_book.run_sync(UUID(vazio["id"])) == "no_transcript"
    curto = _evento_com_fala(client, tenant_a, ["Oi."])
    assert auto_book.run_sync(UUID(curto["id"])) == "no_transcript"
    assert client.patch("/organizations/me", json={"auto_booklet": False}, headers=tenant_a).status_code == 200
    assert client.get("/organizations/me", headers=tenant_a).json()["auto_booklet"] is False
    off = _evento_com_fala(client, tenant_a)
    assert auto_book.run_sync(UUID(off["id"])) == "disabled"
    client.patch("/organizations/me", json={"auto_booklet": True}, headers=tenant_a)
    ru = _evento_com_fala(client, tenant_a, original_language="ru")
    assert auto_book.run_sync(UUID(ru["id"])) == "unsupported_language"


def test_without_deepseek_key_uses_local_fallback_and_still_publishes(client, tenant_a, monkeypatch):
    monkeypatch.setattr(editorial, "_chat_json", lambda *a, **k: None)             # sem chave / DeepSeek fora do ar
    ev = _evento_com_fala(client, tenant_a)
    assert auto_book.run_sync(UUID(ev["id"])) == "published_fallback"
    d = client.get(f"/documents/events/{ev['id']}", headers=tenant_a).json()[0]
    assert d["status"] == "PUBLISHED" and d["content"]["fallback"] is True and d["content"]["chapters"][0]["title"] == "Parte 1"


def test_long_transcript_uses_two_steps(client, tenant_a, monkeypatch):
    chamadas = []

    def falso(system, user, max_tokens=4000):
        chamadas.append(user[:12])
        return {"notas": ["ponto A", "ponto B"]} if user.split("\n")[-2:-1] is not None and "TRECHO" in user else LIVRO
    monkeypatch.setattr(editorial, "_chat_json", falso)
    longa = [("Palavra importante sobre a fé e a esperança. " * 12).strip()] * 70       # ~38 mil caracteres
    ev = _evento_com_fala(client, tenant_a, longa)
    assert auto_book.run_sync(UUID(ev["id"])) == "published"
    assert len(chamadas) >= 3                                                           # várias notas + a chamada final


def test_pdf_has_logo_when_org_uploaded_one(client, tenant_a, deepseek):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 120), (200, 30, 30)).save(buf, "PNG")
    r = client.post("/organizations/me/logo", files={"file": ("logo.png", buf.getvalue(), "image/png")}, headers=tenant_a)
    assert r.status_code == 200
    ev = _evento_com_fala(client, tenant_a)
    assert auto_book.run_sync(UUID(ev["id"])) == "published"
    pub = client.get(f"/public/booklets/{ev['join_code']}").json()
    pdf = client.get(f"/public/booklets/{ev['join_code']}/{pub[0]['id']}/pdf").content
    assert b"/Subtype /Image" in pdf                                                   # a logo foi embutida no PDF
