"""Superfície PÚBLICA/ouvinte e transporte em tempo real (WebSocket).

Fluxo do ouvinte:
 1) GET  /public/join/{code}            -> dados públicos do evento (sem login)
 2) POST /public/join/{code}/token      -> token de ouvinte (curto, só leitura, só desta sessão)
 3) WS   /sessions/{id}/live            -> 1ª mensagem {"type":"auth","token","lang","last_seq"}
 4) GET  /sessions/{id}/transcripts     -> scrollback paginado (histórico)

Segurança do WebSocket: autenticação por 1ª mensagem (token nunca vai na URL/logs), prazo de
5 s para autenticar, checagem de Origin, limite de conexões por IP, tamanho máximo de mensagem,
e validação do idioma. Membros do tenant usam o access token; ouvintes usam o token de ouvinte.
"""
import asyncio
import json
import re
from uuid import UUID

import jwt
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core.timeutil import iso
from ..core.ratelimit import client_ip, rate_limit, ws_counter
from ..db import SessionLocal, get_db
from ..deps import Ctx, require_member, require_operator
from ..models import Event, EventSession, EventStatus, Membership, Tenant
from ..security import verify_password, create_listener_token, decode_token
from ..services import original_asr
from ..services.audio_gate import AudioGate, gates, get_audio
from ..services.event_clock import event_limits
from ..services.plan_schema import limit as plan_limit
from ..services.channels import manager
from ..services.languages import available_languages
from ..services.transcripts import fetch_page, fetch_since, hub, write_segment

settings = get_settings()
router = APIRouter(tags=["live"])
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
_pub_limit = rate_limit("public", 60)


def _plan_languages(langs: list[dict], ev: Event, db: Session) -> list[dict]:
    """Se o plano do evento restringe idiomas (allowed_languages), só estes aparecem para o ouvinte."""
    allowed = set(event_limits(db, ev).get("allowed_languages") or []) if ev.status == EventStatus.LIVE else set()
    return [l for l in langs if l["code"] in allowed] if allowed else langs


# ---------------- Público ----------------
@router.get("/public/join/{code}", dependencies=[Depends(_pub_limit)])
async def public_join(code: str, db: Session = Depends(get_db), x_event_password: str | None = Header(default=None)):
    ev = db.scalar(select(Event).where(Event.join_code == code.lower(), Event.deleted_at.is_(None)))
    if not ev or ev.status == EventStatus.CANCELED:
        raise HTTPException(404, "Evento não encontrado.")
    from ..models import Tenant
    from .public import contact_out
    t = db.get(Tenant, ev.tenant_id)
    if t.status != "active":
        raise HTTPException(404, "Evento não encontrado.")
    if ev.access_password_hash and not verify_password(x_event_password or "", ev.access_password_hash):
        # PRIVADO sem a senha (a senha vai no cabeçalho, nunca na URL): sem a senha só mostramos o mínimo para a tela de senha (nada de tema, palestrante ou idiomas).
        return {"private": True, "title": ev.title, "organization": t.name, "organization_slug": t.slug, "branding": t.branding,
                "status": ev.status.value}
    return {"private": False, "title": ev.title, "type": ev.type, "presenter": ev.presenter, "theme": ev.theme,
            "scripture": ev.scripture, "status": ev.status.value, "original_language": ev.original_language,
            "starts_at": iso(ev.starts_at), "organization": t.name, "organization_slug": t.slug, "branding": t.branding, "contact": contact_out(t),
            "session_id": str(ev.sessions[0].id) if ev.sessions else None,
            "languages": _plan_languages(await available_languages(), ev, db)}


class JoinIn(BaseModel):
    password: str | None = Field(default=None, max_length=60)


@router.post("/public/join/{code}/token", dependencies=[Depends(rate_limit("listener_token", 30))])
def listener_token(code: str, body: JoinIn | None = None, db: Session = Depends(get_db),
                   _slow: None = Depends(rate_limit("join_password", 10))):
    ev = db.scalar(select(Event).where(Event.join_code == code.lower(), Event.deleted_at.is_(None)))
    if not ev or ev.status == EventStatus.CANCELED or not ev.sessions:
        raise HTTPException(404, "Evento não encontrado.")
    # Evento privado: o token só sai com a senha certa (limite de 10 tentativas/min por IP contra adivinhação).
    if ev.access_password_hash and not verify_password((body.password if body else None) or "", ev.access_password_hash):
        raise HTTPException(403, "Senha do evento incorreta.")
    s = ev.sessions[0]
    return {"token": create_listener_token(str(s.id), str(ev.tenant_id)), "session_id": str(s.id)}


