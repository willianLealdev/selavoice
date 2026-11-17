"""Gerenciador de canais de tradução: UM canal por (sessão, idioma), compartilhado.

Fluxo:
  ouvinte entra  -> join(): contador +1; se era o primeiro, inicia a tarefa do canal (usa IA).
  ouvinte sai    -> leave(): contador -1; se zerou, agenda desligamento após a carência
                    (`channel_grace_seconds`) — sem ouvintes, SEM custo de IA.
  falha          -> failover só desse idioma (circuit breaker), registra FailoverEvent.
  medição        -> minutos-idioma lançados no livro-razão a cada minuto e ao fechar.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from ..config import get_settings
from ..db import SessionLocal
from ..models import ChannelState, FailoverEvent, ProviderConfig, Tenant, TranslationChannel
from ..providers.base import ProviderUnavailable, TranslationProvider
from ..providers.external import AzureProvider, GeminiProvider
from ..providers.failover import FailoverRouter
from ..providers.mock import MockProvider
from . import original_asr
from .audio_gate import get_audio
from .billing import minutes_remaining, record_usage
from .transcripts import hub, write_segment

settings = get_settings()
log = logging.getLogger("selavoice.channels")


def build_registry() -> dict[str, TranslationProvider]:
    reg: dict[str, TranslationProvider] = {"gemini": GeminiProvider(), "azure": AzureProvider()}
    if not settings.is_prod:  # simulador NUNCA em produção
        reg["mock"] = MockProvider()
    return reg


registry = build_registry()
router = FailoverRouter(priority=["gemini", "azure", "mock"])
METER_SECONDS = 60
# segundos de fala ainda NÃO gravados no banco, por evento: event_id -> (instante do último evento, pendente)
_speech: dict[str, tuple[float, float]] = {}


def take_speech(event_id) -> float:
    """Entrega (e zera) os segundos de fala acumulados do evento; o relógio grava em Event.active_seconds."""
    k = str(event_id)
    last, pend = _speech.get(k, (0.0, 0.0))
    _speech[k] = (last, 0.0)
    return pend


ACTIVE_HOLD_S = 3.0   # pausa de até 3 s entre eventos de tradução ainda conta como "traduzindo" (respiros dentro da frase)


@dataclass
class _Chan:
    tenant_id: object
    event_id: object
    session_id: str
    lang: str
    source_lang: str
    listeners: int = 0
    task: asyncio.Task | None = None
    shutdown: asyncio.TimerHandle | None = None
    started: float = field(default_factory=time.monotonic)
    metered_to: float = field(default_factory=time.monotonic)
    meter_n: int = 0
    provider: str = ""
    # Áudio do palestrante (PCM16 16 kHz) esperando para ir ao provedor. Limitada: se o provedor atrasar,
    # descartamos o mais ANTIGO (melhor perder um pedaço do que acumular atraso).
    audio_q: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=300))
    # Tempo COM TRADUÇÃO sendo entregue (s) ainda não lançado no livro-razão. Silêncio não conta.
    active_s: float = 0.0
    last_event_t: float = 0.0
    orig_seq: int | None = None   # segmento ORIGINAL provisório em andamento (reserva do Deepgram)


class ChannelManager:
    def __init__(self) -> None:
        self.channels: dict[tuple[str, str], _Chan] = {}

    # ----- API pública -----
    def join(self, tenant_id, event_id, session_id, lang: str, source_lang: str) -> _Chan:
        key = (str(session_id), lang)
        ch = self.channels.get(key)
        if ch is None:
            # UUIDs reais nos modelos; str só nas chaves do hub/dicionários.
            ch = _Chan(UUID(str(tenant_id)), UUID(str(event_id)), str(session_id), lang, source_lang)
            self.channels[key] = ch
        ch.listeners += 1
        if ch.shutdown:  # cancelou o desligamento agendado
            ch.shutdown.cancel()
            ch.shutdown = None
        if ch.task is None or ch.task.done():
            ch.started = ch.metered_to = time.monotonic()
            ch.task = asyncio.create_task(self._run(ch))
            self._db_state(ch, ChannelState.ACTIVE)
        return ch

    def push_audio(self, session_id, chunk: bytes) -> None:
        """Recebe um pedaço de áudio do palestrante (ingestão) e o entrega a TODOS os canais de idioma da sessão.
        Cada idioma tem a sua própria sessão no provedor, então o mesmo áudio é copiado para cada um."""
        sid = str(session_id)
        for (s, _), ch in self.channels.items():
            if s != sid:
                continue
            if ch.audio_q.full():
                try:
                    ch.audio_q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            ch.audio_q.put_nowait(chunk)

    async def _pump(self, ch: "_Chan", sess) -> None:
        """Move o áudio da fila do canal para a sessão do provedor."""
        while True:
            await sess.push_audio(await ch.audio_q.get())

    def leave(self, session_id, lang: str) -> None:
        ch = self.channels.get((str(session_id), lang))
        if not ch:
            return
        ch.listeners = max(0, ch.listeners - 1)
        if ch.listeners == 0 and ch.shutdown is None:
            loop = asyncio.get_running_loop()
            ch.shutdown = loop.call_later(settings.channel_grace_seconds, lambda: asyncio.create_task(self.close(ch)))

    async def close(self, ch: _Chan, *, force: bool = False) -> None:
        if ch.listeners > 0 and not force:
            return
        if ch.task and not ch.task.done():
            ch.task.cancel()
            try:
                await ch.task
            except (asyncio.CancelledError, Exception):
                pass
        self._meter(ch)  # lança o resto dos minutos
        self._db_state(ch, ChannelState.IDLE)
        self.channels.pop((ch.session_id, ch.lang), None)

    async def close_session(self, session_id) -> None:
        for (sid, _), ch in list(self.channels.items()):
            if sid == str(session_id):
                await self.close(ch, force=True)

    def stats(self, session_id) -> list[dict]:
        return [{"language": c.lang, "listeners": c.listeners, "provider": c.provider,
                 "active": bool(c.task and not c.task.done())}
                for (sid, _), c in self.channels.items() if sid == str(session_id)]

    # ----- internos -----
    def _db_state(self, ch: _Chan, state: ChannelState) -> None:
        with SessionLocal() as db:
            row = db.scalar(select(TranslationChannel).where(
                TranslationChannel.session_id == UUID(ch.session_id), TranslationChannel.target_language == ch.lang))
            if row is None:
                row = TranslationChannel(tenant_id=ch.tenant_id, session_id=UUID(ch.session_id), target_language=ch.lang)
                db.add(row)
            row.state, row.listeners = state, ch.listeners
            row.provider = ch.provider or row.provider
            row.active_since = datetime.now(timezone.utc) if state == ChannelState.ACTIVE else None
            db.commit()

    @staticmethod
    def _audio_cfg(tenant_id) -> dict:
        """Configuração de áudio da organização (filtro de voz, só idioma do evento...)."""
        with SessionLocal() as db:
            t = db.get(Tenant, tenant_id)
            return get_audio((t.settings or {}) if t else {})

    @staticmethod
    def _touch_active(ch: "_Chan") -> None:
        """Chamado a cada evento de TRADUÇÃO entregue (texto ou voz). Soma o tempo desde o evento anterior, limitado a ACTIVE_HOLD_S:
        silêncio (sem evento) não acumula => não é cobrado."""
        now = time.monotonic()
        gap = now - ch.last_event_t if ch.last_event_t else ACTIVE_HOLD_S
        ch.active_s += min(gap, ACTIVE_HOLD_S)
        ch.last_event_t = now
        # Relógio de FALA do EVENTO (união de todos os idiomas): as horas do plano contam só o tempo em que há tradução.
        if ch.event_id is not None:
            k = str(ch.event_id)
            last, pend = _speech.get(k, (0.0, 0.0))
            _speech[k] = (now, pend + min(now - last if last else ACTIVE_HOLD_S, ACTIVE_HOLD_S))

    def _meter(self, ch: _Chan) -> None:
        minutes = ch.active_s / 60          # só tempo COM tradução (silêncio não é cobrado)
        if minutes <= 0:
            return
        ch.active_s = 0.0
        ch.metered_to = time.monotonic()
        ch.meter_n += 1
        cost = 0
        prov = registry.get(ch.provider)
        with SessionLocal() as db:
            if prov:
                # tarifa configurada pelo Super Admin (Financeiro) prevalece; sem ela, usa a estimativa do provedor
                pc = db.scalar(select(ProviderConfig).where(ProviderConfig.name == ch.provider))
                rate = (pc.capabilities or {}).get("rate_usd_per_min") if pc else None
                cost = int((float(rate) * minutes if rate is not None else prov.estimated_cost(minutes)) * 1_000_000)
            record_usage(db, tenant_id=ch.tenant_id, event_id=ch.event_id, session_id=UUID(ch.session_id),
                         language=ch.lang, provider=ch.provider or "none", minutes=minutes, cost_micros=cost,
                         key=f"{ch.session_id}:{ch.lang}:{int(ch.started)}:{ch.meter_n}")

    async def _available(self) -> set[str]:
        ok = set()
        for name, p in registry.items():
            if (await p.health()).ok:
                ok.add(name)
        return ok

    async def _run(self, ch: _Chan) -> None:
        """Laço do canal: escolhe provedor, consome eventos, publica, faz failover e mede uso."""
        seq: int | None = None
        last_provider = ""
        last_tick = time.monotonic()
        while True:
            avail = await self._available()
            name = router.choose(ch.session_id, ch.lang, avail)
            if name is None:
                hub.publish(ch.session_id, ch.lang, {"type": "status", "state": "no_provider",
                                                     "message": "Tradução indisponível no momento."})
                await asyncio.sleep(5)
                continue
            if last_provider and name != last_provider:
                self._record_failover(ch, last_provider, name)
                hub.publish(ch.session_id, ch.lang, {"type": "status", "state": "degraded",
                                                     "message": "Trocamos de provedor; pode haver uma pequena lacuna."})
            ch.provider = last_provider = name
            pump, sess = None, None
            try:
                sess = await registry[name].start_session(ch.source_lang, ch.lang)
                strict = self._audio_cfg(ch.tenant_id)["only_event_language"]
                if strict:   # "só traduzir o idioma do evento": o provedor passa a ignorar fala em outro idioma
                    sess.strict_source = ch.source_lang.split("-")[0].lower()
                hub.publish(ch.session_id, ch.lang, {"type": "status", "state": "live", "provider": name})
                pump = asyncio.create_task(self._pump(ch, sess))
                async for ev in sess.stream_events():
                    router.report_success(ch.session_id, ch.lang, name)
                    if strict and original_asr.unintelligible(ch.session_id):
                        continue   # fala ininteligível no idioma do evento (ex.: "línguas estranhas", algazarra): não traduz nem publica
                    if ev.audio:  # VOZ traduzida do provedor -> ouvintes (quadro binário; não é gravada)
                        hub.publish(ch.session_id, ch.lang, {"type": "audio", "pcm": ev.audio})
                        self._touch_active(ch)   # há tradução sendo entregue => conta como tempo cobrável
                    if ev.original:
                        await self._write_original(ch, ev)
                    if not ev.text:
                        continue
                    self._touch_active(ch)
                    out = await write_segment(ch.tenant_id, ch.session_id, ch.lang, ev.text, is_final=ev.is_final,
                                              seq=seq, start_ms=ev.start_ms, end_ms=ev.end_ms, provider=name)
                    if out is not None:
                        seq = None if ev.is_final else out["seq"]
                    if time.monotonic() - last_tick >= METER_SECONDS:
                        last_tick = time.monotonic()
                        self._meter(ch)
                        if self._quota_exhausted(ch):
                            hub.publish(ch.session_id, ch.lang, {"type": "status", "state": "quota_exhausted",
                                                                 "message": "Limite de tradução do evento atingido."})
                            await sess.stop()
                            return
            except asyncio.CancelledError:
                raise
            except ProviderUnavailable as e:
                log.warning("provedor %s falhou (%s): %s", name, ch.lang, e)
                router.report_failure(ch.session_id, ch.lang, name)
                await asyncio.sleep(0.05)
            except Exception:  # erro inesperado: conta como falha, nunca derruba o servidor
                log.exception("erro no canal %s/%s", ch.session_id, ch.lang)
                router.report_failure(ch.session_id, ch.lang, name)
                await asyncio.sleep(0.5)
            finally:
                if pump:
                    pump.cancel()
                try:
                    if sess:
                        await sess.stop()  # fecha a conexão com o provedor (evita sessão aberta gastando crédito)
                except Exception:
                    pass

    async def _write_original(self, ch: _Chan, ev) -> None:
        """RESERVA da transcrição do original: usa o texto que o próprio provedor devolve, mas SÓ se o Deepgram não está
        transcrevendo e SÓ no canal de menor código de idioma (todos os canais recebem o mesmo áudio => mesmo texto; grava 1 vez)."""
        if original_asr.active(ch.session_id):
            return
        langs = [l for (s, l) in self.channels if s == ch.session_id]
        if not langs or ch.lang != min(langs):
            return
        out = await write_segment(ch.tenant_id, ch.session_id, ch.source_lang, ev.original, is_final=ev.is_final, seq=ch.orig_seq,
                                  provider=ch.provider, kind="original", publish=False)
        if out is not None:
            ch.orig_seq = None if ev.is_final else out["seq"]

    def _quota_exhausted(self, ch: _Chan) -> bool:
        with SessionLocal() as db:
            return minutes_remaining(db, ch.tenant_id) <= 0

    def _record_failover(self, ch: _Chan, a: str, b: str) -> None:
        with SessionLocal() as db:
            db.add(FailoverEvent(tenant_id=ch.tenant_id, session_id=UUID(ch.session_id), language=ch.lang,
                                 from_provider=a, to_provider=b, reason="circuit_open"))
            db.commit()


manager = ChannelManager()
