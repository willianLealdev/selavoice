"""Filtro de voz (portão), calibração, cobrança só com tradução, idioma do evento e configuração da organização."""
import time

import pytest

from app.providers import gemini as G
from app.services import secrets_store as sec
from app.services.audio_gate import AudioGate, DEFAULT_AUDIO, clean_audio, get_audio
from app.services.channels import ACTIVE_HOLD_S, _Chan, manager
from conftest import make_event, speech_frame
from test_gemini import FakeGemini


def _feed(gate, frames):
    return [gate.process(f) for f in frames]


def _passed(out):
    return sum(1 for o in out if any(any(c) for c in o))


# ---------------------------------------------------------------- portão de voz
def test_gate_blocks_quiet_background_after_speaker_established():
    g = AudioGate("normal")
    # o palestrante fala (forte) por 2 s => o portão aprende o volume dele
    _feed(g, [speech_frame(amp=8000, phase=i * 320) for i in range(100)])
    speaker = _passed(_feed(g, [speech_frame(amp=8000, phase=i * 320) for i in range(50)]))
    # conversa de fundo ~ -22 dB (bem mais baixa): não passa
    bg = _passed(_feed(g, [speech_frame(amp=600, freq=330, phase=i * 320) for i in range(100)]))
    assert speaker == 50 and bg == 0
    assert g.stats()["dropped_pct"] > 15


def test_gate_keeps_word_onsets_with_preroll_and_ends_with_short_silence():
    g = AudioGate("normal")
    _feed(g, [speech_frame(amp=8000, phase=i * 320) for i in range(100)])
    _feed(g, [b"\x00" * 640 for _ in range(60)])                       # silêncio longo: fecha o portão
    out = _feed(g, [b"\x00" * 640 for _ in range(10)])
    assert sum(len(c) for o in out for c in o) == 0                    # depois do "fim de frase" NADA é enviado (nem custa)
    out = g.process(speech_frame(amp=8000))                            # volta a falar: o 1º quadro vem com a pré-rolagem
    assert len(out) >= 2 and sum(len(c) for c in out) >= 640 * 2


def test_gate_off_passes_everything_but_still_measures_speech():
    g = AudioGate("off")
    out = _feed(g, [speech_frame(amp=8000)] * 10 + [b"\x00" * 640] * 10)
    assert all(o and len(o[0]) == 640 for o in out)
    assert 0.15 < g.speech_s < 0.25                                    # 10 quadros de 20 ms com voz


def test_calibration_learns_speaker_before_chatter():
    g = AudioGate("normal")
    g.start_calibration(1.0)
    _feed(g, [speech_frame(amp=8000, phase=i * 320) for i in range(55)])   # o palestrante fala ~1 s
    assert g.calibrated and not g.calibrating and g.level > 4000
    # conversa de fundo logo no início (antes de qualquer fala do palestrante): já é bloqueada
    assert _passed(_feed(g, [speech_frame(amp=900, freq=300, phase=i * 320) for i in range(60)])) == 0


def test_calibration_without_speech_does_not_set_level():
    g = AudioGate("normal")
    g.start_calibration(0.5)
    _feed(g, [b"\x00" * 640 for _ in range(30)])
    assert not g.calibrated and g.level == 0.0


# ---------------------------------------------------------------- cobrança só com tradução
def test_billing_counts_only_time_with_translation_not_silence(monkeypatch):
    ch = _Chan(tenant_id=None, event_id=None, session_id="s", lang="en", source_lang="pt")
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    manager._touch_active(ch)                       # 1º evento: conta o "respiro" (<= ACTIVE_HOLD_S)
    for _ in range(10):                             # 10 s de tradução contínua (evento a cada 1 s)
        now[0] += 1.0
        manager._touch_active(ch)
    assert 10 <= ch.active_s <= 10 + ACTIVE_HOLD_S
    before = ch.active_s
    now[0] += 120.0                                 # 2 MINUTOS de silêncio (nenhum evento): não acumula
    assert ch.active_s == before
    manager._touch_active(ch)                       # voltou a falar: soma no máximo o "respiro", nunca os 120 s
    assert ch.active_s <= before + ACTIVE_HOLD_S


# ---------------------------------------------------------------- idioma do evento (Gemini)
def _collect(session, seconds=2):
    import asyncio

    async def go():
        ev = []

        async def rd():
            try:
                async for e in session.stream_events():
                    ev.append(e)
            except Exception as e:
                ev.append(e)
        t = asyncio.create_task(rd())
        for _ in range(40):
            await session.push_audio(b"\x00" * 640)
            await asyncio.sleep(0.01)
        await asyncio.sleep(seconds)
        await session.stop()
        await t
        return ev
    return asyncio.run(go())


