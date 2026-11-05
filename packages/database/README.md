# packages/database

The source of truth for the schema is the SQLAlchemy models in
`apps/api/app/models.py` and the Alembic migrations in `apps/api/alembic/versions/`:

| Migration | Contents |
|-----------|----------|
| `0001_initial_schema` | All Phase 1 tables (users, organizations, members, invitations, refresh tokens, properties, documents, document pages, extracted data, scenarios, underwriting results, financing structures, chat messages, audit logs) with indexes, soft-delete and audit columns. |
| `0002_row_level_security` | Enables and **forces** Postgres RLS on every tenant-owned table with a `tenant_isolation` policy keyed on `app.current_org_id`, and grants DML to the non-superuser app role. |

`schema.sql` in this folder is the generated PostgreSQL DDL (`alembic upgrade head --sql`),
kept for review and for DBAs. Regenerate it after adding a migration:

```bash
cd apps/api && AXIOM_DATABASE_URL=postgresql+psycopg://x:y@localhost/z alembic upgrade head --sql > ../../packages/database/schema.sql
```
