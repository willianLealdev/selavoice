"""Evento privado: coluna events.access_password_hash (idempotente, ver 0003)."""
revision = "0006"
down_revision = "0005"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "access_password_hash" not in [c["name"] for c in insp.get_columns("events")]:
        op.add_column("events", sa.Column("access_password_hash", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "access_password_hash")
