"""Adaptador do Gemini Live Translate — testado contra um SERVIDOR FALSO que imita o protocolo da documentação.

ATENÇÃO: isto valida NOSSA implementação do protocolo, NÃO o serviço real do Google (a conta de teste está sem créditos).
"""
import asyncio
import base64
import json
import threading
import time

import pytest
import websockets

from app.providers import gemini as G
from app.services import secrets_store as sec
from conftest import make_event, register, speech_frame


class FakeGemini:
    """Servidor WebSocket local. Para cada áudio recebido responde com voz + texto traduzido + fim de turno."""
    def __init__(self, reject_reason: str | None = None, say_turn_complete: bool = True, texts=("Hola ", "a todos."), input_texts=(), input_lang=None):
        self.texts = list(texts)
        self.input_texts, self.input_lang = list(input_texts), input_lang
        self.setups, self.audio_msgs = [], []
        self.reject, self.turn = reject_reason, say_turn_complete
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        assert self.ready.wait(5)

    def _run(self):
        asyncio.set_event_loop(self.loop)

        async def handler(ws):
            setup = json.loads(await ws.recv())
            self.setups.append(setup)
            if self.reject:
                await ws.close(code=1011, reason=self.reject)
                return
            await ws.send(json.dumps({"setupComplete": {}}))
            n = 0
            async for raw in ws:
                m = json.loads(raw)
                if "realtimeInput" in m:
                    self.audio_msgs.append(m["realtimeInput"]["audio"])
                    n += 1
                    if n == 1:
                        for t in getattr(self, "input_texts", []):   # o que o palestrante falou: o Gemini real manda ANTES da tradução
                            it = {"text": t}
                            if getattr(self, "input_lang", None):
                                it["languageCode"] = self.input_lang      # idioma que o Gemini ouviu (campo real, visto em teste)
                            await ws.send(json.dumps({"serverContent": {"inputTranscription": it}}))
                        loud, quiet = b"\x00\x20" * 480, b"\x00\x00" * 480      # voz de verdade x áudio mudo
                        for chunk in (loud, quiet, quiet):
                            await ws.send(json.dumps({"serverContent": {"modelTurn": {"parts": [{"inlineData": {"data": base64.b64encode(chunk).decode()}}]}}}))
                        for t in self.texts:
                            await ws.send(json.dumps({"serverContent": {"outputTranscription": {"text": t}}}))
                        if self.turn:
                            await ws.send(json.dumps({"serverContent": {"turnComplete": True}}))

        async def main():
            self.server = await websockets.serve(handler, "127.0.0.1", 0)
            self.port = self.server.sockets[0].getsockname()[1]
            self.ready.set()
            await asyncio.Future()

        self.loop.run_until_complete(main())


@pytest.fixture()
def fake(monkeypatch):
    def make(**kw):
        f = FakeGemini(**kw)
        monkeypatch.setattr(G, "URL", f"ws://127.0.0.1:{f.port}/ws")
        sec.save("gemini", {"api_key": "k" * 12}, [], True)
        G.LAST_ERROR.update(msg="", at=0.0, ok_at=0.0)
        return f
    yield make
    sec.save("gemini", {}, ["api_key"], None)
    G.LAST_ERROR.update(msg="", at=0.0, ok_at=0.0)


def _collect(session, seconds=3):
    async def go():
        ev = []

        async def rd():
            try:
                async for e in session.stream_events():
                    ev.append(e)
            except Exception as e:
                ev.append(e)
        t = asyncio.create_task(rd())
        for _ in range(40):                               # 40 quadros de 20 ms = 800 ms de áudio
            await session.push_audio(b"\x00" * 640)
            await asyncio.sleep(0.01)
        await asyncio.sleep(seconds)
        await session.stop()
        await t
        return ev
    return asyncio.run(go())


