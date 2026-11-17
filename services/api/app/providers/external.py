"""Adaptadores dos provedores reais: Gemini Live (primário) e Azure Speech (fallback).

STATUS: BLOCKED_EXTERNAL — sem chaves de sandbox não é possível validar de ponta a ponta.
O que está pronto: interface, matriz de capacidade (VERIFIED=False), detecção de chave,
estimativa de custo configurável e contrato de eventos normalizados.
O que falta (exige chave + conta): abrir o WebSocket real, enviar PCM 16 kHz, ler o áudio/
texto traduzidos e medir latência/custo. Ver docs/BLOCKERS.md.

NÃO afirmamos número de idiomas com voz, latência de 2 s, nem preço fixo: tudo isso é
configurável e deve ser MEDIDO em staging (spec: Definition of Done).
"""
import logging
import time

import httpx

from ..services.secrets_store import get_secret, is_enabled

log = logging.getLogger("selavoice.providers")
from .base import (LanguageCapability, ProviderHealth, ProviderSession, ProviderUnavailable,
                   TranslationProvider)



from .gemini import GeminiProvider  # noqa: E402,F401  (adaptador real em gemini.py)


def parse_azure_languages(voices: list[dict], translator: dict) -> list[LanguageCapability]:
    """Junta (a) idiomas de TEXTO do Azure Translator e (b) idiomas com VOZ (locales da lista de vozes do Speech).
    Voz: usa o código-base do locale (pt-BR -> pt). Idiomas só com voz também entram (a tradução de texto pode vir de outro serviço)."""
    text = set((translator.get("translation") or {}).keys())
    speech = {str(v.get("Locale", "")).split("-")[0].lower() for v in voices if v.get("Locale")}
    out = []
    for code in sorted(text | speech):
        base = code.split("-")[0].lower()
        out.append(LanguageCapability(code, code in text, (code.lower() in speech) or (base in speech),
                                      verified=False, discovered=True))
    return out


class AzureProvider(TranslationProvider):
    name = "azure"
    streaming_implemented = True   # adaptador escrito com o SDK oficial; NUNCA executado contra o serviço (sem chave)
    _TTL = 6 * 3600  # relê a lista a cada 6 h
    _HEALTH_TTL = 300

    def __init__(self) -> None:
        self._langs: list[LanguageCapability] | None = None
        self._at = 0.0
        self._voices: list[dict] = []      # vozes descobertas (escolhe a voz de cada idioma de destino)
        self._health: tuple[float, ProviderHealth] | None = None

    def configured(self) -> bool:
        return bool(get_secret("azure", "key") and get_secret("azure", "region") and is_enabled("azure"))

    def list_languages(self) -> list[LanguageCapability]:
        # Lista descoberta pela API (quando disponível); senão, uma lista estática MÍNIMA e NÃO verificada.
        return self._langs or [LanguageCapability(l, True, True, verified=False) for l in ("en", "es", "pt", "fr", "de", "it", "zh")]

    async def _fetch(self) -> tuple[list[dict], dict]:
        region = get_secret("azure", "region")
        async with httpx.AsyncClient(timeout=15) as c:
            v = await c.get(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                            headers={"Ocp-Apim-Subscription-Key": get_secret("azure", "key")})
            v.raise_for_status()
            t = await c.get("https://api.cognitive.microsofttranslator.com/languages",
                            params={"api-version": "3.0", "scope": "translation"})  # lista pública, sem chave
            t.raise_for_status()
        return v.json(), t.json()

    async def refresh_languages(self) -> None:
        if not self.configured() or (self._langs and time.time() - self._at < self._TTL):
            return
        try:
            voices, tr = await self._fetch()
            self._voices = voices
            self._langs, self._at = parse_azure_languages(voices, tr), time.time()
        except Exception as e:  # sem rede/chave inválida: mantém a lista anterior, nunca derruba a API
            log.warning("azure: descoberta de idiomas falhou (%s)", type(e).__name__)

    async def start_session(self, source_language: str, target_language: str) -> ProviderSession:
        if not self.configured():
            raise ProviderUnavailable("BLOCKED_EXTERNAL: chave/região do Azure ausentes (Super Admin > Integrações)")
        if not self._voices:
            await self.refresh_languages()   # precisa das vozes para escolher a voz do idioma de destino
        from .azure_session import AzureSession
        return AzureSession(source_language, target_language, self._voices)   # conexão só abre com o 1º áudio

    async def health(self) -> ProviderHealth:
        if not get_secret("azure", "key") or not get_secret("azure", "region"):
            return ProviderHealth(False, "BLOCKED_EXTERNAL: sem chave/região do Azure")
        if not is_enabled("azure"):
            return ProviderHealth(False, "desativado no painel")
        if self._health and time.time() - self._health[0] < self._HEALTH_TTL:
            return self._health[1]
        try:   # teste leve de autenticação (lista de vozes); não envia áudio, não gera custo de tradução
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(f"https://{get_secret('azure', 'region')}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                                headers={"Ocp-Apim-Subscription-Key": get_secret("azure", "key")})
            h = ProviderHealth(True, "chave aceita pelo Azure; tradução ao vivo habilitada (não validada de ponta a ponta)") if r.status_code == 200                 else ProviderHealth(False, "chave/região recusadas pelo Azure" if r.status_code in (401, 403) else f"Azure respondeu HTTP {r.status_code}")
        except httpx.HTTPError:
            h = ProviderHealth(False, "Não foi possível conectar ao Azure")
        self._health = (time.time(), h)
        return h

    def estimated_cost(self, minutes: float, speech: bool = True) -> float:
        return round(minutes * 0.04, 4)  # PLACEHOLDER
