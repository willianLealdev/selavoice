"""Transcrição do ORIGINAL ao vivo (o que o palestrante fala, no idioma dele) — Deepgram.

POR QUE: o documento pós-evento é feito a partir da transcrição ORIGINAL. Sem isto ela só existia se alguém colasse o texto.
Uma conexão por SESSÃO (não por idioma): o mesmo áudio do palestrante alimenta o Deepgram, independente de haver ouvintes.

PROTOCOLO (Deepgram, streaming): wss://api.deepgram.com/v1/listen?model=nova-3&language=..&encoding=linear16&sample_rate=16000&channels=1
  - auth no cabeçalho  `Authorization: Token <chave>`; áudio PCM16 em quadros binários; mensagens JSON `Results`
    com channel.alternatives[0].transcript, `is_final` (trecho firme) e `speech_final` (fim da fala/pausa).
  - `KeepAlive` a cada 5 s se não houver áudio; `CloseStream` ao terminar.
DECISÕES:
  - Trechos `is_final` são ACUMULADOS até `speech_final` e gravados como UM segmento final (parágrafo natural para o documento).
  - O texto parcial aparece como segmento provisório (revisões) — mas NÃO é publicado aos ouvintes (publish=False): ouvinte vê
    só a tradução; o original serve ao documento e à equipe.
  - Se o Deepgram falhar/não tiver chave, `active()` vira False e o Gemini (que também devolve o texto original) assume.
  - Sem áudio por IDLE_CLOSE_S, a conexão fecha (não gasta crédito parada).
"""
import asyncio
import json
import logging
import time
from urllib.parse import urlencode

from .secrets_store import get_secret, is_enabled
from .transcripts import write_segment

log = logging.getLogger("selavoice.asr")

URL = "wss://api.deepgram.com/v1/listen"
MODEL = "nova-3"
IDLE_CLOSE_S = 90
LOW_CONF = 0.5          # abaixo disto (em trechos de 3+ palavras) a fala é tratada como ininteligível no idioma do evento
LOW_HOLD_S = 4.0        # por quantos segundos o "ininteligível" vale depois de detectado
_low_until: dict[str, float] = {}
KEEPALIVE_S = 5
# nosso idioma de origem -> código do Deepgram (só onde difere)
DG_LANG = {"pt": "pt-BR", "en": "en-US", "zh": "zh-CN"}


def available() -> bool:
    return bool(get_secret("deepgram", "api_key") and is_enabled("deepgram"))


