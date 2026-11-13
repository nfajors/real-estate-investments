"""Axiom API application factory."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Base, engine
from .routers import analysis, auth, documents, orgs, properties, reports, scenarios


class JsonFormatter(logging.Formatter):
    """Structured logs. Never log request bodies, tokens or emails (no PII in logs)."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": round(record.created, 3), "level": record.levelname, "logger": record.name,
                   "msg": record.getMessage()}
        for key in ("request_id", "method", "path", "status", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("axiom")
    root.handlers = [handler]
    root.setLevel(get_settings().log_level)
    root.propagate = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    _configure_logging()
    if not get_settings().is_postgres:
        # SQLite dev/test databases are created directly; Postgres uses Alembic migrations.
        Base.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Axiom API",
        version="1.0.0",
        description="AI-assisted commercial real estate underwriting. Deterministic engine; AI proposes, humans verify.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Org-Id"],
    )
    access_log = logging.getLogger("axiom.http")

    @app.middleware("http")
    async def security_and_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        access_log.info("request", extra={"request_id": request_id, "method": request.method,
                                          "path": request.url.path, "status": response.status_code,
                                          "duration_ms": round((time.perf_counter() - start) * 1000, 1)})
        return response

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # pragma: no cover - defensive
        logging.getLogger("axiom").exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Internal server error"}, status_code=500)

    @app.get("/api/health", tags=["meta"])
    def health():
        from axiom_engine import ENGINE_VERSION

        from .services.ai import ai_available

        return {"status": "ok", "engine_version": ENGINE_VERSION, "ai_available": ai_available()}

    for r in (auth.router, orgs.router, properties.router, scenarios.router, analysis.router, documents.router,
              reports.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()