# ---------------- Resolução de quem está vendo ----------------
def resolve_viewer(db: Session, token: str, session_id: UUID) -> tuple[object, str]:
    """Valida o token (ouvinte OU membro do tenant) para ESTA sessão. Retorna (sessão, tipo).
    Levanta PermissionError se não autorizado."""
    sess = db.get(EventSession, session_id)
    if not sess:
        raise PermissionError("sessão inexistente")
    try:
        claims = decode_token(token, "listener")
        if claims["sid"] != str(session_id) or claims["tid"] != str(sess.tenant_id):
            raise PermissionError("token de outra sessão")
        return sess, "listener"
    except jwt.PyJWTError:
        pass
    try:
        claims = decode_token(token, "access")
    except jwt.PyJWTError:
        raise PermissionError("token inválido")
    if claims.get("elev") and claims["elev"] == str(sess.tenant_id):
        return sess, "support"
    mem = db.scalar(select(Membership).where(Membership.user_id == UUID(claims["sub"]),
                                             Membership.tenant_id == sess.tenant_id))
    if not mem:
        raise PermissionError("sem membership neste tenant")  # barreira cross-tenant
    return sess, "member"


# ---------------- Scrollback ----------------
@router.get("/sessions/{session_id}/transcripts", dependencies=[Depends(_pub_limit)])
def transcripts(session_id: UUID, language: str = Query(pattern=LANG_RE.pattern), before_seq: int | None = None,
                after_seq: int | None = None, limit: int = Query(50, le=200),
                db: Session = Depends(get_db), x_token: str | None = Header(default=None)):
    """Histórico paginado. O token vai SOMENTE no cabeçalho X-Token (nunca na URL)."""
    token = x_token
    if not token:
        raise HTTPException(401, "Token ausente.")
    try:
        sess, _ = resolve_viewer(db, token, session_id)
    except PermissionError:
        raise HTTPException(404, "Sessão não encontrada.")  # 404: não revela existência
    if after_seq is not None:
        return {"segments": fetch_since(db, sess.id, language, after_seq)}
    return {"segments": fetch_page(db, sess.id, language, before_seq, limit)}


