"""Apostilas (Fase 6): original -> rascunho -> revisão humana -> PDF; não publicado é inacessível."""
from app.services.editorial import detect_references
from conftest import make_event

PARAS = ["Abram em João 3:16 e leiam comigo.", "A fé move montanhas.", "Também em Salmos 23 encontramos paz."]


def _setup(client, h):
    ev = make_event(client, h, "Culto Doc", presenter="Pr. Ana", theme="Fé")
    assert client.post(f"/documents/events/{ev['id']}/original-transcript", json={"paragraphs": PARAS}, headers=h).status_code == 201
    return ev, client.post(f"/documents/events/{ev['id']}/generate", headers=h).json()


def test_reference_detection():
    assert "João 3:16" in detect_references("Veja João 3:16 hoje")
    assert detect_references("Texto sem citação nenhuma.") == []


def test_full_flow_requires_review_and_produces_pdf(client, tenant_a):
    ev, d = _setup(client, tenant_a)
    did = d["id"]
    assert {f["ref"] for f in d["flags"]} >= {"João 3:16"}
    assert not any(c["editorial"] for c in d["content"]["chapters"])  # sem IA: nada "inventado"
    assert client.get(f"/documents/{did}/pdf", headers=tenant_a).status_code == 404   # ainda não aprovado
    client.post(f"/documents/{did}/submit", headers=tenant_a)
    assert client.post(f"/documents/{did}/approve", json={}, headers=tenant_a).status_code == 409  # refs não revisadas
    for f in d["flags"]:
        client.post(f"/documents/{did}/review-flag", json={"ref": f["ref"]}, headers=tenant_a)
    assert client.post(f"/documents/{did}/approve", json={"note": "ok"}, headers=tenant_a).status_code == 200
    pdf = client.get(f"/documents/{did}/pdf", headers=tenant_a)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.post(f"/documents/{did}/publish", headers=tenant_a).json()["status"] == "PUBLISHED"


def test_document_cross_tenant_denied(client, tenant_a, tenant_b):
    _, d = _setup(client, tenant_a)
    assert client.get(f"/documents/{d['id']}", headers=tenant_b).status_code == 404
    assert client.get(f"/documents/{d['id']}/pdf", headers=tenant_b).status_code == 404
    assert client.put(f"/documents/{d['id']}", json={"content": {}}, headers=tenant_b).status_code == 404


def test_unpublished_hidden_from_public_then_visible(client, tenant_a):
    ev, d = _setup(client, tenant_a)
    did, code = d["id"], ev["join_code"]
    assert client.get(f"/public/booklets/{code}").json() == []
    client.post(f"/documents/{did}/submit", headers=tenant_a)
    for f in d["flags"]:
        client.post(f"/documents/{did}/review-flag", json={"ref": f["ref"]}, headers=tenant_a)
    client.post(f"/documents/{did}/approve", json={}, headers=tenant_a)
    assert client.get(f"/public/booklets/{code}").json() == []                    # aprovado ainda NÃO é público
    assert client.get(f"/public/booklets/{code}/{did}/pdf").status_code == 404
    client.post(f"/documents/{did}/publish", headers=tenant_a)
    assert client.get(f"/public/booklets/{code}/{did}/pdf").content.startswith(b"%PDF")
