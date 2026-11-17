"""Interface de provedores de tradução (spec: Provider abstraction).

Cada adaptador (Gemini, Azure, Mock) implementa `TranslationProvider`.
A MATRIZ DE CAPACIDADES diz, por idioma, se há texto e/ou voz de saída.
Valores marcados `verified=False` NÃO foram validados contra a documentação oficial
nem em teste real — a UI deve avisar (spec: nunca afirmar suporte sem verificar).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


class ProviderUnavailable(Exception):
    """Provedor sem credencial ou fora do ar (BLOCKED_EXTERNAL quando falta chave)."""


@dataclass
class LanguageCapability:
    language: str
    text_output: bool
    speech_output: bool
    verified: bool = False   # True só após teste real do fluxo completo
    discovered: bool = False  # True se a lista veio da API do provedor (e não de uma lista estática)


@dataclass
class TranslationEvent:
    """Evento normalizado, igual para qualquer provedor."""
    text: str
    is_final: bool
    start_ms: int = 0
    end_ms: int = 0
    audio: bytes | None = None  # chunk de áudio traduzido (Opus/PCM) quando houver
    original: str = ""          # texto ORIGINAL falado (quando o provedor devolve); `is_final` vale para ele se `text` vazio


@dataclass
class ProviderHealth:
    ok: bool
    detail: str = ""
    latency_ms: float | None = None


class TranslationProvider(ABC):
    name: str = "base"
    # False = o adaptador de tradução AO VIVO ainda não foi escrito/validado (BLOCKED_EXTERNAL). Mesmo com chave salva,
    # o provedor NÃO é oferecido ao público nem recebe canais: evita mostrar idiomas que ainda não funcionam de verdade.
    streaming_implemented: bool = False

    @abstractmethod
    def list_languages(self) -> list[LanguageCapability]: ...

    def configured(self) -> bool:
        """True se o provedor está habilitado e com credenciais (aí seus idiomas entram na lista do ouvinte)."""
        return True

    async def refresh_languages(self) -> None:
        """Atualiza a lista de idiomas consultando a API do provedor (quando ela oferece isso)."""
        return None

    def supports_speech_output(self, language: str) -> bool:
        return any(c.language == language and c.speech_output for c in self.list_languages())

    def supports_text_output(self, language: str) -> bool:
        return any(c.language == language and c.text_output for c in self.list_languages())

    @abstractmethod
    async def start_session(self, source_language: str, target_language: str) -> "ProviderSession": ...

    @abstractmethod
    async def health(self) -> ProviderHealth: ...

    @abstractmethod
    def estimated_cost(self, minutes: float, speech: bool = True) -> float:
        """Custo estimado em USD. Valores são ESTIMATIVAS configuráveis, não preços verificados."""


class ProviderSession(ABC):
    @abstractmethod
    async def push_audio(self, chunk: bytes) -> None: ...

    @abstractmethod
    def stream_events(self) -> AsyncIterator[TranslationEvent]: ...

    @abstractmethod
    async def stop(self) -> None: ...
