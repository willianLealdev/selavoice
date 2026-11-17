"""Configurações da plataforma (teste grátis editável no painel). Idempotente (ver 0003/0004)."""
revision = "0005"
down_revision = "0004"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    if "platform_settings" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "platform_settings",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("key", sa.String(60), nullable=False, unique=True),
            sa.Column("value", sa.JSON(), nullable=False),
        )
        op.create_index("ix_platform_settings_key", "platform_settings", ["key"])


def downgrade() -> None:
    op.drop_table("platform_settings")