def test_session_follows_documented_protocol(fake):
    f = fake()
    ev = _collect(G.GeminiSession("pt"), 1)
    cfg = f.setups[0]["setup"]
    assert cfg["model"] == "models/gemini-3.5-live-translate-preview"
    assert cfg["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert cfg["generationConfig"]["translationConfig"]["targetLanguageCode"] == "pt-BR"     # "pt" vira pt-BR
    assert "inputAudioTranscription" in cfg and "outputAudioTranscription" in cfg
    # áudio enviado em blocos de ~100 ms (3200 bytes) com o formato exigido
    assert f.audio_msgs and all(a["mimeType"] == "audio/pcm;rate=16000" for a in f.audio_msgs)
    assert len(base64.b64decode(f.audio_msgs[0]["data"])) == 3200
    voice = [e for e in ev if not isinstance(e, Exception) and e.audio]
    texts = [e for e in ev if not isinstance(e, Exception) and e.text]
    assert len(voice) == 1 and voice[0].audio == b"\x00\x20" * 480                           # voz repassada; áudio MUDO descartado
    assert texts[-1].text == "Hola a todos." and texts[-1].is_final                           # fechou no turnComplete


def test_session_finalizes_by_silence_when_no_turn_complete(fake):
    fake(say_turn_complete=False)
    ev = _collect(G.GeminiSession("es"), G.IDLE_FINAL_S + 1.5)
    finals = [e for e in ev if not isinstance(e, Exception) and e.text and e.is_final]
    assert finals and finals[0].text == "Hola a todos."


def test_connection_is_lazy_no_audio_no_connection(fake):
    f = fake()
    s = G.GeminiSession("en")
    asyncio.run(s.stop())
    assert f.setups == []                                  # nada conectou: canal sem áudio não gasta crédito


def test_provider_reports_google_reason_and_goes_unhealthy(fake):
    fake(reject_reason="Your prepayment credits are depleted. Please go to AI Studio")
    p = G.GeminiProvider()
    h = asyncio.run(p.health())
    assert not h.ok and "esgotados" in h.detail and "kkkk" not in h.detail                   # motivo claro, sem vazar a chave
    with pytest.raises(Exception) as e:
        async def run():
            s = await p.start_session("pt", "en")
            await s.push_audio(b"\x00" * 3200)
            async for _ in s.stream_events():
                pass
        asyncio.run(run())
    assert "kkkk" not in str(e.value)


def test_healthy_when_handshake_ok_and_languages_come_from_docs(fake):
    fake()
    p = G.GeminiProvider()
    assert asyncio.run(p.health()).ok
    codes = {c.language for c in p.list_languages()}
    assert len(codes) >= 70 and {"en", "es", "pt", "pt-PT", "zh-Hans", "zh-Hant", "sw"} <= codes
    assert all(not c.verified for c in p.list_languages())                                   # só a documentação, não verificado


def test_end_to_end_audio_in_voice_and_text_out(client, tenant_a, fake):
    """palestrante (ingest) -> canal do idioma -> Gemini falso -> ouvinte recebe VOZ (binário) e TEXTO final."""
    f = fake()
    ev = make_event(client, tenant_a)
    assert client.post(f"/events/{ev['id']}/start", headers=tenant_a).status_code == 200
    sid = ev["sessions"][0]["id"]
    ltok = client.post(f"/public/join/{ev['join_code']}/token").json()["token"]
    itok = client.get(f"/events/sessions/{sid}/audio-token", headers=tenant_a).json()["token"]
    # o simulador (mock) só entra se o Gemini estiver fora do ar; aqui o Gemini está saudável
    with client.websocket_connect(f"/sessions/{sid}/live") as lw:
        lw.send_json({"type": "auth", "token": ltok, "lang": "es", "last_seq": 0})
        assert lw.receive_json()["type"] == "replay"
        with client.websocket_connect(f"/sessions/{sid}/ingest") as iw:
            iw.send_json({"type": "auth", "token": itok})
            assert iw.receive_json()["type"] == "ready"
            for _ in range(20):
                iw.send_bytes(speech_frame())
                time.sleep(0.01)
            got_voice, got_text, t0 = False, "", time.time()
            while time.time() - t0 < 8 and not (got_voice and got_text):
                try:
                    m = lw.receive()
                except Exception:
                    break
                if m.get("bytes"):
                    got_voice = True
                elif m.get("text"):
                    j = json.loads(m["text"])
                    if j.get("type") == "segment" and j.get("final"):
                        got_text = j["text"]
    assert got_voice, "o ouvinte deveria receber a voz traduzida (quadro binário)"
    assert got_text == "Hola a todos."
    assert f.setups[-1]["setup"]["generationConfig"]["translationConfig"]["targetLanguageCode"] == "es"  # [0] é o teste de saúde
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)


def test_text_is_split_by_sentence_and_idle(fake):
    fake(say_turn_complete=False, texts=("Bom dia a todos.", " Bem-vindos", " à sessão.", " Hoje vamos falar."))
    ev = _collect(G.GeminiSession("pt"), G.IDLE_FINAL_S + 1.5)
    finals = [e.text for e in ev if not isinstance(e, Exception) and e.text and e.is_final]
    # 1ª frase fecha quando chega texto novo após a pontuação; a 2ª idem; a última fecha pelo silêncio
    assert finals == ["Bom dia a todos.", "Bem-vindos à sessão.", "Hoje vamos falar."]


def test_silence_detector():
    assert G._is_silent(b"\x00\x00" * 1000) and not G._is_silent(b"\x00\x20" * 1000)
