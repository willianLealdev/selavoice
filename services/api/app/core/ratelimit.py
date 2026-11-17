"""Limitador de taxa (janela deslizante) e controle de conexões WebSocket por IP.

Em memória = vale para 1 processo. Em produção com várias réplicas, trocar o backend
por Redis (INCR + EXPIRE) mantendo esta mesma interface (ver docs/DECISIONS.md, ADR-006).
"""
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window: int = 60) -> bool:
        """True = permitido. Registra o acesso."""
        now = time.monotonic()
        q = self._hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()


limiter = SlidingWindowLimiter()


def client_ip(request: Request) -> str:
    """IP do cliente. Só confia em X-Forwarded-For se vier do proxy (Traefik/Nginx) configurado."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window: int = 60):
    """Fábrica de dependência FastAPI: limita por IP + nome da rota."""
    def _dep(request: Request):
        if not limiter.check(f"{name}:{client_ip(request)}", limit, window):
            raise HTTPException(status_code=429, detail="Muitas requisições. Tente novamente em instantes.")
    return _dep


class ConnectionCounter:
    """Limita conexões WebSocket simultâneas por IP (anti-abuso)."""
    def __init__(self) -> None:
        self._n: dict[str, int] = defaultdict(int)

    def acquire(self, ip: str, max_n: int) -> bool:
        if self._n[ip] >= max_n:
            return False
        self._n[ip] += 1
        return True

    def release(self, ip: str) -> None:
        self._n[ip] = max(0, self._n[ip] - 1)


ws_counter = ConnectionCounter()
