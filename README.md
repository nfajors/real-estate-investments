# Axiom — AI-Powered CRE Investment & Underwriting Platform

Axiom is an institutional-grade underwriting workspace for commercial real estate. Deterministic, fully tested
financial engines do the calculating. AI only proposes extracted values and explains results. A person verifies
every number before it enters a model.

> **Demo data:** new workspaces can load five fictional sample deals, each labelled `[DEMO]`.
> Every export of a demo deal carries a *For Demonstration Purposes Only* watermark.

## Repository layout

| Path | What it is |
|------|------------|
| `packages/financial-engine` | Pure-Python calculation library (`axiom_engine`) with **100% line + branch coverage**: TVM/IRR, debt schedules, the DCF underwriting engine, scenarios & sensitivity, Monte Carlo, valuation reconciliation, financing comparison, development feasibility, risk scoring |
| `apps/api` | FastAPI backend: auth, organizations and roles, Postgres row-level security, deals, scenarios, documents, AI and rule-based extraction, verification, reports, AI analyst |
| `apps/web` | Next.js 16 (App Router) + Tailwind v4 + Radix/shadcn-style UI + React Query + Recharts |
| `packages/database` | Generated PostgreSQL DDL (`schema.sql`) and a migration guide. The source of truth is the Alembic migrations in `apps/api/alembic` |
| `packages/shared` | Generated OpenAPI contract (`openapi.json`) |
| `docker-compose.yml`, `infra/` | Full local stack: Postgres with RLS, the API, and the web app |

## Quick start (local development)

Requirements: Python 3.11+, Node 22+. PostgreSQL is optional; SQLite works for development.

```bash
make setup
```

```bash
make dev-api        # http://localhost:8000/api/docs
```

```bash
make dev-web        # http://localhost:3000  (proxies /api to :8000)
```

Open http://localhost:3000/register, create a workspace and keep **Load sample portfolio** ticked.

### Full stack with Docker (Postgres + RLS)

```bash
docker compose up --build
```

Migrations run as the owner role. The API connects as `axiom_app`, a role with neither superuser rights nor
`BYPASSRLS`, so row-level security is always enforced.

### Enabling AI

Set `ANTHROPIC_API_KEY` in the API's environment. The default model is `claude-opus-5-5` (`AXIOM_AI_MODEL`).
Without a key, the platform still works end to end:

* extraction uses the deterministic rule-based extractor (`heuristic-v1`);
* the analyst answers from rule-based templates built on engine output;
* image uploads are stored but need AI to be extracted.

All settings are listed in `apps/api/.env.example`.

## How it works

**Workflow (PRD §5):** create a workspace → invite your team → create a deal → upload an OM, T12 or rent roll →
review extractions side by side (accept, edit or reject) → apply the verified values to a scenario → edit
assumptions with live recalculation → run scenarios, sensitivity tables and Monte Carlo → compare financing
structures and deals → export the Excel model, the one-pager or the IC memo → ask the AI analyst.

**Financial accuracy**
* All maths lives in `axiom_engine`. The web app never computes financial figures.
* Every stored result keeps the full assumption snapshot, the engine version, and an audit trace of each headline
  metric's formula and inputs.
* A 10-year model calculates in about 2 ms; the PRD target is under 500 ms.
* Validation rejects impossible inputs and flags aggressive ones (for example rent growth above 8%, exit cap below
  3.5%, LTV above 80%, a loan maturing before exit).
* The Excel export rebuilds the whole model with **live formulas** (assumptions → monthly debt schedule → cash
  flow → returns). A reconciliation block compares each formula result with the engine's value. CI recalculates
  the workbook with LibreOffice and asserts the two agree to within 1e-6.

**Document intelligence**
* PDFs are parsed per page (pdfplumber); spreadsheets per sheet with cell references.
* With AI enabled, Claude returns structured output with a confidence score and a verbatim excerpt for each field.
  The server checks every excerpt against the parsed text. If it isn't found, confidence is capped at 0.35 and the
  field is marked *unverified citation*.
* The verification view highlights the cited region on the rendered page image, or the cited cells for
  spreadsheets. Keyboard shortcuts: `j`/`k` to move, `a` to accept, `r` to reject.
* Only accepted or edited values can be applied to a scenario. Each review and apply is written to the audit log
  and stored as a new version.

**Security**
* Authentication: scrypt password hashes; short-lived JWT access tokens kept in memory only; rotating refresh
  tokens in an httpOnly cookie, with reuse detection that revokes the whole token family.
* Roles: Owner, Admin, Analyst and Viewer, checked on every endpoint, plus plan limits and feature flags.
* Tenant isolation: every query filters by organization in the application. In addition, Postgres RLS uses `FORCE`
  policies keyed on a transaction-local `app.current_org_id`.
* Files are encrypted at rest (AES-256-GCM locally, server-side encryption on S3) and served only through
  short-lived HMAC-signed URLs.
* Logs are structured JSON with no PII. Security headers are set on every response.

## Testing

```bash
make test-engine
```

```bash
make test-api
```

```bash
make test-web
```

```bash
make e2e
```

* `make test-engine` runs 139 tests, compares results with numpy-financial, and fails below 100% coverage.
* `make test-api` runs 45 integration tests. To exercise RLS, point `AXIOM_TEST_DATABASE_URL` at a migrated
  Postgres database and connect as the app role.
* `make test-web` runs the typecheck, the linter and the production build.
* `make e2e` runs the Playwright critical-path test. It needs the API and the web app running.

CI (`.github/workflows/ci.yml`) runs all of these, testing the API against both SQLite and Postgres with RLS.

## Roadmap status

| Phase | Status |
|-------|--------|
| **1 – MVP** | Auth, organizations and roles; deal CRUD and dashboard; uploads and storage; extraction and verification; the engine; the assumptions editor with live underwriting; scenarios; PDF and Excel exports; light and dark themes |
| **2 – Advanced** | AI analyst chat, Monte Carlo, financing structures with preferred equity and covenants, valuation reconciliation, multi-deal comparison, the IC memo generator (AI narrative is optional and labelled) |
| **3 – Institutional** | Development feasibility is a basic beta behind a feature flag. Portfolio analytics, SSO and market-data integrations are behind disabled flags. Billing is Stripe-ready: it runs in manual mode until `AXIOM_STRIPE_*` keys are set |

Use `make samples` to write the sample OM PDF and the rent-roll/T12 workbook to `samples/` for upload testing.