@pytest.fixture()
def gem(monkeypatch):
    def make(**kw):
        f = FakeGemini(**kw)
        monkeypatch.setattr(G, "URL", f"ws://127.0.0.1:{f.port}/ws")
        sec.save("gemini", {"api_key": "k" * 12}, [], True)
        G.LAST_ERROR.update(msg="", at=0.0, ok_at=0.0)
        return f
    yield make
    sec.save("gemini", {}, ["api_key"], None)
    G.LAST_ERROR.update(msg="", at=0.0, ok_at=0.0)


def test_foreign_language_speech_is_not_translated(gem):
    gem(texts=("Hello all.",), input_texts=["Good morning everyone."], input_lang="en")
    s = G.GeminiSession("es"); s.strict_source = "pt"                      # o evento é em português; falaram inglês
    ev = _collect(s, 1.5)
    assert not [e for e in ev if not isinstance(e, Exception) and (e.audio or e.text or e.original)]   # nada vai ao público


def test_event_language_speech_is_translated(gem):
    gem(texts=("Hola a todos.",), input_texts=["Bom dia a todos."], input_lang="pt")
    s = G.GeminiSession("es"); s.strict_source = "pt"
    ev = _collect(s, 1.5)
    assert [e for e in ev if not isinstance(e, Exception) and e.audio] and [e for e in ev if not isinstance(e, Exception) and e.text]


def test_without_strict_language_everything_is_translated(gem):
    gem(texts=("Hello all.",), input_texts=["Good morning everyone."], input_lang="en")
    ev = _collect(G.GeminiSession("es"), 1.5)                              # filtro de idioma desligado
    assert [e for e in ev if not isinstance(e, Exception) and e.text]


# ---------------------------------------------------------------- configuração da organização
def test_audio_defaults_and_validation():
    assert get_audio({}) == DEFAULT_AUDIO and get_audio({"audio": {"filter": "strong"}})["filter"] == "strong"
    assert clean_audio({"filter": "off", "noise_suppression": False}) == {"filter": "off", "noise_suppression": False}
    with pytest.raises(ValueError):
        clean_audio({"filter": "turbo"})


def test_org_audio_settings_api(client, tenant_a):
    assert client.get("/organizations/me", headers=tenant_a).json()["audio"] == DEFAULT_AUDIO
    r = client.patch("/organizations/me", json={"audio": {"filter": "strong", "only_event_language": False}}, headers=tenant_a)
    assert r.status_code == 200
    a = client.get("/organizations/me", headers=tenant_a).json()["audio"]
    assert a["filter"] == "strong" and a["only_event_language"] is False and a["noise_suppression"] is True   # o resto não muda
    assert client.patch("/organizations/me", json={"audio": {"filter": "turbo"}}, headers=tenant_a).status_code == 422


# ---------------------------------------------------------------- ponta a ponta: silêncio não vai ao provedor
def test_silence_never_reaches_provider_but_voice_does(client, tenant_a, gem):
    f = gem(texts=("Hola.",))
    ev = make_event(client, tenant_a)
    client.post(f"/events/{ev['id']}/start", headers=tenant_a)
    sid = ev["sessions"][0]["id"]
    ltok = client.post(f"/public/join/{ev['join_code']}/token").json()["token"]
    itok = client.get(f"/events/sessions/{sid}/audio-token", headers=tenant_a).json()["token"]
    assert client.post(f"/sessions/{sid}/audio-calibrate", headers=tenant_a).status_code == 409      # sem captura: não calibra
    with client.websocket_connect(f"/sessions/{sid}/live") as lw:
        lw.send_json({"type": "auth", "token": ltok, "lang": "es", "last_seq": 0})
        lw.receive_json()
        with client.websocket_connect(f"/sessions/{sid}/ingest") as iw:
            iw.send_json({"type": "auth", "token": itok})
            assert iw.receive_json()["type"] == "ready"
            for _ in range(60):                                       # 1,2 s só de SILÊNCIO
                iw.send_bytes(b"\x00" * 640)
                time.sleep(0.005)
            time.sleep(0.5)
            assert f.audio_msgs == []  # nada foi ao provedor (e portanto nada é cobrado)
            assert client.post(f"/sessions/{sid}/audio-calibrate", headers=tenant_a).status_code == 200
            for i in range(300):                                      # agora VOZ
                iw.send_bytes(speech_frame(phase=i * 320))
                time.sleep(0.003)
            time.sleep(0.8)
            st = client.get(f"/sessions/{sid}/ingest-status", headers=tenant_a).json()
    assert f.audio_msgs                                               # a voz chegou ao provedor
    assert st["filter"]["mode"] == "normal" and st["filter"]["dropped_pct"] > 0
    client.post(f"/events/{ev['id']}/stop", headers=tenant_a)
