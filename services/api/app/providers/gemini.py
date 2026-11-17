"""Gemini 3.5 Live Translate — tradução de voz em tempo real (adaptador REAL).

PROTOCOLO (documentação oficial, ai.google.dev/gemini-api/docs/live-api/live-translate):
  - WebSocket  wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key=...
  - 1ª mensagem  {"setup": {"model": "models/gemini-3.5-live-translate-preview", "inputAudioTranscription": {},
                  "outputAudioTranscription": {}, "generationConfig": {"responseModalities": ["AUDIO"],
                  "translationConfig": {"targetLanguageCode": "<idioma>", "echoTargetLanguage": false}}}}
  - Áudio de entrada: {"realtimeInput": {"audio": {"data": <base64 PCM16 16 kHz mono>, "mimeType": "audio/pcm;rate=16000"}}}
  - Saída: serverContent.modelTurn.parts[].inlineData.data (PCM16 24 kHz mono = VOZ traduzida),
           serverContent.outputTranscription.text (TEXTO traduzido), serverContent.inputTranscription.text (texto original).
  - Não há campo de idioma de ORIGEM: o Gemini detecta sozinho.

DECISÕES:
  - A chave vai na URL (é o que a API exige) e NUNCA aparece em logs/erros (mensagens de erro são genéricas).
  - Conexão PREGUIÇOSA: só abre o WebSocket quando chega o primeiro áudio (canal sem áudio não gasta nada).
  - A doc não define "fim de frase" para a transcrição: finalizamos quando chega turnComplete/generationComplete, quando o texto
    termina em pontuação final e já é longo, ou após `IDLE_FINAL_S` sem texto novo.
  - Se o modelo mudar de nome, troque MODEL (ou configure no painel no futuro). Preview = pode mudar sem aviso.
"""
import asyncio
import base64
import json
import logging
import time
from typing import AsyncIterator

from ..services.secrets_store import get_secret, is_enabled
from .base import (LanguageCapability, ProviderHealth, ProviderSession, ProviderUnavailable, TranslationEvent,
                   TranslationProvider)
from .gemini_languages import GEMINI_LANGS, api_code

log = logging.getLogger("selavoice.gemini")

# Último erro de conexão (texto seguro, sem a chave) — alimenta o painel e tira o provedor do ar por alguns minutos,
# para não ficar tentando (e falhando) a cada ouvinte quando, por exemplo, os créditos acabaram.
LAST_ERROR: dict = {"msg": "", "at": 0.0, "ok_at": 0.0}
ERROR_COOLDOWN_S = 300


_probe_lock = asyncio.Lock()
PROBE_OK_TTL_S = 120


async def _probe() -> None:
    """Teste de conexão REAL (só o aperto de mão: conecta, envia a configuração e espera `setupComplete`).
    Não envia áudio, então não gera custo de tradução. Atualiza LAST_ERROR (vazio = tudo certo)."""
    import websockets
    key = get_secret("gemini", "api_key")
    try:
        ws = await asyncio.wait_for(websockets.connect(f"{URL}?key={key}", open_timeout=8), 10)
        await ws.send(json.dumps({"setup": {"model": MODEL, "generationConfig": {"responseModalities": ["AUDIO"],
                                  "translationConfig": {"targetLanguageCode": "en"}}}}))
        first = json.loads(await asyncio.wait_for(ws.recv(), 10))
        await ws.close()
        LAST_ERROR.update(msg="" if "setupComplete" in first else "O Google não aceitou a configuração da sessão.", at=time.time(), ok_at=time.time())
    except websockets.ConnectionClosed as e:
        LAST_ERROR.update(msg=_friendly(e.rcvd.reason if e.rcvd else ""), at=time.time())
    except Exception as e:
        LAST_ERROR.update(msg=f"Não foi possível conectar ao Google ({type(e).__name__}).", at=time.time())


def _friendly(reason: str) -> str:
    r = (reason or "").lower()
    if "credit" in r or "billing" in r or "quota" in r:
        return "Créditos/cota da conta Google esgotados (adicione crédito no Google AI Studio)."
    if "api key" in r or "permission" in r or "unauthenticated" in r:
        return "Chave do Gemini recusada pelo Google."
    return "O Google encerrou a conexão: " + (reason or "motivo não informado")[:160]

MODEL = "models/gemini-3.5-live-translate-preview"
URL = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent"
SEND_BYTES = 3200      # ~100 ms de PCM16 16 kHz (tamanho recomendado pela documentação)
IDLE_FINAL_S = 3.0     # sem texto novo por este tempo => fecha a frase (o Gemini pode pausar ~1,5 s no meio de uma frase)
MIN_SENTENCE = 8       # um "." solto (ex.: "Sr.") não fecha frase: precisa de um mínimo de texto
END_PUNCT = (".", "!", "?", "。", "！", "？", "…")
SILENCE_RMS = 40       # quadros de voz mais quietos que isto são descartados (o Gemini manda áudio mudo entre falas)


