"""Transcrição ao vivo (Fase 3), canais compartilhados (Fase 4) e failover (Fase 5)."""
import asyncio
import time

import pytest
from starlette.websockets import WebSocketDisconnect

from app.providers.base import ProviderUnavailable
from app.providers.failover import CircuitBreaker, FailoverRouter
from app.providers.mock import MockProvider
from app.services.channels import manager, registry, router as fo_router
from app.services.transcripts import write_segment, fetch_since
from conftest import make_event


def _listener(client, ev):
    return client.post(f"/public/join/{ev['join_code']}/token").json()["token"]


def _start(client, h, ev):
    assert client.post(f"/events/{ev['id']}/start", headers=h).status_code == 200


def test_40_minute_synthetic_event_no_loss_no_duplicates(client, tenant_a):
    """40 min ≈ 1 final a cada 10 s = 240 finais (+ provisórios). Verifica contiguidade e imutabilidade."""
    ev = make_event(client, tenant_a)
    sid, tid = ev["sessions"][0]["id"], client.get("/auth/me", headers=tenant_a).json()["memberships"][0]["tenant_id"]
    from uuid import UUID

    async def run():
        for i in range(240):
            first = await write_segment(UUID(tid), UUID(sid), "en", f"par {i} ...", is_final=False)
            await write_segment(UUID(tid), UUID(sid), "en", f"par {i} meio", is_final=False, seq=first["seq"])
            await write_segment(UUID(tid), UUID(sid), "en", f"par {i} fim", is_final=True, seq=first["seq"])
        # segmento final é imutável
        assert await write_segment(UUID(tid), UUID(sid), "en", "adulterado", is_final=True, seq=1) is None
    asyncio.run(run())
    tok = _listener(client, ev)
    segs = client.get(f"/sessions/{sid}/transcripts", params={"language": "en", "after_seq": 0}, headers={"X-Token": tok}).json()["segments"]
    assert [s["seq"] for s in segs] == list(range(1, 241))             # contíguo, sem buracos/duplicatas
    assert all(s["final"] and s["rev"] == 2 for s in segs)
    assert segs[0]["text"] == "par 0 fim"
    # paginação de scrollback
    page = client.get(f"/sessions/{sid}/transcripts", params={"language": "en", "limit": 50}, headers={"X-Token": tok}).json()["segments"]
    assert [s["seq"] for s in page] == list(range(191, 241))
    older = client.get(f"/sessions/{sid}/transcripts", params={"language": "en", "before_seq": 191, "limit": 50}, headers={"X-Token": tok}).json()["segments"]
    assert older[-1]["seq"] == 190


def test_websocket_live_stream_and_resume(client, tenant_a):
    ev = make_event(client, tenant_a)
    _start(client, tenant_a, ev)
    sid = ev["sessions"][0]["id"]
    tok = _listener(client, ev)
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:
        ws.send_json({"type": "auth", "token": tok, "lang": "en", "last_seq": 0})
        assert ws.receive_json()["type"] == "replay"
        got = []
        t0 = time.time()
        while len([g for g in got if g.get("final")]) < 3 and time.time() - t0 < 10:
            m = ws.receive_json()
            if m["type"] == "segment":
                got.append(m)
        finals = [g for g in got if g["final"]]
        assert [f["seq"] for f in finals] == [1, 2, 3] and "Good morning" in finals[0]["text"]
    # reconexão: informa last_seq=2 e recebe o que faltou
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:
        ws.send_json({"type": "auth", "token": tok, "lang": "en", "last_seq": 2})
        replay = ws.receive_json()
        assert replay["type"] == "replay" and all(s["seq"] > 2 for s in replay["segments"])
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)


def test_two_listeners_share_one_channel_per_language(client, tenant_a):
    ev = make_event(client, tenant_a)
    _start(client, tenant_a, ev)
    sid = ev["sessions"][0]["id"]
    tok = _listener(client, ev)
    with client.websocket_connect(f"/sessions/{sid}/live") as w1, client.websocket_connect(f"/sessions/{sid}/live") as w2, \
            client.websocket_connect(f"/sessions/{sid}/live") as w3:
        for w, lang in ((w1, "en"), (w2, "en"), (w3, "es")):
            w.send_json({"type": "auth", "token": tok, "lang": lang, "last_seq": 0})
            w.receive_json()
        stats = {s["language"]: s for s in manager.stats(sid)}
        assert set(stats) == {"en", "es"}               # só 2 canais (um por idioma), não 3
        assert stats["en"]["listeners"] == 2           # dois ouvintes dividem o canal "en"
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
    assert manager.stats(sid) == []                    # sem ouvintes/evento encerrado: sem canais (sem custo de IA)


