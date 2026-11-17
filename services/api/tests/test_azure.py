"""Azure Speech: funções puras do adaptador + recusa de chave inválida (usa a internet; ignora se offline).

ATENÇÃO: a tradução real do Azure NUNCA foi executada (falta chave/região do usuário)."""
import array
import asyncio

import pytest

from app.providers.azure_session import AzureSession, pick_voice, resample_16k_to_24k, source_locale, target_code
from app.services import secrets_store as sec

VOICES = [{"Locale": "en-US", "ShortName": "en-US-JennyNeural", "VoiceType": "Neural"},
          {"Locale": "en-GB", "ShortName": "en-GB-SoniaNeural", "VoiceType": "Neural"},
          {"Locale": "sw-KE", "ShortName": "sw-KE-RafikiNeural", "VoiceType": "Neural"},
          {"Locale": "pt-BR", "ShortName": "pt-BR-FranciscaNeural", "VoiceType": "Neural"}]


def test_locale_and_voice_mapping():
    assert source_locale("pt") == "pt-BR" and source_locale("en") == "en-US" and source_locale("es-MX") == "es-MX"
    assert source_locale("sw", VOICES) == "sw-KE"                    # idioma raro: acha pela lista de vozes
    assert target_code("zh") == "zh-Hans" and target_code("en") == "en"
    assert pick_voice("en", VOICES) == "en-US-JennyNeural" and pick_voice("pt", VOICES) == "pt-BR-FranciscaNeural"
    assert pick_voice("zu", VOICES) is None                          # sem voz => só texto


def test_resample_16k_to_24k_length_and_values():
    a = array.array("h", [0, 1000, 2000, 3000, 4000, 5000])
    out = array.array("h"); out.frombytes(resample_16k_to_24k(a.tobytes()))
    assert len(out) == 9 and out[0] == 0 and 0 <= out[1] <= 1500    # 6 amostras -> 9 (x1,5), interpolação suave


def test_invalid_key_becomes_clean_provider_error_not_crash():
    sec.save("azure", {"key": "0" * 32, "region": "eastus"}, [], True)
    try:
        async def go():
            s = AzureSession("pt", "en", VOICES)
            for _ in range(10):
                await s.push_audio(b"\x00" * 640)
                await asyncio.sleep(0.02)
            try:
                async for _ in s.stream_events():
                    pass
            finally:
                await s.stop()
        with pytest.raises(Exception) as e:
            asyncio.run(asyncio.wait_for(go(), 40))
        msg = str(e.value)
        if "connect" in msg.lower() and "401" not in msg:
            pytest.skip("sem acesso à internet")
        assert "Azure" in msg and "0" * 32 not in msg                # erro claro e sem vazar a chave
    finally:
        sec.save("azure", {}, ["key", "region"], None)