def _is_silent(pcm: bytes) -> bool:
    """True se o trecho PCM16 é (quase) silêncio. Amostra 1 em cada 8 para ser barato."""
    import array
    import math
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    sample = a[::8] or a
    return math.sqrt(sum(x * x for x in sample) / len(sample)) < SILENCE_RMS if len(sample) else True


class _Sentences:
    """Junta os pedacinhos de texto do Gemini em FRASES: fecha ao chegar texto novo depois de uma pontuação final,
    no fim do turno (flush) ou após IDLE_FINAL_S sem texto novo (idle)."""
    def __init__(self) -> None:
        self.text, self.at = "", 0.0

    def add(self, t: str) -> list[tuple[str, bool]]:
        out: list[tuple[str, bool]] = []
        if len(self.text.strip()) >= MIN_SENTENCE and self.text.rstrip().endswith(END_PUNCT):
            out.append((self.text.strip(), True))
            self.text, t = "", t.lstrip()
        self.text += t
        self.at = time.monotonic()
        if self.text.strip():
            out.append((self.text.strip(), False))
        return out

    def flush(self) -> tuple[str, bool] | None:
        if not self.text.strip():
            return None
        r, self.text = (self.text.strip(), True), ""
        return r

    def idle(self) -> tuple[str, bool] | None:
        return self.flush() if self.text and time.monotonic() - self.at >= IDLE_FINAL_S else None


class GeminiSession(ProviderSession):
    def __init__(self, target: str) -> None:
        self.target = target
        self._ws = None
        self._reader: asyncio.Task | None = None
        self._out: asyncio.Queue[TranslationEvent | Exception | None] = asyncio.Queue()
        self._buf = bytearray()
        self._acc_out, self._acc_in = _Sentences(), _Sentences()
        self._connecting = asyncio.Lock()
        self._stopped = False
        self.first_audio_at: float | None = None     # para medir latência real (1º áudio enviado -> 1º texto recebido)
        self.first_text_latency: float | None = None

    # ---------- conexão ----------
    async def _ensure(self) -> None:
        if self._ws is not None or self._stopped:
            return
        async with self._connecting:
            if self._ws is not None or self._stopped:
                return
            import websockets
            key = get_secret("gemini", "api_key")
            try:
                ws = await asyncio.wait_for(websockets.connect(f"{URL}?key={key}", max_size=8 * 2**20, open_timeout=10), 12)
                await ws.send(json.dumps({"setup": {
                    "model": MODEL, "inputAudioTranscription": {}, "outputAudioTranscription": {},
                    "generationConfig": {"responseModalities": ["AUDIO"],
                                         "translationConfig": {"targetLanguageCode": api_code(self.target), "echoTargetLanguage": False}}}}))
                first = json.loads(await asyncio.wait_for(ws.recv(), 12))
            except websockets.ConnectionClosed as e:   # o Google explica o motivo (não contém a chave)
                msg = _friendly(e.rcvd.reason if e.rcvd else "")
                LAST_ERROR.update(msg=msg, at=time.time())
                raise ProviderUnavailable(f"Gemini: {msg}") from None
            except Exception as e:  # SEM detalhes: a URL contém a chave
                LAST_ERROR.update(msg=f"falha ao conectar ({type(e).__name__})", at=time.time())
                raise ProviderUnavailable(f"Gemini: falha ao conectar ({type(e).__name__})") from None
            if "setupComplete" not in first:
                await ws.close()
                raise ProviderUnavailable("Gemini: o serviço recusou a configuração da sessão")
            self._ws = ws
            self._reader = asyncio.create_task(self._read())

    async def push_audio(self, chunk: bytes) -> None:
        if self._stopped:
            return
        self._buf += chunk
        if len(self._buf) < SEND_BYTES:
            return
        data, self._buf = bytes(self._buf), bytearray()
        try:
            await self._ensure()
            if self.first_audio_at is None:
                self.first_audio_at = time.monotonic()
            await self._ws.send(json.dumps({"realtimeInput": {"audio": {"data": base64.b64encode(data).decode(), "mimeType": "audio/pcm;rate=16000"}}}))
        except ProviderUnavailable as e:
            await self._out.put(e)
        except Exception:
            await self._out.put(ProviderUnavailable("Gemini: conexão perdida ao enviar áudio"))

    # ---------- leitura ----------
    def _emit(self, which: str, item: tuple[str, bool] | None) -> None:
        if not item:
            return
        text, final = item
        self._out.put_nowait(TranslationEvent(text=text, is_final=final) if which == "out"
                             else TranslationEvent(text="", is_final=final, original=text))

    async def _read(self) -> None:
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(self._ws.recv(), 0.4)
                except asyncio.TimeoutError:
                    raw = None
                # frase aberta há mais de IDLE_FINAL_S sem texto novo => fecha (mesmo que o áudio continue chegando)
                self._emit("out", self._acc_out.idle())
                self._emit("in", self._acc_in.idle())
                if raw is None:
                    continue
                msg = json.loads(raw)
                sc = msg.get("serverContent")
                if not sc:
                    continue
                for part in (sc.get("modelTurn") or {}).get("parts", []):
                    d = (part.get("inlineData") or {}).get("data")
                    if d:
                        pcm = base64.b64decode(d)
                        if not _is_silent(pcm):     # silêncio não é enviado aos ouvintes (economiza banda)
                            self._out.put_nowait(TranslationEvent(text="", is_final=False, audio=pcm))
                t = (sc.get("outputTranscription") or {}).get("text")
                if t:
                    if self.first_text_latency is None and self.first_audio_at:
                        self.first_text_latency = time.monotonic() - self.first_audio_at
                    for item in self._acc_out.add(t):
                        self._emit("out", item)
                ti = (sc.get("inputTranscription") or {}).get("text")
                if ti:   # o que o palestrante FALOU (idioma original): serve ao documento pós-evento (reserva do Deepgram)
                    for item in self._acc_in.add(ti):
                        self._emit("in", item)
                if sc.get("turnComplete") or sc.get("generationComplete"):
                    self._emit("out", self._acc_out.flush())
                    self._emit("in", self._acc_in.flush())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self._stopped:
                import websockets
                if isinstance(e, websockets.ConnectionClosed) and e.rcvd and e.rcvd.reason:
                    LAST_ERROR.update(msg=_friendly(e.rcvd.reason), at=time.time())
                log.warning("gemini: leitura encerrada (%s)", type(e).__name__)
                await self._out.put(ProviderUnavailable("Gemini: conexão encerrada"))
        finally:
            await self._out.put(None)

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
        if self._reader:
            self._reader.cancel()
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        await self._out.put(None)