def test_listener_on_scheduled_event_does_not_activate_ai(client, tenant_a):
    ev = make_event(client, tenant_a)  # NÃO iniciado
    sid = ev["sessions"][0]["id"]
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:
        ws.send_json({"type": "auth", "token": _listener(client, ev), "lang": "en", "last_seq": 0})
        assert ws.receive_json()["live"] is False
        assert manager.stats(sid) == []


def test_ws_abuse_rejected(client, tenant_a):
    ev = make_event(client, tenant_a)
    sid = ev["sessions"][0]["id"]
    for bad in ({"type": "auth", "token": "lixo", "lang": "en"},):  # token inválido
        with client.websocket_connect(f"/sessions/{sid}/live") as ws:
            ws.send_json(bad)
            with pytest.raises(WebSocketDisconnect) as e:
                ws.receive_json()
            assert e.value.code == 4403
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:   # JSON/idioma malformado
        ws.send_json({"type": "auth", "token": "x", "lang": "../../etc"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4400
    # Origin não permitido: recusado ANTES do accept (a exceção ocorre já na conexão).
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(f"/sessions/{sid}/live", headers={"origin": "https://evil.com"}):
            pass
    assert e.value.code == 4403


def test_expired_listener_token_rejected(client, tenant_a, monkeypatch):
    import jwt
    from app.config import get_settings
    ev = make_event(client, tenant_a)
    sid = ev["sessions"][0]["id"]
    s = get_settings()
    tok = jwt.encode({"iss": s.jwt_issuer, "sub": "listener:x", "typ": "listener", "sid": sid, "tid": "x", "exp": 1},
                     s.jwt_secret, algorithm="HS256")
    r = client.get(f"/sessions/{sid}/transcripts", params={"language": "en"}, headers={"X-Token": tok})
    assert r.status_code == 404


# ---------------- Failover ----------------
def test_circuit_breaker_opens_and_recovers():
    cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=0.05)
    cb.record_failure(); assert not cb.is_open
    cb.record_failure(); assert cb.is_open
    time.sleep(0.2); assert not cb.is_open  # meio-aberto após cooldown (folga p/ relógio do Windows)


def test_router_fails_over_only_the_failing_language():
    r = FailoverRouter(priority=["gemini", "azure"], threshold=2, cooldown=60, min_switch_seconds=0)
    avail = {"gemini", "azure"}
    assert r.choose("s", "en", avail) == "gemini" and r.choose("s", "es", avail) == "gemini"
    r.report_failure("s", "en", "gemini"); r.report_failure("s", "en", "gemini")
    assert r.choose("s", "en", avail) == "azure"      # só "en" trocou
    assert r.choose("s", "es", avail) == "gemini"     # "es" intacto
    r.admin_override[("s", "es")] = "azure"
    assert r.choose("s", "es", avail) == "azure"      # override do admin


def test_channel_failover_end_to_end(client, tenant_a):
    """Provedor 'gemini' (aqui simulado) falha; o canal 'en' passa para 'azure' sem afetar 'es'."""
    from app.services.channels import registry
    saved = dict(registry)
    registry.clear()
    registry["gemini"] = MockProvider(fail_after=1)  # falha após 1 segmento
    registry["azure"] = MockProvider()
    old_router = (fo_router.threshold, fo_router.min_switch_seconds)
    fo_router.threshold, fo_router.min_switch_seconds = 1, 0
    fo_router._breakers.clear(); fo_router._current.clear()
    try:
        ev = make_event(client, tenant_a)
        _start(client, tenant_a, ev)
        sid = ev["sessions"][0]["id"]
        tok = _listener(client, ev)
        with client.websocket_connect(f"/sessions/{sid}/live") as ws:
            ws.send_json({"type": "auth", "token": tok, "lang": "en", "last_seq": 0})
            ws.receive_json()
            statuses, t0 = [], time.time()
            while time.time() - t0 < 10 and not any(s.get("state") == "degraded" for s in statuses):
                m = ws.receive_json()
                if m["type"] == "status":
                    statuses.append(m)
            assert any(s.get("state") == "degraded" for s in statuses)   # usuário é avisado
        client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
    finally:
        registry.clear(); registry.update(saved)
        fo_router.threshold, fo_router.min_switch_seconds = old_router
        fo_router._breakers.clear(); fo_router._current.clear()


def test_usage_metered_after_channel_close(client, tenant_a):
    ev = make_event(client, tenant_a)
    _start(client, tenant_a, ev)
    sid = ev["sessions"][0]["id"]
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:
        ws.send_json({"type": "auth", "token": _listener(client, ev), "lang": "es", "last_seq": 0})
        ws.receive_json()
        time.sleep(0.6)
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
    assert client.get("/usage", headers=tenant_a).json()["language_minutes_used"] > 0


# ---------------- Ingestão de áudio ----------------
def _ingest_token(client, h, ev):
    return client.get(f"/events/sessions/{ev['sessions'][0]['id']}/audio-token", headers=h).json()["token"]


def test_ingest_requires_valid_scoped_live_token(client, tenant_a, tenant_b):
    ev = make_event(client, tenant_a)
    sid = ev["sessions"][0]["id"]
    # o operador de OUTRO tenant não consegue emitir token de ingestão desta sessão
    assert client.get(f"/events/sessions/{sid}/audio-token", headers=tenant_b).status_code == 404
    tok = _ingest_token(client, tenant_a, ev)
    # evento ainda não iniciado => recusa (4409)
    with client.websocket_connect(f"/sessions/{sid}/ingest") as ws:
        ws.send_json({"token": tok})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4409
    _start(client, tenant_a, ev)
    # token de ouvinte NÃO serve para ingestão
    with client.websocket_connect(f"/sessions/{sid}/ingest") as ws:
        ws.send_json({"token": _listener(client, ev)})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4403
    # token correto: aceita áudio e o diagnóstico enxerga
    with client.websocket_connect(f"/sessions/{sid}/ingest") as ws:
        ws.send_json({"token": tok})
        assert ws.receive_json()["type"] == "ready"
        for _ in range(5):
            ws.send_bytes(b"\x00" * 1000)
        time.sleep(0.3)
        st = client.get(f"/sessions/{sid}/ingest-status", headers=tenant_a).json()
        assert st["frames"] == 5 and st["bytes"] == 5000
        ws.send_bytes(b"\x00" * (70 * 1024))  # frame gigante => derruba a conexão
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_bytes()
        assert e.value.code == 4413
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)


