"""Postgres row-level security checks (skipped on SQLite)."""

import pytest
from sqlalchemy import text

from app.db import SessionLocal, engine, set_tenant

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="RLS requires PostgreSQL")


def test_rls_hides_rows_without_or_with_other_tenant(owner, prop, client):
    from conftest import register

    other = register(client, org="Other Tenant")
    other.post("/api/properties", json={"name": "Other deal", "property_type": "office",
                                        "purchase_price": 5_000_000, "rentable_sf": 20_000})
    db = SessionLocal()
    try:
        # No tenant bound → policies expose nothing, even though rows exist.
        assert db.execute(text("SELECT count(*) FROM properties")).scalar() == 0
        assert db.execute(text("SELECT count(*) FROM underwriting_results")).scalar() == 0
        db.rollback()
        set_tenant(db, owner.org_id)
        names = {r[0] for r in db.execute(text("SELECT name FROM properties"))}
        assert names == {prop["name"]}
        # Cross-tenant writes are rejected by WITH CHECK.
        with pytest.raises(Exception):
            db.execute(text("UPDATE properties SET org_id = :o"), {"o": other.org_id})
            db.flush()
    finally:
        db.rollback()
        db.close()