class GeminiProvider(TranslationProvider):
    name = "gemini"
    streaming_implemented = True   # adaptador escrito conforme a documentação; validação REAL só com teste (ver docs/BLOCKERS.md)

    def configured(self) -> bool:
        return bool(get_secret("gemini", "api_key") and is_enabled("gemini"))

    def list_languages(self) -> list[LanguageCapability]:
        # Tabela da DOCUMENTAÇÃO (a API não lista idiomas): texto + voz, ainda não verificados idioma a idioma.
        return [LanguageCapability(code, True, True, verified=False, discovered=False) for code in GEMINI_LANGS]

    async def start_session(self, source_language: str, target_language: str) -> ProviderSession:
        if not self.configured():
            raise ProviderUnavailable("BLOCKED_EXTERNAL: chave do Gemini ausente/desativada (Super Admin > Integrações)")
        if target_language not in GEMINI_LANGS:
            raise ProviderUnavailable("Gemini: idioma de destino não suportado")
        return GeminiSession(target_language)   # a conexão só abre quando o 1º áudio chegar

    async def health(self) -> ProviderHealth:
        if not get_secret("gemini", "api_key"):
            return ProviderHealth(False, "BLOCKED_EXTERNAL: sem GEMINI_API_KEY")
        if not is_enabled("gemini"):
            return ProviderHealth(False, "desativado no painel")
        # Sem chamada de rede aqui (health roda a cada decisão de canal). Falhas reais abrem o circuit breaker.
        now = time.time()
        stale = now - LAST_ERROR["at"] > (ERROR_COOLDOWN_S if LAST_ERROR["msg"] else PROBE_OK_TTL_S)
        if stale:
            async with _probe_lock:
                if time.time() - LAST_ERROR["at"] > (ERROR_COOLDOWN_S if LAST_ERROR["msg"] else PROBE_OK_TTL_S):
                    await _probe()
        if LAST_ERROR["msg"]:
            return ProviderHealth(False, LAST_ERROR["msg"])
        return ProviderHealth(True, "conexão com o Google OK; tradução ao vivo habilitada")

    def estimated_cost(self, minutes: float, speech: bool = True) -> float:
        return round(minutes * 0.05, 4)  # PLACEHOLDER: configure a tarifa real em Custos e receita
