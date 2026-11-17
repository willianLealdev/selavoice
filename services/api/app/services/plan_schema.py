"""Regras de um PLANO: quais limites existem, como validar e como ler (inclusive "ilimitado").

CONVENÇÃO DO "ILIMITADO": o limite existe no plano com valor `null` (None) = SEM LIMITE.
Chave AUSENTE = valor padrão antigo (planos criados antes desta versão continuam como eram).
Em saldos (contadores) o ilimitado vira o número gigante UNLIM, que nunca chega a zero.

LIMITES (todos configuráveis no Super Admin -> Planos):
  Tempo de transmissão (HORAS contadas desde o INÍCIO da transmissão, não do agendamento)
    included_hours       horas de transmissão incluídas (por período mensal ou por compra avulsa)
    max_event_hours      teto de horas de UM evento (ao atingir, o evento é encerrado automaticamente)
    extra_hour_cents     preço da hora extra (INFORMATIVO: a cobrança automática de excedente não existe ainda)
  Pessoas
    listener_concurrency ouvintes simultâneos por evento
    admin_seats          administradores/operadores da equipe
  Idiomas
    max_languages        idiomas de tradução simultâneos por evento
    allowed_languages    lista de idiomas permitidos (vazia = todos os que os provedores oferecem)
    included_language_minutes  minutos-idioma incluídos (1 idioma ouvido por 1 min = 1)
  Eventos
    included_events      eventos incluídos (por período/compra)
    max_concurrent_events eventos AO VIVO ao mesmo tempo
  Recursos
    recordings, pdf_booklets, retention_days
  Excedente
    overage              hard_stop (para) | topup (permite créditos comprados)
"""
import re

UNLIM = 1_000_000_000  # "ilimitado" nos contadores de saldo

LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
INT_FIELDS = ("included_events", "included_language_minutes", "max_languages", "listener_concurrency",
              "max_concurrent_events", "admin_seats", "retention_days", "extra_hour_cents")
HOUR_FIELDS = ("included_hours", "max_event_hours")
BOOL_FIELDS = ("recordings", "pdf_booklets")
OVERAGE = ("hard_stop", "topup")


class PlanError(ValueError):
    pass


def normalize(raw: dict) -> dict:
    """Valida e limpa os limites enviados pelo painel. Chaves desconhecidas são descartadas."""
    out: dict = {}
    for k in INT_FIELDS:
        if k in raw:
            v = raw[k]
            if v is not None:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v > UNLIM:
                    raise PlanError(f"Valor inválido em {k}.")
                v = int(v)
            out[k] = v
    for k in HOUR_FIELDS:
        if k in raw:
            v = raw[k]
            if v is not None:
                if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v > 100_000:
                    raise PlanError(f"Valor inválido em {k}.")
                v = round(float(v), 2)
            out[k] = v
    for k in BOOL_FIELDS:
        if k in raw:
            out[k] = bool(raw[k])
    if "allowed_languages" in raw:
        langs = raw["allowed_languages"] or []
        if not isinstance(langs, list) or len(langs) > 300 or not all(isinstance(x, str) and LANG_RE.match(x) for x in langs):
            raise PlanError("Lista de idiomas inválida.")
        out["allowed_languages"] = sorted({x.lower() for x in langs})
    if "overage" in raw:
        if raw["overage"] not in OVERAGE:
            raise PlanError("Política de excedente inválida.")
        out["overage"] = raw["overage"]
    return out


def limit(limits: dict | None, key: str, default=None):
    """Lê um limite. Retorna None quando é ILIMITADO. Chave ausente => `default`."""
    l = limits or {}
    return l[key] if key in l else default


def max_event_minutes(limits: dict | None) -> int | None:
    """Teto de duração de UM evento, em minutos (None = sem teto). Aceita o campo antigo `max_event_minutes`."""
    l = limits or {}
    if "max_event_hours" in l:
        return None if l["max_event_hours"] is None else int(round(l["max_event_hours"] * 60))
    if "max_event_minutes" in l:
        return l["max_event_minutes"]
    return None


def grant_amounts(limits: dict | None) -> dict:
    """Saldos iniciais ao conceder o plano (período/compra). UNLIM = ilimitado; event_minutes None = ilimitado."""
    l = limits or {}
    ev = UNLIM if ("included_events" in l and l["included_events"] is None) else int(l.get("included_events", 0) or 0)
    lm = UNLIM if ("included_language_minutes" in l and l["included_language_minutes"] is None) else int(l.get("included_language_minutes", 0) or 0)
    h = l.get("included_hours") if "included_hours" in l else None
    return {"events": ev, "language_minutes": lm, "event_minutes": None if h is None else int(round(h * 60))}


def is_unlimited(n: int | None) -> bool:
    return n is None or n >= UNLIM // 2
