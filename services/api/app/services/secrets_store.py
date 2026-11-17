"""Cofre de chaves de integração, editável pelo Super Admin no painel.

SEGURANÇA
- Valores ficam CIFRADOS (Fernet) em `provider_configs.credentials_enc`; nunca em texto puro.
- A API NUNCA devolve o valor: só "configurada" + últimos 4 caracteres.
- Auditoria registra QUAIS campos mudaram, jamais os valores.
- Prioridade de leitura: banco (painel) > variável de ambiente (.env).
- O cache é local ao processo e é limpo a cada gravação (várias réplicas: reiniciar/usar Redis).
"""
import json
import re

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import ProviderConfig
from ..security import decrypt_secret, encrypt_secret

settings = get_settings()

# Catálogo: o que cada integração aceita. secret=True => nunca exibido. env = variável de fallback.
CATALOG: dict[str, dict] = {
    "gemini": {"label": "Google Gemini Live (tradução principal)", "fields": {
        "api_key": {"label": "API Key", "secret": True, "env": "gemini_api_key"}}},
    "azure": {"label": "Azure Speech (tradução reserva)", "fields": {
        "key": {"label": "Speech Key", "secret": True, "env": "azure_speech_key"},
        "region": {"label": "Região (ex.: eastus)", "secret": False, "env": "azure_speech_region"}}},
    "deepgram": {"label": "Deepgram (transcrição do original)", "fields": {
        "api_key": {"label": "API Key", "secret": True, "env": "deepgram_api_key"}}},
    "deepseek": {"label": "DeepSeek (somente edição da apostila)", "fields": {
        "api_key": {"label": "API Key", "secret": True, "env": "deepseek_api_key"}}},
    "resend": {"label": "Resend (envio de e-mails: convites e recuperação de senha)", "fields": {
        "api_key": {"label": "API Key (re_…)", "secret": True, "env": "resend_api_key"},
        "from_email": {"label": "E-mail remetente (domínio verificado no Resend)", "secret": False, "env": "resend_from_email"}}},
    "stripe": {"label": "Stripe (pagamentos)", "fields": {
        "secret_key": {"label": "Secret Key (sk_test_… ou sk_live_…)", "secret": True, "env": "stripe_secret_key"},
        "webhook_secret": {"label": "Webhook Signing Secret (whsec_…)", "secret": True, "env": "stripe_webhook_secret"},
        "mode": {"label": "Modo: fake | test | live", "secret": False, "env": "stripe_mode"}}},
}

_cache: dict[str, dict] | None = None
_VALUE_RE = re.compile(r"^[\x21-\x7e]{1,500}$")  # ASCII visível, sem espaços/quebras de linha


def invalidate() -> None:
    global _cache
    _cache = None


def _load_all() -> dict[str, dict]:
    global _cache
    if _cache is None:
        data: dict[str, dict] = {}
        with SessionLocal() as db:
            for row in db.scalars(select(ProviderConfig)):
                try:
                    data[row.name] = json.loads(decrypt_secret(row.credentials_enc)) if row.credentials_enc else {}
                except Exception:  # chave de cifra trocada/dado corrompido: trata como vazio (não derruba o app)
                    data[row.name] = {}
        _cache = data
    return _cache


def get_secret(provider: str, field: str) -> str:
    """Valor efetivo (painel > .env). String vazia se não configurado."""
    v = _load_all().get(provider, {}).get(field)
    if v:
        return v
    env = CATALOG[provider]["fields"][field]["env"]
    return str(getattr(settings, env, "") or "")


def is_enabled(provider: str) -> bool:
    with SessionLocal() as db:
        row = db.scalar(select(ProviderConfig).where(ProviderConfig.name == provider))
        return True if row is None else bool(row.enabled)


def validate_values(provider: str, values: dict) -> dict[str, str]:
    """Valida campos recebidos; devolve só os não vazios. Levanta ValueError com mensagem em pt-BR."""
    spec = CATALOG[provider]["fields"]
    out: dict[str, str] = {}
    for k, v in values.items():
        if k not in spec:
            raise ValueError(f"Campo desconhecido: {k}")
        v = (v or "").strip()
        if not v:
            continue  # vazio = manter o atual
        if not _VALUE_RE.match(v):
            raise ValueError(f"Valor inválido em “{spec[k]['label']}” (sem espaços/quebras de linha, até 500 caracteres).")
        out[k] = v
    if provider == "azure" and "region" in out and not re.fullmatch(r"[a-z0-9]{3,30}", out["region"]):
        raise ValueError("Região do Azure inválida (ex.: eastus, brazilsouth).")
    if provider == "resend":
        if "from_email" in out and not re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", out["from_email"]):
            raise ValueError("E-mail remetente inválido (ex.: no-reply@seudominio.com).")
        if "api_key" in out and not out["api_key"].startswith("re_"):
            raise ValueError("A API Key do Resend começa com re_.")
    if provider == "stripe":
        if "mode" in out and out["mode"] not in ("fake", "test", "live"):
            raise ValueError("Modo do Stripe deve ser fake, test ou live.")
        if "secret_key" in out and not out["secret_key"].startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
            raise ValueError("A Secret Key do Stripe deve começar com sk_test_ ou sk_live_.")
        if "webhook_secret" in out and not out["webhook_secret"].startswith("whsec_"):
            raise ValueError("O Webhook Secret do Stripe deve começar com whsec_.")
    return out


def save(provider: str, values: dict[str, str], clear: list[str], enabled: bool | None) -> list[str]:
    """Grava (mescla) valores cifrados. Retorna a lista de campos alterados (sem valores)."""
    with SessionLocal() as db:
        row = db.scalar(select(ProviderConfig).where(ProviderConfig.name == provider))
        if row is None:
            row = ProviderConfig(name=provider, enabled=True)
            db.add(row)
        cur = json.loads(decrypt_secret(row.credentials_enc)) if row.credentials_enc else {}
        changed = []
        for k, v in values.items():
            cur[k] = v
            changed.append(k)
        for k in clear:
            if k in CATALOG[provider]["fields"] and cur.pop(k, None) is not None:
                changed.append(f"-{k}")
        row.credentials_enc = encrypt_secret(json.dumps(cur)) if cur else None
        if enabled is not None:
            row.enabled = enabled
            changed.append(f"enabled={enabled}")
        db.commit()
    invalidate()
    return changed


def describe(provider: str) -> dict:
    """Estado para a tela: NUNCA inclui o valor, só se existe e os 4 últimos caracteres."""
    stored = _load_all().get(provider, {})
    fields = {}
    for k, spec in CATALOG[provider]["fields"].items():
        val = get_secret(provider, k)
        src = "painel" if stored.get(k) else ("ambiente" if val else "")
        item = {"label": spec["label"], "secret": spec["secret"], "set": bool(val), "source": src}
        if val:
            item["hint"] = ("••••" + val[-4:]) if spec["secret"] else val  # não-secretos (região/modo) podem aparecer
        fields[k] = item
    return {"name": provider, "label": CATALOG[provider]["label"], "enabled": is_enabled(provider), "fields": fields}