# ---------------- WebSocket ----------------
@router.websocket("/sessions/{session_id}/live")
async def live_ws(ws: WebSocket, session_id: UUID):
    ip = ws.client.host if ws.client else "unknown"
    origin = ws.headers.get("origin")
    if origin and origin not in settings.cors_list:  # navegadores sempre mandam Origin
        await ws.close(code=4403)
        return
    if not ws_counter.acquire(ip, settings.ws_max_connections_per_ip):
        await ws.close(code=4429)
        return
    q = None
    lang = None
    joined = False
    sid = str(session_id)
    try:
        await ws.accept()
        # 1) autenticação em até 5 s
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=5)
        except (asyncio.TimeoutError, WebSocketDisconnect):
            await ws.close(code=4401)
            return
        if len(raw) > 4096:
            await ws.close(code=4413)
            return
        try:
            msg = json.loads(raw)
            token, lang = str(msg["token"]), str(msg["lang"])
            last_seq = int(msg.get("last_seq", 0))
            if msg.get("type") != "auth" or not LANG_RE.match(lang) or last_seq < 0:
                raise ValueError
        except (ValueError, KeyError, TypeError):
            await ws.close(code=4400)
            return
        if lang not in {l["code"] for l in await available_languages()}:
            await ws.send_json({"type": "error", "code": "language_unavailable"})
            await ws.close(code=4404)  # idioma não oferecido pelos provedores configurados
            return
        with SessionLocal() as db:
            try:
                sess, kind = resolve_viewer(db, token, session_id)
            except PermissionError:
                await ws.close(code=4403)
                return
            ev = db.get(Event, sess.event_id)
            tenant_id, event_id, src_lang, live = sess.tenant_id, ev.id, ev.original_language, ev.status == EventStatus.LIVE
            lim = event_limits(db, ev) if live else {}
            backlog = fetch_since(db, sess.id, lang, last_seq)
        # ---- Limites do PLANO para ouvintes (só enquanto AO VIVO; equipe e suporte não são limitados) ----
        if live and kind == "listener":
            allowed = lim.get("allowed_languages") or []
            mine = [(s_, l_) for (s_, l_) in manager.channels if s_ == sid]
            cap_l, cap_p = plan_limit(lim, "max_languages", None), plan_limit(lim, "listener_concurrency", None)
            problem = None
            if allowed and lang not in allowed:
                problem = ("language_not_in_plan", 4404)
            elif cap_l is not None and (sid, lang) not in mine and len(mine) >= int(cap_l):
                problem = ("language_limit", 4409)   # o plano já está usando todos os idiomas simultâneos
            elif cap_p is not None and sum(manager.channels[k].listeners for k in mine) >= int(cap_p):
                problem = ("event_full", 4429)       # lotação de ouvintes do plano
            if problem:
                await ws.send_json({"type": "error", "code": problem[0]})
                await ws.close(code=problem[1])
                return
        q = hub.subscribe(sid, lang)  # assina ANTES do replay: nada se perde (cliente deduplica por seq/rev)
        if live:
            manager.join(tenant_id, event_id, sess.id, lang, src_lang)  # ativa/compartilha o canal do idioma
            joined = True
        await ws.send_json({"type": "replay", "segments": backlog, "live": live})

        async def reader():  # ouve ping/mensagens do cliente (e detecta desconexão)
            while True:
                data = await ws.receive_text()
                if len(data) > 1024:
                    raise WebSocketDisconnect(4413)
                m = json.loads(data)
                if m.get("type") == "ping":
                    await ws.send_json({"type": "pong"})

        rtask = asyncio.create_task(reader())
        try:
            while True:
                getter = asyncio.create_task(q.get())
                done, _ = await asyncio.wait({getter, rtask}, return_when=asyncio.FIRST_COMPLETED)
                if rtask in done:
                    getter.cancel()
                    break
                item = getter.result()
                if item.get("type") == "audio":
                    await ws.send_bytes(item["pcm"])
                else:
                    await ws.send_json(item)
        finally:
            rtask.cancel()
    except (WebSocketDisconnect, RuntimeError, ValueError):
        pass
    finally:
        if q is not None:
            hub.unsubscribe(sid, lang, q)
        if joined:
            manager.leave(session_id, lang)
        ws_counter.release(ip)


