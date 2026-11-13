# Build context: repository root (needs packages/financial-engine).
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv

COPY packages/financial-engine /srv/packages/financial-engine
COPY apps/api/pyproject.toml /srv/apps/api/pyproject.toml
COPY apps/api/app /srv/apps/api/app
RUN pip install /srv/packages/financial-engine "/srv/apps/api[s3]"

COPY apps/api/alembic /srv/apps/api/alembic
COPY apps/api/alembic.ini /srv/apps/api/alembic.ini
COPY apps/api/docker-entrypoint.sh /srv/apps/api/docker-entrypoint.sh

WORKDIR /srv/apps/api
RUN useradd --system --uid 10001 axiom && mkdir -p /data/storage && chown -R axiom /data
USER axiom
ENV AXIOM_STORAGE_PATH=/data/storage
EXPOSE 8000
ENTRYPOINT ["sh", "/srv/apps/api/docker-entrypoint.sh"]
