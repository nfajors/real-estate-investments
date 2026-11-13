"""Database engine/session management with tenant context for Postgres RLS.

Every request that operates inside an organization stores the org id in
``session.info["org_id"]``. Whenever that session begins a transaction we
issue ``set_config('app.current_org_id', <org>, true)`` (transaction-local), so
Postgres row-level security policies only ever expose that tenant's rows – even
if an application-layer filter were forgotten.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import JSON, create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings

JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True}
    if settings.database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(settings.database_url, **kwargs)
    if settings.database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, transaction, connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    org_id = session.info.get("org_id")
    connection.execute(
        text("SELECT set_config('app.current_org_id', :org, true)"),
        {"org": str(org_id) if org_id else ""},
    )


def set_tenant(session: Session, org_id) -> None:
    """Bind a session to a tenant; re-applies immediately if a transaction is open."""
    session.info["org_id"] = str(org_id) if org_id else None
    if session.in_transaction() and session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(
            text("SELECT set_config('app.current_org_id', :org, true)"), {"org": session.info["org_id"] or ""}
        )


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
