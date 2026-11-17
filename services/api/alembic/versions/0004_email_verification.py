"""Confirmação de e-mail: coluna users.email_verified_at + tabela email_verifications.

IDEMPOTENTE (ver 0003): num banco NOVO a 0001 já criou tudo a partir dos modelos atuais.
CONTAS JÁ EXISTENTES são marcadas como confirmadas (cadastraram antes desta regra; não podem ser trancadas fora).
"""
revision = "0004"
down_revision = "0003"
import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "email_verified_at" not in [c["name"] for c in insp.get_columns("users")]:
        op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
        op.execute("UPDATE users SET email_verified_at = created_at")   # só na 1ª vez: contas antigas ficam confirmadas
    if "email_verifications" not in insp.get_table_names():
        op.create_table(
            "email_verifications",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_email_verifications_user_id", "email_verifications", ["user_id"])


def downgrade() -> None:
    op.drop_table("email_verifications")
    op.drop_column("users", "email_verified_at")
