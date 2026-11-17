"""Ponto de entrada da API FastAPI.

Rodar local:  uvicorn app.main:app --reload --port 8000
Docs interativas (só fora de produção): http://localhost:8000/docs
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .core.middleware import SecurityMiddleware
from .db import Base, engine
from . import models  # noqa: F401  (registra as tabelas)
from .routers import admin, admin_stats, auth, billing, documents, events, live, orgs, public

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Em dev/teste criamos as tabelas direto; em produção SEMPRE use `alembic upgrade head`.
    if not settings.is_prod:
        Base.metadata.create_all(engine)
    clock = None
    if settings.event_clock_seconds > 0:  # relógio de horas de transmissão (services/event_clock.py)
        from .services.event_clock import run_forever
        clock = asyncio.create_task(run_forever(settings.event_clock_seconds))
    yield
    if clock:
        clock.cancel()


app = FastAPI(
    title="SelaVoice API", version="1.0.0", lifespan=lifespan,
    docs_url=None if settings.is_prod else "/docs",
    redoc_url=None, openapi_url=None if settings.is_prod else "/openapi.json",
)

app.add_middleware(SecurityMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_list, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Org-Slug", "X-Requested-With", "X-Client", "X-Token"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    """Nunca vaza stack trace/detalhes internos ao cliente."""
    logging.getLogger("selavoice").exception("erro não tratado em %s", request.url.path)
    return JSONResponse({"detail": "Erro interno."}, status_code=500)


@app.get("/health")
def health():
    return {"status": "ok"}


for r in (auth.router, orgs.router, events.router, live.router, billing.router, documents.router,
          documents.public_router, public.router, public.lang_router, admin.router, admin_stats.router):
    app.include_router(r)
