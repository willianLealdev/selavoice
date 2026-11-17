"""Pacotes de recarga: tabela topup_packs (idempotente, ver 0003)."""
revision = "0008"
down_revision = "0007"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "topup_packs" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "topup_packs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="usd"),
        sa.Column("status", sa.String(12), nullable=False, server_default="published"),
        sa.Column("stripe_price_id", sa.String(80), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("topup_packs")