# ---------------- Idiomas dinâmicos ----------------
def test_languages_come_from_providers_not_hardcoded(client):
    langs = client.get("/public/languages").json()
    by = {l["code"]: l for l in langs}
    assert {"en", "es", "pt"} <= set(by) and by["en"]["speech"] and by["en"]["text"] and "mock" in by["en"]["providers"]
    assert all(set(l) >= {"code", "text", "speech", "providers", "discovered", "verified"} for l in langs)


def test_public_join_lists_same_languages(client, tenant_a):
    ev = make_event(client, tenant_a)
    j = client.get(f"/public/join/{ev['join_code']}").json()
    assert {l["code"] for l in j["languages"]} == {l["code"] for l in client.get("/public/languages").json()}


def test_ws_rejects_language_not_offered(client, tenant_a):
    ev = make_event(client, tenant_a)
    sid = ev["sessions"][0]["id"]
    with client.websocket_connect(f"/sessions/{sid}/live") as ws:
        ws.send_json({"type": "auth", "token": _listener(client, ev), "lang": "xx", "last_seq": 0})
        assert ws.receive_json()["code"] == "language_unavailable"
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4404


def test_azure_language_discovery_parser_and_availability(monkeypatch):
    """Descoberta pela API do Azure (resposta simulada): texto ∪ voz, marcado como `discovered`."""
    import asyncio
    from app.providers.external import AzureProvider, parse_azure_languages
    voices = [{"Locale": "pt-BR"}, {"Locale": "pt-PT"}, {"Locale": "sw-KE"}, {"Locale": "fil-PH"}]
    tr = {"translation": {"pt": {}, "sw": {}, "af": {}, "zh-Hans": {}}}
    caps = {c.language: c for c in parse_azure_languages(voices, tr)}
    assert caps["pt"].speech_output and caps["pt"].text_output and caps["pt"].discovered
    assert caps["af"].text_output and not caps["af"].speech_output        # só texto
    assert caps["fil"].speech_output and not caps["fil"].text_output      # só voz
    assert "zh-Hans" in caps
    # provedor configurado + descoberta => idiomas novos aparecem na lista pública
    from app.services import secrets_store as sec, languages as L
    from app.services.channels import registry
    sec.save("azure", {"key": "k" * 10, "region": "eastus"}, [], True)
    az = AzureProvider()

    async def fake_fetch():
        return voices, tr
    monkeypatch.setattr(az, "_fetch", fake_fetch)
    saved = dict(registry); registry["azure"] = az; L.invalidate()
    try:
        # provedor SEM adaptador ao vivo pronto não oferece idiomas ao público (mesmo com chave)
        monkeypatch.setattr(az, "streaming_implemented", False); L.invalidate()
        assert not {"af", "sw", "fil", "zh-Hans"} & {l["code"] for l in asyncio.run(L.available_languages(force=True))}
        monkeypatch.setattr(az, "streaming_implemented", True); L.invalidate()
        codes = {l["code"] for l in asyncio.run(L.available_languages(force=True))}
        assert {"af", "sw", "fil", "zh-Hans"} <= codes
    finally:
        registry.clear(); registry.update(saved); sec.save("azure", {}, ["key", "region"], None); L.invalidate()
