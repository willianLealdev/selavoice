"""Logo da organização: envio seguro, exibição pública e isolamento entre tenants."""
import io

from PIL import Image

from conftest import register


def _img(fmt="PNG", size=(900, 300)):
    b = io.BytesIO()
    Image.new("RGB", size, (10, 90, 210)).save(b, format=fmt)
    return b.getvalue()


def _slug(client, h):
    return client.get("/auth/me", headers=h).json()["memberships"][0]["slug"]


def test_upload_logo_is_public_png_and_resized(client):
    h, _ = register(client, "Org Logo Um")
    r = client.post("/organizations/me/logo", files={"file": ("l.jpg", _img("JPEG"), "image/jpeg")}, headers=h)
    assert r.status_code == 200 and r.json()["logo_url"].startswith("/public/orgs/")
    slug = _slug(client, h)
    # aparece no perfil público e na busca, e a imagem é servida SEM login, sempre como PNG <= 512 px
    assert client.get(f"/public/orgs/{slug}").json()["logo_url"] == r.json()["logo_url"]
    assert any(o["logo_url"] for o in client.get("/public/orgs", params={"q": "Org Logo"}).json())
    img = client.get(f"/public/orgs/{slug}/logo")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert max(Image.open(io.BytesIO(img.content)).size) <= 512


def test_logo_rejects_svg_fake_and_huge(client):
    h, _ = register(client, "Org Logo Dois")
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    for name, data in [("a.svg", svg), ("a.png", b"isto nao e imagem"), ("a.png", b"")]:
        assert client.post("/organizations/me/logo", files={"file": (name, data, "image/png")}, headers=h).status_code == 422
    big = _img("PNG", (4000, 4000)) + b"0" * (2 * 1024 * 1024)
    assert client.post("/organizations/me/logo", files={"file": ("a.png", big, "image/png")}, headers=h).status_code in (413, 422)
    assert client.get(f"/public/orgs/{_slug(client, h)}/logo").status_code == 404  # nada foi salvo


def test_logo_cannot_be_set_to_external_url_and_can_be_removed(client):
    h, _ = register(client, "Org Logo Tres")
    client.patch("/organizations/me", json={"branding": {"logo_url": "https://evil.example/x.png"}}, headers=h)
    assert not client.get(f"/public/orgs/{_slug(client, h)}").json()["logo_url"]
    client.post("/organizations/me/logo", files={"file": ("l.png", _img(), "image/png")}, headers=h)
    client.patch("/organizations/me", json={"branding": {"primary_color": "#112233"}}, headers=h)  # cor não apaga o logo
    assert client.get(f"/public/orgs/{_slug(client, h)}").json()["logo_url"]
    assert client.delete("/organizations/me/logo", headers=h).status_code == 200
    assert client.get(f"/public/orgs/{_slug(client, h)}/logo").status_code == 404


def test_logo_isolated_between_tenants(client):
    ha, _ = register(client, "Org Logo A")
    hb, _ = register(client, "Org Logo B")
    client.post("/organizations/me/logo", files={"file": ("l.png", _img(), "image/png")}, headers=ha)
    assert client.get(f"/public/orgs/{_slug(client, hb)}/logo").status_code == 404   # B não herda o logo de A
    assert client.post("/organizations/me/logo", files={"file": ("l.png", _img(), "image/png")}).status_code in (401, 403)


def test_contact_public_validated_and_normalized(client):
    h, _ = register(client, "Org Contato")
    ok = {"address": "123 Main St", "city": "Las Vegas", "website": "exemplo.org", "instagram": "https://instagram.com/ufcchurch/",
          "facebook": "@ufc.church", "email": "oi@exemplo.org", "phone": "+1 702 555 0100", "description": "Bem-vindos"}
    assert client.patch("/organizations/me", json={"contact": ok}, headers=h).status_code == 200
    c = client.get(f"/public/orgs/{_slug(client, h)}").json()["contact"]
    assert c["website"] == "https://exemplo.org" and c["instagram"] == "ufcchurch" and c["facebook"] == "ufc.church"
    assert c["links"]["instagram"] == "https://instagram.com/ufcchurch" and c["address"] == "123 Main St"
    # campos vazios somem; contato ruim é recusado (nada de javascript:, script em rede social, e-mail quebrado)
    assert client.patch("/organizations/me", json={"contact": {"address": ""}}, headers=h).status_code == 200
    assert "address" not in client.get(f"/public/orgs/{_slug(client, h)}").json()["contact"]
    for bad in ({"website": "javascript:alert(1)"}, {"instagram": "a b<script>"}, {"email": "naoemail"}, {"phone": "abc"}, {"address": "x" * 300}):
        assert client.patch("/organizations/me", json={"contact": bad}, headers=h).status_code == 422, bad
