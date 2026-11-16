# Hindsight

[![CI](https://github.com/itsminani/hindsight/actions/workflows/ci.yml/badge.svg)](https://github.com/itsminani/hindsight/actions/workflows/ci.yml)

**Company:** StockCode · **Founder:** Team StockCode (solo founder) · SOEN 387, Fall 2026, section F

Hindsight shows investors, investment groups and partners what their past stock sales cost them
compared with holding. It is an API that a web page, a scheduled job or an AI agent can call.

## Tech stack

- Backend: Python 3.14, FastAPI, PostgreSQL, SQLAlchemy, Alembic, a background worker
- Market data: Tiingo (with an API key) or clearly labelled demo prices
- Contract: OpenAPI 3.1 (`contract/openapi.yaml`)
- Frontend: React 19 + TypeScript, Vite, TanStack Query, Recharts; types generated from the contract
- Run: Docker Compose (db, migrate, api, worker, web) · CI: GitHub Actions

## Repository layout

| Folder | What's in it |
|---|---|
| `contract/` | The OpenAPI contract, the source of truth for the API |
| `backend/src/hindsight/api/` | Interface layer: HTTP routes, request/response models |
| `backend/src/hindsight/service/` | Service layer: use cases, transactions, permission checks |
| `backend/src/hindsight/domain/` | Domain layer: business rules (credits, reports) |
| `backend/src/hindsight/repositories/` | Data-source layer: repository interfaces and their PostgreSQL implementations |
| `backend/src/hindsight/integrations/` | Foreign integrations: the price provider interface, Tiingo and demo adapters |
| `backend/src/hindsight/worker.py` | The background worker that computes queued reports |
| `backend/migrations/` | Alembic migrations (001 schema, 002 report price source) |
| `backend/tests/` | Automated tests |
| `conformance/` | Black-box tests: the running service against the contract |
| `frontend/` | The web app (and a developer lab at `/lab`) |
| `docs/` | Data model and design notes |
| `.github/workflows/` | CI pipeline |

## Features

- Sign in with email and password, get a 15-minute Bearer token (JWT)
- Portfolios and positions; you only ever see your own (someone else's is a 404, like a missing one)
- Plans with credits: personal plans, and shared plans whose owner adds and removes members
- Request a hindsight report: holds one credit per ticker on your plan and queues the work
  (202 + polling). Safe under concurrency (`SELECT ... FOR UPDATE`) and safe to retry
  (`Idempotency-Key`)
- A background worker computes each report from market prices, charges the held credits, or
  retries with backoff and releases them if it can't finish
- Price history for charts: `GET /tickers/{ticker}/prices`
- Health checks: `/health/live` (process up) and `/health/ready` (database reachable)

## Running it

Requires Docker Desktop.

```bash
cp .env.example .env                              # first time only; local development values
docker compose up --build                         # db, migrations, API, worker and web app
docker compose exec api python -m hindsight.seed  # demo users and portfolios (once)
```

- The app: http://localhost:3000 (developer lab: http://localhost:3000/lab)
- API docs (the contract): http://localhost:8000/docs
- Health: http://localhost:8000/health/live and /health/ready
- Stop: `Ctrl+C`, or `docker compose down` (add `-v` to also delete the database)

Demo accounts (password: `HINDSIGHT_SEED_PASSWORD` from `.env`):

| Email | Plan |
|---|---|
| alice@example.com | Owns the shared "family" plan (10 credits) |
| bob@example.com | Member of Alice's plan |
| carol@example.com | Personal plan with 1 credit (shows `402 insufficient_credits`) |

Real market data: put a free [Tiingo](https://www.tiingo.com) key in `.env` as
`HINDSIGHT_TIINGO_API_KEY`. Without one, the app uses generated demo prices and says so on screen.

More workers: `docker compose up -d --scale worker=3` (jobs are claimed with `SKIP LOCKED`).

### Without Docker (API and tests)

Needs PostgreSQL running (`docker compose up -d db` is enough).

```bash
cd backend
python -m uv run alembic upgrade head                     # apply migrations
python -m uv run python -m hindsight.seed                 # demo data
python -m uv run uvicorn hindsight.main:app --reload
python -m uv run python -m hindsight.worker               # in another terminal
python -m uv run pytest                                   # tests use their own hindsight_test database
```

Frontend with hot reload (API on port 8000):

```bash
cd frontend
npm ci
npm run dev                                               # http://localhost:5173
```

### Conformance tests (black box, against the contract)

`conformance/` never imports the server: it calls a running API over HTTP and checks every
response (status, content type, body) against `contract/openapi.yaml`. Local servers only.

```bash
docker compose up -d --build && docker compose exec api python -m hindsight.seed --reset
cd conformance
HINDSIGHT_SEED_PASSWORD=demo-password-local-only python -m uv run pytest
```

### Database changes

The schema lives in `backend/src/hindsight/repositories/orm.py`; every change is a migration in
`backend/migrations/versions/` (see `docs/data-model.md`).

```bash
python -m uv run alembic revision --autogenerate -m "what changed"   # then review the file
python -m uv run alembic check                                       # models and migrations agree?
```
