"""Azure Speech — tradução de voz em tempo real (adaptador REAL, via SDK oficial `azure-cognitiveservices-speech`).

STATUS: escrito conforme o SDK oficial, MAS NUNCA EXECUTADO contra o serviço (falta chave/região do Azure). Só funções
puras (mapa de idiomas, reamostragem, escolha de voz) têm teste automatizado. Validar com chave real é obrigatório.

Fluxo: áudio PCM16 16 kHz -> PushAudioInputStream -> TranslationRecognizer (reconhecimento contínuo) ->
  - `recognizing` (parcial) e `recognized` (final) com o TEXTO traduzido;
  - `synthesizing` com a VOZ traduzida (PCM 16 kHz), que reamostramos para 24 kHz para o ouvinte tocar igual ao Gemini.
O Azure PRECISA do idioma de origem (ex.: pt-BR) — o Gemini detecta sozinho, o Azure não (neste modo).
Os callbacks do SDK rodam em threads próprias: repassamos ao asyncio com `call_soon_threadsafe`.
"""
import asyncio
import array
import logging
from typing import AsyncIterator

from ..services.secrets_store import get_secret
from .base import ProviderSession, ProviderUnavailable, TranslationEvent

log = logging.getLogger("selavoice.azure")

# Idioma de origem "pt" -> locale que o Azure exige. Locale já completo (pt-BR) passa direto; senão tenta a lista de vozes.
SOURCE_LOCALE = {"pt": "pt-BR", "en": "en-US", "es": "es-ES", "fr": "fr-FR", "de": "de-DE", "it": "it-IT", "zh": "zh-CN",
                 "ja": "ja-JP", "ko": "ko-KR", "ru": "ru-RU", "ar": "ar-SA", "hi": "hi-IN", "nl": "nl-NL", "pl": "pl-PL",
                 "tr": "tr-TR", "sv": "sv-SE", "uk": "uk-UA", "vi": "vi-VN", "th": "th-TH", "id": "id-ID"}
# Idioma de destino: nosso código -> código do Azure Translator (só onde difere)
TARGET_CODE = {"zh": "zh-Hans"}


def source_locale(lang: str, voices: list[dict] | None = None) -> str:
    if "-" in lang:
        return lang
    if lang in SOURCE_LOCALE:
        return SOURCE_LOCALE[lang]
    for v in voices or []:
        loc = str(v.get("Locale", ""))
        if loc.split("-")[0].lower() == lang.lower():
            return loc
    return f"{lang}-{lang.upper()}"  # último recurso (pode não existir; o Azure responderá erro e o failover age)


def target_code(lang: str) -> str:
    return TARGET_CODE.get(lang, lang)


def pick_voice(lang: str, voices: list[dict]) -> str | None:
    """Primeira voz NEURAL cujo idioma-base é o do destino (None = sem voz: só texto)."""
    base = lang.split("-")[0].lower()
    cand = [v for v in voices if str(v.get("Locale", "")).split("-")[0].lower() == base and "Neural" in str(v.get("VoiceType", "Neural"))]
    pref = [v for v in cand if str(v.get("Locale", "")).lower() == lang.lower()] or cand
    return pref[0]["ShortName"] if pref else None


def resample_16k_to_24k(pcm: bytes) -> bytes:
    """Interpolação linear 16 kHz -> 24 kHz (3 amostras de saída para cada 2 de entrada). Suficiente para voz."""
    if len(pcm) < 4:
        return pcm
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    out = array.array("h")
    n = len(a)
    for j in range(int(n * 1.5)):
        pos = j / 1.5
        i = int(pos)
        frac = pos - i
        nxt = a[i + 1] if i + 1 < n else a[i]
        out.append(int(a[i] + (nxt - a[i]) * frac))
    return out.tobytes()


class AzureSession(ProviderSession):
    def __init__(self, source: str, target: str, voices: list[dict]) -> None:
        self.source, self.target = source_locale(source, voices), target_code(target)
        self.voice = pick_voice(target, voices)
        self._loop = asyncio.get_running_loop()
        self._out: asyncio.Queue[TranslationEvent | Exception | None] = asyncio.Queue()
        self._rec = None
        self._stream = None
        self._stopped = False
        self._first_riff = True

    def _emit(self, item) -> None:   # chamado de threads do SDK
        self._loop.call_soon_threadsafe(self._out.put_nowait, item)

    def _start(self) -> None:
        try:
            import azure.cognitiveservices.speech as sdk
        except ImportError:
            raise ProviderUnavailable("Azure: SDK não instalado (pip install azure-cognitiveservices-speech)") from None
        cfg = sdk.translation.SpeechTranslationConfig(subscription=get_secret("azure", "key"), region=get_secret("azure", "region"))
        cfg.speech_recognition_language = self.source
        cfg.add_target_language(self.target)
        if self.voice:
            cfg.voice_name = self.voice    # sem voz definida o Azure não envia áudio sintetizado
        fmt = sdk.audio.AudioStreamFormat(samples_per_second=16000, bits_per_sample=16, channels=1)
        self._stream = sdk.audio.PushAudioInputStream(stream_format=fmt)
        rec = sdk.translation.TranslationRecognizer(translation_config=cfg, audio_config=sdk.audio.AudioConfig(stream=self._stream))

        def text_of(evt) -> str:
            tr = evt.result.translations or {}
            return (tr.get(self.target) or next(iter(tr.values()), "")).strip()

        rec.recognizing.connect(lambda e: self._emit(TranslationEvent(text=text_of(e), is_final=False)) if text_of(e) else None)
        rec.recognized.connect(lambda e: self._emit(TranslationEvent(text=text_of(e), is_final=True)) if text_of(e) else None)

        def on_synth(e) -> None:
            data = bytes(e.result.audio or b"")
            if self._first_riff and data[:4] == b"RIFF":    # 1º bloco traz cabeçalho WAV (44 bytes)
                data = data[44:]
            self._first_riff = False
            if data:
                self._emit(TranslationEvent(text="", is_final=False, audio=resample_16k_to_24k(data)))
        rec.synthesizing.connect(on_synth)

        def on_cancel(e) -> None:
            det = getattr(e.result, "cancellation_details", None)
            reason = (getattr(det, "error_details", "") or "cancelado")[:160]
            log.warning("azure: reconhecimento cancelado")
            self._emit(ProviderUnavailable(f"Azure: {reason}"))
        rec.canceled.connect(on_cancel)
        rec.session_stopped.connect(lambda e: self._emit(None))
        rec.start_continuous_recognition_async().get()
        self._rec = rec

    async def push_audio(self, chunk: bytes) -> None:
        if self._stopped:
            return
        try:
            if self._rec is None:                              # conexão preguiçosa: só quando o 1º áudio chega
                await self._loop.run_in_executor(None, self._start)
            self._stream.write(chunk)
        except ProviderUnavailable as e:
            await self._out.put(e)
        except Exception as e:
            await self._out.put(ProviderUnavailable(f"Azure: falha ({type(e).__name__})"))

    async def stream_events(self) -> AsyncIterator[TranslationEvent]:
        while True:
            item = await self._out.get()
            if item is None:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    async def stop(self) -> None:
        self._stopped = True
        try:
            if self._stream is not None:
                self._stream.close()
            if self._rec is not None:
                await self._loop.run_in_executor(None, lambda: self._rec.stop_continuous_recognition_async().get())
        except Exception:
            pass
        await self._out.put(None)