# ---------------- Gerador sintético (somente dev/teste) ----------------
@router.post("/sessions/{session_id}/mock-stream")
async def mock_stream(session_id: UUID, languages: list[str], count: int = 10,
                      ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    """Injeta segmentos sintéticos (demonstração/teste). Desligado em produção."""
    if settings.is_prod:
        raise HTTPException(404)
    from ..db import scoped
    from ..providers.mock import SCRIPT_PT, mock_translate
    s = db.scalar(scoped(db, EventSession, ctx.tenant_id).where(EventSession.id == session_id))
    if not s:
        raise HTTPException(404, "Sessão não encontrada.")
    count = min(count, 500)
    for lang in languages[:5]:
        if not LANG_RE.match(lang):
            raise HTTPException(422, "Idioma inválido.")
        for i in range(count):
            await write_segment(ctx.tenant_id, s.id, lang, mock_translate(SCRIPT_PT[i % len(SCRIPT_PT)], lang),
                                is_final=True, provider="mock")
    return {"ok": True, "segments_per_language": count}


# ---------------- Ingestão de áudio (utilitário X32/Windows ou microfone do navegador) ----------------
MAX_FRAME_BYTES = 64 * 1024          # um frame de áudio nunca precisa ser maior que isso
MAX_BYTES_PER_SEC = 512 * 1024       # ~4 Mbps: acima disso é abuso/erro e a conexão é derrubada
ingest_stats: dict[str, dict] = {}   # session_id -> métricas (alimenta o painel de diagnóstico)


@router.websocket("/sessions/{session_id}/ingest")
async def ingest_ws(ws: WebSocket, session_id: UUID):
    """Recebe áudio (frames binários Opus/PCM). Autenticação: 1ª mensagem {"type":"auth","token"} com o
    token EFÊMERO de ingestão (/events/sessions/{id}/audio-token). Só aceita se o evento estiver AO VIVO.
    ENCAMINHAMENTO ao provedor de IA: depende de chaves reais (BLOCKED_EXTERNAL); por ora medimos e validamos."""
    import time as _t
    ip = ws.client.host if ws.client else "unknown"
    if not ws_counter.acquire(ip, settings.ws_max_connections_per_ip):
        await ws.close(code=4429)
        return
    sid = str(session_id)
    try:
        await ws.accept()
        try:
            msg = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=5))
            claims = decode_token(str(msg["token"]), "ingest")
        except (asyncio.TimeoutError, ValueError, KeyError, TypeError, jwt.PyJWTError, WebSocketDisconnect):
            await ws.close(code=4403)
            return
        if claims.get("sid") != sid:
            await ws.close(code=4403)
            return
        with SessionLocal() as db:
            sess = db.get(EventSession, session_id)
            ev = db.get(Event, sess.event_id) if sess else None
            if not sess or str(sess.tenant_id) != claims.get("tid") or ev.status != EventStatus.LIVE:
                await ws.close(code=4409)  # evento não está ao vivo
                return
            ev_lang = ev.original_language
            gate_mode = get_audio((db.get(Tenant, sess.tenant_id).settings or {}))["filter"]   # filtro de voz escolhido pela organização
        st = ingest_stats[sid] = {"bytes": 0, "frames": 0, "started": _t.time(), "last_frame": 0.0}
        gate = gates[sid] = AudioGate(gate_mode)
        await ws.send_json({"type": "ready"})
        window_start, window_bytes = _t.monotonic(), 0
        while True:
            data = await ws.receive_bytes()
            if len(data) > MAX_FRAME_BYTES:
                await ws.close(code=4413)
                return
            now = _t.monotonic()
            if now - window_start >= 1:
                window_start, window_bytes = now, 0
            window_bytes += len(data)
            if window_bytes > MAX_BYTES_PER_SEC:
                await ws.close(code=4429)
                return
            st["bytes"] += len(data)
            st["frames"] += 1
            st["last_frame"] = _t.time()
            # Portão de voz: só a voz do palestrante segue; ruído/conversa de fundo e silêncio longo NÃO vão aos provedores (nem custam)
            for frame in gate.process(data):
                manager.push_audio(sid, frame)  # -> um provedor por idioma ativo (Gemini/Azure); sem ouvintes não há canal => sem custo
                original_asr.feed(claims["tid"], sid, ev_lang, frame)  # transcrição do ORIGINAL (Deepgram), com ou sem ouvintes
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        ws_counter.release(ip)
        gates.pop(sid, None)
        await original_asr.close(sid)  # fecha a transcrição do original (entrega o que faltava)


@router.post("/sessions/{session_id}/audio-calibrate")
def audio_calibrate(session_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    """O operador pede para calibrar a voz do palestrante: nos próximos 5 s o sistema aprende o volume dele."""
    from ..db import scoped
    s = db.scalar(scoped(db, EventSession, ctx.tenant_id).where(EventSession.id == session_id))
    if not s:
        raise HTTPException(404, "Sessão não encontrada.")
    g = gates.get(str(s.id))
    if g is None:
        raise HTTPException(409, "Comece a enviar o áudio (Iniciar captura) antes de calibrar.")
    g.start_calibration(5.0)
    return {"seconds": 5}


@router.get("/sessions/{session_id}/ingest-status")
def ingest_status(session_id: UUID, ctx: Ctx = Depends(require_operator), db: Session = Depends(get_db)):
    """Diagnóstico para o operador: o áudio está chegando? quantos bytes/s?"""
    import time as _t
    from ..db import scoped
    s = db.scalar(scoped(db, EventSession, ctx.tenant_id).where(EventSession.id == session_id))
    if not s:
        raise HTTPException(404, "Sessão não encontrada.")
    st = ingest_stats.get(str(s.id))
    if not st:
        return {"receiving": False}
    elapsed = max(1.0, _t.time() - st["started"])
    g = gates.get(str(s.id))
    return {"receiving": _t.time() - st["last_frame"] < 3, "bytes": st["bytes"], "frames": st["frames"],
            "avg_kbps": round(st["bytes"] * 8 / 1000 / elapsed, 1), "filter": g.stats() if g else None}
