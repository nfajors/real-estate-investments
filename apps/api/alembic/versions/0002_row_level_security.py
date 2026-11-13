"""Row-level security: tenant isolation policies on every org-scoped table.

The API binds each transaction to a tenant with
``set_config('app.current_org_id', <org uuid>, true)``. Policies only expose
rows of that tenant. FORCE makes the policies apply to the table owner too.
The application should connect as a non-superuser role without BYPASSRLS
(set AXIOM_DB_APP_ROLE to grant it DML privileges here).

Revision ID: 0002
Revises: 0001
"""
import os

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

RLS_TABLES = (
    "properties", "documents", "document_pages", "extracted_data", "scenarios",
    "underwriting_results", "financing_structures", "chat_messages", "audit_logs",
)
TENANT = "NULLIF(current_setting('app.current_org_id', true), '')::uuid"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in RLS_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY tenant_isolation ON {t} USING (org_id = {TENANT}) WITH CHECK (org_id = {TENANT})")
    role = os.environ.get("AXIOM_DB_APP_ROLE")
    if role:
        op.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"')
        op.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"')


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for t in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
