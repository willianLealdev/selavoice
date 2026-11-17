"""E-mail (Resend): convite e recuperação de senha. O envio é interceptado (nenhum e-mail real sai)."""
import httpx
import pytest

from conftest import PW, register

NEWPW = "Nova-Senha-Forte-9"


@pytest.fixture()
def sent(monkeypatch, client, superadmin):
    """Configura o Resend pelo painel e captura os envios."""
    out = []
    client.put("/admin/integrations/resend", json={"values": {"api_key": "re_testkey_123456", "from_email": "no-reply@exemplo.com"}},
               headers=superadmin)

    def fake_post(url, **kw):
        out.append((url, kw))
        return httpx.Response(200, json={"id": "x"}, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    yield out
    client.put("/admin/integrations/resend", json={"clear": ["api_key", "from_email"]}, headers=superadmin)


def test_invite_without_email_configured_returns_token(client, tenant_a):
    r = client.post("/organizations/me/invitations", json={"email": "novo@t.com", "role": "MEMBER"}, headers=tenant_a)
    assert r.json()["emailed"] is False and r.json()["invite_token"]


def test_invite_is_emailed_and_token_not_returned(client, tenant_a, sent):
    r = client.post("/organizations/me/invitations", json={"email": "novo@t.com", "role": "EVENT_OPERATOR"}, headers=tenant_a)
    assert r.json() == {"emailed": True, "invite_token": None, "expires_days": 7}
    url, kw = sent[-1]
    assert url == "https://api.resend.com/emails" and kw["json"]["to"] == ["novo@t.com"]
    assert kw["headers"]["Authorization"] == "Bearer re_testkey_123456" and "/invite?token=" in kw["json"]["text"]


def test_invite_html_is_escaped(client, sent):
    h, _ = register(client, 'Igreja <script>alert(1)</script>')
    client.post("/organizations/me/invitations", json={"email": "x@t.com"}, headers=h)
    assert "<script>" not in sent[-1][1]["json"]["html"]


def test_forgot_is_neutral_and_reset_flow(client, sent):
    h, email = register(client)
    unknown = client.post("/auth/forgot", json={"email": "nao@existe.com"})
    known = client.post("/auth/forgot", json={"email": email})
    assert unknown.status_code == known.status_code == 202 and unknown.json() == known.json()   # sem enumeração
    assert len(sent) == 1                                                                         # só o existente recebe
    token = sent[0][1]["json"]["text"].split("token=")[1].split(" ")[0]
    assert client.post("/auth/reset", json={"token": token, "password": "curta"}).status_code == 422
    assert client.post("/auth/reset", json={"token": token, "password": NEWPW}).status_code == 200
    assert client.post("/auth/reset", json={"token": token, "password": NEWPW}).status_code == 400  # uso único
    assert client.post("/auth/login", json={"email": email, "password": PW}).status_code == 401      # senha antiga morreu
    assert client.post("/auth/login", json={"email": email, "password": NEWPW}).status_code == 200
    assert client.get("/events", headers=h).status_code == 200  # access token curto segue valendo até expirar (15 min)


def test_reset_invalid_token(client):
    assert client.post("/auth/reset", json={"token": "lixo", "password": NEWPW}).status_code == 400


def test_resend_validation(client, superadmin):
    put = lambda b: client.put("/admin/integrations/resend", json=b, headers=superadmin)
    assert put({"values": {"api_key": "abc"}}).status_code == 422
    assert put({"values": {"from_email": "sem-arroba"}}).status_code == 422
