"""Painel de chaves: cifrado no banco, nunca devolvido, só super admin, auditado, trava do Stripe live."""
import json

import httpx
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ProviderConfig
from app.services import secrets_store as sec
from app.services.billing import stripe_signature

KEY = "AIzaSyFAKE-KEY-1234567890abcd"


def test_requires_super_admin(client, tenant_a):
    assert client.get("/admin/integrations", headers=tenant_a).status_code == 403
    assert client.put("/admin/integrations/gemini", json={"values": {"api_key": KEY}}, headers=tenant_a).status_code == 403


def test_save_is_encrypted_masked_and_audited(client, superadmin):
    r = client.put("/admin/integrations/gemini", json={"values": {"api_key": KEY}, "enabled": True}, headers=superadmin)
    assert r.status_code == 200
    f = r.json()["fields"]["api_key"]
    assert f["set"] and f["hint"] == "••••abcd" and KEY not in r.text
    assert KEY not in client.get("/admin/integrations", headers=superadmin).text      # nunca volta ao cliente
    with SessionLocal() as db:                                                          # no banco: cifrado
        raw = db.scalar(select(ProviderConfig).where(ProviderConfig.name == "gemini")).credentials_enc
    assert raw and KEY not in raw and "AIza" not in raw
    assert sec.get_secret("gemini", "api_key") == KEY                                   # o sistema consegue usar
    log = client.get("/admin/audit", headers=superadmin).text
    assert "admin.integration_update" in log and KEY not in log                         # auditoria sem o valor
    client.put("/admin/integrations/gemini", json={"values": {"api_key": ""}}, headers=superadmin)
    assert sec.get_secret("gemini", "api_key") == KEY                                   # vazio = mantém
    client.put("/admin/integrations/gemini", json={"clear": ["api_key"]}, headers=superadmin)
    assert sec.get_secret("gemini", "api_key") == ""                                    # clear = apaga


def test_validation_and_stripe_live_guard(client, superadmin):
    put = lambda n, b: client.put(f"/admin/integrations/{n}", json=b, headers=superadmin)
    assert put("gemini", {"values": {"api_key": "tem espaço"}}).status_code == 422
    assert put("nada", {"values": {}}).status_code == 404
    assert put("azure", {"values": {"region": "../x"}}).status_code == 422
    assert put("stripe", {"values": {"secret_key": "abc"}}).status_code == 422
    assert put("stripe", {"values": {"webhook_secret": "xyz"}}).status_code == 422
    assert put("stripe", {"values": {"secret_key": "sk_live_abcdef", "mode": "live"}}).status_code == 422  # sem confirmação
    assert put("stripe", {"values": {"secret_key": "sk_live_abcdef"}}).status_code == 422                   # chave live sem modo live
    assert put("stripe", {"values": {"secret_key": "sk_test_abcdef", "mode": "live"},
                          "confirm_live": "CONFIRMO COBRANCA REAL"}).status_code == 422                    # modo live com chave de teste
    assert put("stripe", {"values": {"secret_key": "sk_test_abcdef", "mode": "test"}}).status_code == 200
    put("stripe", {"clear": ["secret_key", "mode"]})


def test_stripe_webhook_uses_panel_secret(client, superadmin):
    client.put("/admin/integrations/stripe", json={"values": {"webhook_secret": "whsec_painel123"}}, headers=superadmin)
    body = json.dumps({"id": "evt_painel"}).encode()
    ok = client.post("/billing/webhook/stripe", content=body, headers={"Stripe-Signature": stripe_signature(body, "whsec_painel123")})
    old = client.post("/billing/webhook/stripe", content=body, headers={"Stripe-Signature": stripe_signature(body, "whsec_dev_fake_secret")})
    assert ok.status_code == 200 and old.status_code == 400          # só o segredo do painel vale agora
    client.put("/admin/integrations/stripe", json={"clear": ["webhook_secret"]}, headers=superadmin)


def test_connection_test_never_leaks_key(client, superadmin, monkeypatch):
    client.put("/admin/integrations/deepseek", json={"values": {"api_key": "sk-secretvalue9999"}}, headers=superadmin)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(401, request=httpx.Request("GET", a[0])))
    r = client.post("/admin/integrations/deepseek/test", headers=superadmin)
    assert r.json()["ok"] is False and "RECUSADA" in r.json()["detail"] and "secretvalue" not in r.text
    monkeypatch.setattr(httpx, "get", lambda *a, **k: httpx.Response(200, request=httpx.Request("GET", a[0])))
    assert client.post("/admin/integrations/deepseek/test", headers=superadmin).json()["ok"] is True
    client.put("/admin/integrations/deepseek", json={"clear": ["api_key"]}, headers=superadmin)
    assert client.post("/admin/integrations/gemini/test", headers=superadmin).json()["ok"] is False   # sem chave
