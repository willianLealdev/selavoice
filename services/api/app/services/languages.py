"""Idiomas de tradução DISPONÍVEIS = união dos idiomas dos provedores configurados (e do simulador fora de produção).

Nada de lista fixa: quando um provedor está configurado e oferece descoberta (ex.: Azure), a lista vem da API dele
e aparece para o ouvinte. Cada item informa se há VOZ e/ou TEXTO e quais provedores o cobrem.
Honestidade: `discovered` = veio da API do provedor; `verified` = o fluxo completo foi testado (hoje só o simulador).
Sem nenhum provedor configurado em produção, a lista é VAZIA (a interface avisa "tradução indisponível").
"""
import time

from .channels import registry

_cache: dict = {"at": 0.0, "data": []}
_TTL = 300  # 5 min


def invalidate() -> None:
    _cache["at"] = 0.0


async def available_languages(force: bool = False) -> list[dict]:
    if not force and _cache["data"] and time.time() - _cache["at"] < _TTL:
        return _cache["data"]
    merged: dict[str, dict] = {}
    for name, p in registry.items():
        if not p.configured() or not p.streaming_implemented:
            continue  # sem adaptador ao vivo pronto, não oferece idiomas ao público
        await p.refresh_languages()
        for c in p.list_languages():
            m = merged.setdefault(c.language, {"code": c.language, "text": False, "speech": False,
                                               "providers": [], "discovered": False, "verified": False})
            m["text"] |= c.text_output
            m["speech"] |= c.speech_output
            m["discovered"] |= c.discovered
            m["verified"] |= c.verified
            if name not in m["providers"]:
                m["providers"].append(name)
    data = [merged[k] for k in sorted(merged)]
    _cache.update(at=time.time(), data=data)
    return data
