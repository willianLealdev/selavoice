"""Conexão com o banco e utilitários de isolamento por tenant.

ISOLAMENTO (defesa em camadas):
1) Camada de aplicação: toda consulta de dado de cliente passa por `scoped()`,
   que SEMPRE filtra por tenant_id vindo da membership autenticada.
2) Camada de banco (PostgreSQL): políticas RLS (ver alembic/versions/0002_rls.py) usam
   a variável de sessão `app.tenant_id`, definida por `set_tenant_context()`.
Assim, mesmo que um desenvolvedor esqueça um filtro, o banco nega o acesso.
"""
from typing import Iterator, Type, TypeVar
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        # Integridade referencial e melhor concorrência no SQLite local.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


class Base(DeclarativeBase):
    """Base de todos os modelos."""


def get_db() -> Iterator[Session]:
    """Dependência FastAPI: uma sessão por requisição, sempre fechada."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_tenant_context(db: Session, tenant_id: str | None) -> None:
    """Informa ao PostgreSQL qual tenant está ativo (usado pelas políticas RLS)."""
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": tenant_id or ""})


T = TypeVar("T")


def scoped(db: Session, model: Type[T], tenant_id) -> "select":
    """SELECT já filtrado pelo tenant. Use SEMPRE para modelos com tenant_id."""
    return select(model).where(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
