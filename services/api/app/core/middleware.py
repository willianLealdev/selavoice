"""Middlewares: cabeçalhos de segurança, ID de requisição, limite de tamanho e log JSON.

Cabeçalhos aplicados (mitigam XSS, clickjacking, sniffing, vazamento de referrer):
CSP restritiva, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, HSTS, Permissions-Policy.
"""
import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from ..config import get_settings

settings = get_settings()
log = logging.getLogger("selavoice")

# Campos que NUNCA podem aparecer em logs (PII/segredos).
_REDACT = {"password", "token", "authorization", "refresh_token", "access_token", "secret", "code"}


def redact(d: dict) -> dict:
    return {k: ("***" if k.lower() in _REDACT else v) for k, v in d.items()}


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        # Limite de corpo (anti-abuso). Rotas de webhook também passam aqui.
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > settings.max_body_bytes:
            return JSONResponse({"detail": "Corpo da requisição grande demais."}, status_code=413)
        t0 = time.perf_counter()
        resp = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        resp.headers["X-Request-ID"] = rid
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "camera=(), geolocation=(), microphone=(self)"
        if request.url.path not in ("/docs", "/openapi.json"):  # Swagger (só dev) precisa de CDN
            resp.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        resp.headers["Cache-Control"] = "no-store"
        if settings.is_prod:
            resp.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        # Log estruturado JSON (sem corpo, sem cabeçalhos sensíveis).
        log.info(json.dumps({"rid": rid, "method": request.method, "path": request.url.path,
                             "status": resp.status_code, "ms": round(ms, 1)}))
        return resp
