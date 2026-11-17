"""Horas de transmissão: saldo no direito (entitlements) e vínculo evento -> direito.

event_minutes_remaining NULL = ilimitado (linhas antigas continuam funcionando sem limite de horas).
"""
revision = "0003"
down_revision = "0002"
import sqlalchemy as sa
from alembic import op


def _has(table: str, col: str) -> bool:
    return any(c["name"] == col for c in sa.inspect(op.get_bind()).get_columns(table))


def upgrade() -> None:
    # IDEMPOTENTE: a migração 0001 cria as tabelas a partir dos modelos ATUAIS (create_all), então num banco NOVO
    # estas colunas já existem. Só adiciona se faltarem (bancos criados antes desta versão).
    if not _has("entitlements", "event_minutes_remaining"):
        op.add_column("entitlements", sa.Column("event_minutes_remaining", sa.Integer(), nullable=True))
    if not _has("events", "entitlement_id"):
        op.add_column("events", sa.Column("entitlement_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "entitlement_id")
    op.drop_column("entitlements", "event_minutes_remaining")
