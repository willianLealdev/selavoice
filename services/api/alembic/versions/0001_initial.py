"""Schema inicial: cria todas as tabelas a partir dos modelos (baseline).
Mudanças futuras: `alembic revision --autogenerate -m "descricao"` e revisar o arquivo gerado."""
revision = "0001"
down_revision = None
from alembic import op
from app.db import Base
from app import models  # noqa: F401


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
