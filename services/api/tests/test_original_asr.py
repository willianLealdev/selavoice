"""Transcrição do ORIGINAL ao vivo: Deepgram (servidor FALSO imitando o protocolo) e reserva pelo Gemini.

ATENÇÃO: valida a NOSSA implementação; o Deepgram real foi validado à parte, em teste manual curto (docs/BLOCKERS.md)."""
import asyncio
import json
import threading
import time
import uuid

import websockets
from sqlalchemy import select

from app.db import SessionLocal
from app.models import TranscriptSegment
from app.providers import gemini as G
from app.services import original_asr, secrets_store as sec
from conftest import make_event, speech_frame
from test_gemini import FakeGemini


class FakeDeepgram:
    def __init__(self):
        self.urls, self.audio_bytes = [], 0
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        assert self.ready.wait(5)

    def _run(self):
        asyncio.set_event_loop(self.loop)

        async def handler(ws):
            self.urls.append(ws.request.path)
            sent = False
            async for m in ws:
                if isinstance(m, bytes):
                    self.audio_bytes += len(m)
                    if not sent:
                        sent = True

                        def res(txt, final, speech_final):
                            return json.dumps({"type": "Results", "is_final": final, "speech_final": speech_final,
                                               "channel": {"alternatives": [{"transcript": txt}]}})
                        await ws.send(res("Bom dia", False, False))
                        await ws.send(res("Bom dia a todos.", True, False))
                        await ws.send(res("Sejam bem-vindos.", True, True))     # fim da fala => fecha o parágrafo
                        await ws.send(res("Hoje falaremos de crescimento.", True, True))

        async def main():
            self.server = await websockets.serve(handler, "127.0.0.1", 0)
            self.port = self.server.sockets[0].getsockname()[1]
            self.ready.set()
            await asyncio.Future()
        self.loop.run_until_complete(main())


def _originals(session_id):
    with SessionLocal() as db:
        rows = db.scalars(select(TranscriptSegment).where(TranscriptSegment.session_id == uuid.UUID(session_id),
                                                          TranscriptSegment.kind == "original").order_by(TranscriptSegment.seq)).all()
        return [(r.text, r.is_final, r.provider, r.language) for r in rows]


def _run_ingest(client, h, ev, seconds=1.2):
    sid = ev["sessions"][0]["id"]
    itok = client.get(f"/events/sessions/{sid}/audio-token", headers=h).json()["token"]
    with client.websocket_connect(f"/sessions/{sid}/ingest") as iw:
        iw.send_json({"type": "auth", "token": itok})
        assert iw.receive_json()["type"] == "ready"
        t0 = time.time()
        while time.time() - t0 < seconds:
            iw.send_bytes(speech_frame())
            time.sleep(0.02)
    time.sleep(0.8)   # fecha a transcrição (entrega o que faltava)
    return sid


def test_deepgram_original_transcript_grouped_by_speech_final(client, tenant_a, monkeypatch):
    f = FakeDeepgram()
    monkeypatch.setattr(original_asr, "URL", f"ws://127.0.0.1:{f.port}/v1/listen")
    sec.save("deepgram", {"api_key": "d" * 12}, [], True)
    try:
        ev = make_event(client, tenant_a, original_language="pt")
        assert client.post(f"/events/{ev['id']}/start", headers=tenant_a).status_code == 200
        sid = _run_ingest(client, tenant_a, ev)
        segs = _originals(sid)
        finals = [t for t, fin, prov, lang in segs if fin]
        assert finals == ["Bom dia a todos. Sejam bem-vindos.", "Hoje falaremos de crescimento."]   # 1 segmento por fim de fala
        assert all(prov == "deepgram" and lang == "pt" for _, _, prov, lang in segs)
        assert "language=pt-BR" in f.urls[0] and "encoding=linear16" in f.urls[0] and "sample_rate=16000" in f.urls[0]
        assert f.audio_bytes > 0 and not original_asr.active(sid)                                  # fechou ao fim da ingestão
        client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
    finally:
        sec.save("deepgram", {}, ["api_key"], None)


def test_original_not_published_to_listeners(client, tenant_a, monkeypatch):
    f = FakeDeepgram()
    monkeypatch.setattr(original_asr, "URL", f"ws://127.0.0.1:{f.port}/v1/listen")
    sec.save("deepgram", {"api_key": "d" * 12}, [], True)
    try:
        ev = make_event(client, tenant_a, original_language="pt")
        client.post(f"/events/{ev['id']}/start", headers=tenant_a)
        sid = ev["sessions"][0]["id"]
        ltok = client.post(f"/public/join/{ev['join_code']}/token").json()["token"]
        with client.websocket_connect(f"/sessions/{sid}/live") as lw:
            lw.send_json({"type": "auth", "token": ltok, "lang": "pt", "last_seq": 0})
            assert lw.receive_json()["type"] == "replay"
            _run_ingest(client, tenant_a, ev, 1.0)
            seen = []
            t0 = time.time()
            while time.time() - t0 < 1.5:
                try:
                    m = lw.receive()
                except Exception:
                    break
                if m.get("text"):
                    seen.append(json.loads(m["text"]))
        assert not [m for m in seen if m.get("type") == "segment" and "Bom dia" in m.get("text", "")]   # original não vaza ao ouvinte
        client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
    finally:
        sec.save("deepgram", {}, ["api_key"], None)


def test_gemini_original_is_fallback_when_deepgram_off(client, tenant_a, monkeypatch):
    g = FakeGemini(texts=("Hello all.",))
    g.input_texts = ["Hola a todos.", " Bienvenidos."]
    monkeypatch.setattr(G, "URL", f"ws://127.0.0.1:{g.port}/ws")
    sec.save("gemini", {"api_key": "k" * 12}, [], True)
    G.LAST_ERROR.update(msg="", at=0.0, ok_at=0.0)
    try:
        ev = make_event(client, tenant_a, original_language="es")
        client.post(f"/events/{ev['id']}/start", headers=tenant_a)
        sid = ev["sessions"][0]["id"]
        ltok = client.post(f"/public/join/{ev['join_code']}/token").json()["token"]
        with client.websocket_connect(f"/sessions/{sid}/live") as lw:        # 2 canais (en e fr) => grava o original UMA vez
            lw.send_json({"type": "auth", "token": ltok, "lang": "en", "last_seq": 0})
            lw.receive_json()
            with client.websocket_connect(f"/sessions/{sid}/live") as lw2:
                lw2.send_json({"type": "auth", "token": ltok, "lang": "fr", "last_seq": 0})
                lw2.receive_json()
                _run_ingest(client, tenant_a, ev, 1.0)
                time.sleep(G.IDLE_FINAL_S + 1)
        segs = _originals(sid)
        finals = [t for t, fin, prov, lang in segs if fin]
        assert finals == ["Hola a todos.", "Bienvenidos."] or finals == ["Hola a todos. Bienvenidos."]
        assert all(prov == "gemini" and lang == "es" for _, _, prov, lang in segs)          # idioma ORIGINAL do evento
        assert len(finals) <= 2                                                                # não duplicou por canal
        client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
    finally:
        sec.save("gemini", {}, ["api_key"], None)
        G.LAST_ERROR.update(msg="", at=0.0, ok_at=0.0)
