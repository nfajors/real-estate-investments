.PHONY: setup test test-engine test-api test-web dev-api dev-web e2e samples

VENV ?= .venv
PY := $(VENV)/bin/python

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -e "packages/financial-engine[test]" -e "apps/api[test]" pypdf
	cd apps/web && npm ci

test: test-engine test-api test-web

test-engine:
	cd packages/financial-engine && ../../$(PY) -m pytest --cov

test-api:
	cd apps/api && ../../$(PY) -m pytest

test-web:
	cd apps/web && npx tsc --noEmit && npm run lint && npm run build

dev-api:
	cd apps/api && ../../$(VENV)/bin/uvicorn app.main:app --reload --port 8000

dev-web:
	cd apps/web && npm run dev

e2e:
	cd apps/web && npx playwright test

samples:
	cd apps/api && ../../$(PY) -m app.services.demo_docs ../../samples
