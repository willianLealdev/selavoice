"""Dados de contato PÚBLICOS da organização (endereço, site, redes sociais...).

Aparecem para todo o público (perfil e tela do ouvinte) para a pessoa confirmar que está no lugar certo.
SEGURANÇA: tudo é texto curto e VALIDADO. Links só aceitam http/https (bloqueia `javascript:` e similares) e
redes sociais são guardadas como "usuário" (o link é montado pelo sistema), então o organizador não consegue
colocar um destino arbitrário num campo de rede social.
"""
import re

TEXT = {"description": 400, "address": 200, "city": 100, "phone": 30, "whatsapp": 30}
URLS = {"website": 200}
HANDLES = {"instagram": (r"[A-Za-z0-9._]{1,30}", ("instagram.com",)), "facebook": (r"[A-Za-z0-9.\-_]{1,60}", ("facebook.com", "fb.com")),
           "youtube": (r"@?[A-Za-z0-9._\-]{1,60}", ("youtube.com",)), "tiktok": (r"[A-Za-z0-9._]{1,30}", ("tiktok.com",))}
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,120}\.[^@\s]{2,}$")
PHONE = re.compile(r"^[0-9+()\-.\s]{5,30}$")


class ContactError(ValueError):
    pass


def _handle(field: str, raw: str) -> str:
    pattern, hosts = HANDLES[field]
    v = raw.strip()
    m = re.match(r"^(?:https?://)?(?:www\.|m\.)?([^/]+)/(?:@)?([^/?#]+)", v)
    if m and any(m.group(1).lower() == h for h in hosts):  # aceita colar o link do perfil
        v = m.group(2)
    v = v.lstrip("@") if field != "youtube" else v
    if not re.fullmatch(pattern, v):
        raise ContactError(f"Campo inválido: {field}.")
    return v


def clean_contact(data: dict) -> dict:
    """Valida e normaliza. Campo vazio = remove. Campos desconhecidos são ignorados."""
    out: dict[str, str] = {}
    for k, v in data.items():
        v = ("" if v is None else str(v)).strip()
        if not v:
            continue
        if k in TEXT:
            if len(v) > TEXT[k]:
                raise ContactError(f"Texto muito longo: {k}.")
            if k in ("phone", "whatsapp") and not PHONE.match(v):
                raise ContactError(f"Telefone inválido: {k}.")
            out[k] = v
        elif k == "email":
            if not EMAIL.match(v):
                raise ContactError("E-mail de contato inválido.")
            out[k] = v
        elif k in URLS:
            if not re.match(r"^https?://", v, re.I):
                v = "https://" + v
            if len(v) > URLS[k] or not re.match(r"^https?://[^\s<>\"']+\.[^\s<>\"']+$", v, re.I):
                raise ContactError("Endereço do site inválido.")
            out[k] = v
        elif k in HANDLES:
            out[k] = _handle(k, v)
    return out


def social_links(c: dict) -> dict:
    """Monta os links finais das redes (o front só exibe)."""
    base = {"instagram": "https://instagram.com/{}", "facebook": "https://facebook.com/{}",
            "youtube": "https://youtube.com/{}", "tiktok": "https://tiktok.com/@{}"}
    return {k: base[k].format(c[k]) for k in base if c.get(k)}
