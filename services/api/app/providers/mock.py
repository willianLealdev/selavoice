"""Provedor SIMULADO (determinístico) — usado em dev, testes e CI, sem chaves externas.

Não traduz de verdade: transforma frases de um roteiro em PT usando um mini-dicionário
(en/es) ou um prefixo [idioma]. Emite provisórios (texto crescendo) e depois o final,
exatamente como um provedor real faria. Aceita injeção de falha para testar failover.
"""
import asyncio
from typing import AsyncIterator

from .base import (LanguageCapability, ProviderHealth, ProviderSession, ProviderUnavailable,
                   TranslationEvent, TranslationProvider)

SCRIPT_PT = [
    "Bom dia a todos. Sejam muito bem-vindos à nossa sessão de abertura.",
    "Hoje vamos falar sobre três temas: crescimento, parcerias e o caminho à frente.",
    "Peço que encontrem seus lugares e silenciem os celulares.",
    "Nosso primeiro palestrante vem de São Paulo para estar conosco.",
    "As perguntas serão respondidas ao final de cada apresentação.",
    "Muito obrigado pela presença. Vamos começar.",
]

_DICT = {
    "en": {
        SCRIPT_PT[0]: "Good morning, everyone. Welcome to our opening session.",
        SCRIPT_PT[1]: "Today we will cover three topics: growth, partnerships and the road ahead.",
        SCRIPT_PT[2]: "Please find your seats and silence your phones.",
        SCRIPT_PT[3]: "Our first speaker joins us all the way from São Paulo.",
        SCRIPT_PT[4]: "Questions will be answered at the end of each presentation.",
        SCRIPT_PT[5]: "Thank you very much for being here. Let us begin.",
    },
    "es": {
        SCRIPT_PT[0]: "Buenos días a todos. Bienvenidos a nuestra sesión de apertura.",
        SCRIPT_PT[1]: "Hoy hablaremos de tres temas: crecimiento, alianzas y el camino por delante.",
        SCRIPT_PT[2]: "Les pedimos que busquen sus asientos y silencien sus teléfonos.",
        SCRIPT_PT[3]: "Nuestro primer orador viene desde São Paulo para estar con nosotros.",
        SCRIPT_PT[4]: "Las preguntas se responderán al final de cada presentación.",
        SCRIPT_PT[5]: "Muchas gracias por su presencia. Comencemos.",
    },
}


def mock_translate(text: str, lang: str) -> str:
    return _DICT.get(lang, {}).get(text, f"[{lang}] {text}")


class MockSession(ProviderSession):
    def __init__(self, source: str, target: str, fail_after: int | None, delay: float):
        self.source, self.target, self.fail_after, self.delay = source, target, fail_after, delay
        self._q: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._stopped = False
        self._emitted = 0

    async def push_audio(self, chunk: bytes) -> None:
        return None  # o simulador não usa áudio (e não pode acumular memória)

    async def stop(self) -> None:
        self._stopped = True
        await self._q.put(None)

    async def stream_events(self) -> AsyncIterator[TranslationEvent]:
        t = 0
        i = 0
        while not self._stopped:
            src = SCRIPT_PT[i % len(SCRIPT_PT)]
            i += 1
            full = mock_translate(src, self.target)
            words = full.split(" ")
            for n in range(2, len(words) + 1, max(1, len(words) // 3)):  # provisórios crescentes
                if self._stopped:
                    return
                await asyncio.sleep(self.delay)
                yield TranslationEvent(" ".join(words[:n]), False, t, t + 500 * n)
            await asyncio.sleep(self.delay)
            yield TranslationEvent(full, True, t, t + 500 * len(words))
            t += 500 * len(words)
            self._emitted += 1
            if self.fail_after is not None and self._emitted >= self.fail_after:
                raise ProviderUnavailable("falha simulada do provedor mock")


class MockProvider(TranslationProvider):
    name = "mock"
    streaming_implemented = True

    def __init__(self, fail_after: int | None = None, delay: float = 0.25, healthy: bool = True):
        self.fail_after, self.delay, self._healthy = fail_after, delay, healthy

    def configured(self) -> bool:
        from ..config import get_settings
        return not get_settings().is_prod  # o simulador NUNCA aparece em produção

    def list_languages(self) -> list[LanguageCapability]:
        return [LanguageCapability(l, True, True, verified=True)
                for l in ("en", "es", "pt", "fr", "de", "it", "zh", "ko", "ja", "ru", "ar", "hi")]

    async def start_session(self, source_language: str, target_language: str) -> ProviderSession:
        if not self._healthy:
            raise ProviderUnavailable("mock indisponível")
        return MockSession(source_language, target_language, self.fail_after, self.delay)

    async def health(self) -> ProviderHealth:
        return ProviderHealth(self._healthy, "simulador", 1.0)

    def estimated_cost(self, minutes: float, speech: bool = True) -> float:
        return 0.0
