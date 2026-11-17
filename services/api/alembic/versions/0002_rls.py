"""Row-Level Security (PostgreSQL): o banco NEGA acesso a linhas de outro tenant.

Cada requisição define `app.tenant_id` (set_tenant_context). As políticas comparam tenant_id com ele.
FORCE ROW LEVEL SECURITY vale também para o dono da tabela. Jobs/seed globais usam o papel
`selavoice_admin` (BYPASSRLS), que NUNCA é usado pela API de requisições.
STATUS: escrito, mas NÃO executado nesta máquina (sem Docker/PostgreSQL) — ver docs/BLOCKERS.md.
"""
revision = "0002"
down_revision = "0001"
from alembic import op
from app.models import TENANT_TABLES


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return  # SQLite local: isolamento só na camada de aplicação
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING (tenant_id::text = current_setting('app.tenant_id', true)) "
            f"WITH CHECK (tenant_id::text = current_setting('app.tenant_id', true))"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