class _Session:
    def __init__(self, tenant_id, session_id: str, lang: str) -> None:
        self.tenant_id, self.sid, self.lang = tenant_id, session_id, lang
        self.q: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=400)
        self.task = asyncio.create_task(self._run())
        self.ok = False                 # conectado e recebendo resultados
        self.failed_at = 0.0
        self.last_audio = time.monotonic()
        self._buf = ""                  # trechos firmes ainda sem fim de fala
        self._seq: int | None = None    # segmento provisório em andamento

    async def _publish(self, text: str, final: bool) -> None:
        text = text.strip()
        if not text:
            return
        out = await write_segment(self.tenant_id, self.sid, self.lang, text, is_final=final, seq=self._seq,
                                  provider="deepgram", kind="original", publish=False)
        if out is not None:
            self._seq = None if final else out["seq"]

    async def _recv(self, ws) -> None:
        async for raw in ws:
            m = json.loads(raw)
            if m.get("type") != "Results":
                continue
            self.ok = True
            alt = ((m.get("channel") or {}).get("alternatives") or [{}])[0]
            txt = (alt.get("transcript") or "").strip()
            if m.get("is_final") and len(txt.split()) >= 3:
                conf = float(alt.get("confidence") or 0)
                if conf < LOW_CONF:      # o ASR do idioma do evento não entendeu: algazarra, outro idioma, "línguas estranhas"
                    _low_until[self.sid] = time.monotonic() + LOW_HOLD_S
                elif conf >= 0.75:
                    _low_until.pop(self.sid, None)
            if m.get("is_final"):
                if txt:
                    self._buf = f"{self._buf} {txt}".strip()
                if m.get("speech_final") or not txt:
                    if self._buf:
                        await self._publish(self._buf, True)
                        self._buf = ""
                else:
                    await self._publish(self._buf, False)
            elif txt:
                await self._publish(f"{self._buf} {txt}".strip(), False)
        if self._buf:  # conexão fechou: não perde o que já estava firme
            await self._publish(self._buf, True)
            self._buf = ""

    async def _run(self) -> None:
        import websockets
        key = get_secret("deepgram", "api_key")
        qs = urlencode({"model": MODEL, "language": DG_LANG.get(self.lang, self.lang), "encoding": "linear16", "sample_rate": 16000,
                        "channels": 1, "interim_results": "true", "smart_format": "true", "punctuate": "true", "endpointing": 700})
        try:
            ws = await asyncio.wait_for(websockets.connect(f"{URL}?{qs}", additional_headers={"Authorization": f"Token {key}"},
                                                           open_timeout=10, max_size=4 * 2**20), 12)
        except Exception as e:  # sem detalhes: o cabeçalho tem a chave
            log.warning("deepgram: falha ao conectar (%s)", type(e).__name__)
            self.failed_at = time.time()
            return
        self.ok = True
        recv = asyncio.create_task(self._recv(ws))
        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(self.q.get(), KEEPALIVE_S)
                except asyncio.TimeoutError:
                    if time.monotonic() - self.last_audio > IDLE_CLOSE_S:
                        break
                    await ws.send(json.dumps({"type": "KeepAlive"}))
                    continue
                if chunk is None:
                    break
                await ws.send(chunk)
            await ws.send(json.dumps({"type": "CloseStream"}))
            await asyncio.wait_for(recv, 8)   # deixa o Deepgram entregar o que faltava
        except Exception as e:
            log.warning("deepgram: sessão encerrada (%s)", type(e).__name__)
            self.failed_at = time.time()
        finally:
            self.ok = False
            recv.cancel()
            try:
                await ws.close()
            except Exception:
                pass

    def feed(self, chunk: bytes) -> None:
        self.last_audio = time.monotonic()
        if self.q.full():
            try:
                self.q.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self.q.put_nowait(chunk)


_sessions: dict[str, _Session] = {}
RETRY_AFTER_S = 60


def feed(tenant_id, session_id, lang: str, chunk: bytes) -> None:
    """Chamado a cada quadro de áudio do palestrante. Abre a conexão sob demanda (sem áudio, sem custo)."""
    if not available():
        return
    sid = str(session_id)
    s = _sessions.get(sid)
    if s is not None and s.task.done():
        if time.time() - s.failed_at < RETRY_AFTER_S:
            return                       # falhou há pouco: não fica tentando a cada quadro (o Gemini cobre)
        s = None
    if s is None:
        s = _sessions[sid] = _Session(tenant_id, sid, lang)
    s.feed(chunk)


def unintelligible(session_id) -> bool:
    """True se, agora, o que se ouve NÃO é fala compreensível no idioma do evento (baixa confiança do Deepgram)."""
    return _low_until.get(str(session_id), 0.0) > time.monotonic()


def active(session_id) -> bool:
    """True se o Deepgram está transcrevendo esta sessão agora (então o Gemini NÃO grava o original)."""
    s = _sessions.get(str(session_id))
    return bool(s and not s.task.done() and s.ok)


async def close(session_id) -> None:
    _low_until.pop(str(session_id), None)
    s = _sessions.pop(str(session_id), None)
    if s and not s.task.done():
        s.q.put_nowait(None)
        try:
            await asyncio.wait_for(s.task, 12)
        except Exception:
            s.task.cancel()
