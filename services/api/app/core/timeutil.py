"""Datas sempre com fuso (UTC) nas respostas da API.

O SQLite (dev) devolve datetimes SEM fuso; o navegador interpretaria como hora local e mostraria a hora errada.
No PostgreSQL (timestamptz) já vem com fuso. Este helper garante o mesmo comportamento nos dois.
"""
from datetime import datetime, timezone


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
