"""Alembic: usa DATABASE_URL do ambiente e os modelos do app como fonte da verdade."""
from alembic import context
from sqlalchemy import create_engine
from app.config import get_settings
from app.db import Base
from app import models  # noqa: F401

target_metadata = Base.metadata
url = get_settings().database_url


def run_migrations_online() -> None:
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
