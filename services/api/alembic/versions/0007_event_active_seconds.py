"""Horas só com fala: coluna events.active_seconds (idempotente, ver 0003)."""
revision = "0007"
down_revision = "0006"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "active_seconds" not in [c["name"] for c in insp.get_columns("events")]:
        op.add_column("events", sa.Column("active_seconds", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("events", "active_seconds")
