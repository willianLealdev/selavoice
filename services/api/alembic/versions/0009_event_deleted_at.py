"""Exclusão de evento (lógica): coluna events.deleted_at (idempotente, ver 0003)."""
revision = "0009"
down_revision = "0008"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "deleted_at" not in [c["name"] for c in insp.get_columns("events")]:
        op.add_column("events", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "deleted_at")
