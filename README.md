# Hindsight

**Company:** StockCode · **Founder:** Team StockCode (solo founder) · SOEN 387, Fall 2026, section F

Hindsight shows investors, investment groups and partners what their past stock sales cost them
compared with holding. It is an API that a web page, a scheduled job or an AI agent can call.

## Tech stack

- Backend: Python 3.14, FastAPI, PostgreSQL, SQLAlchemy, Alembic
- Contract: OpenAPI 3.1 (`contract/openapi.yaml`)
- Frontend: React + TypeScript (for testing the service)
- Run: Docker Compose

## Repository layout

| Folder | What's in it |
|---|---|
| `contract/` | The OpenAPI contract, the source of truth for the API |
| `backend/src/hindsight/api/` | Interface layer: HTTP routes, request/response models |
| `backend/src/hindsight/service/` | Service layer: use cases, transactions, permission checks |
| `backend/src/hindsight/domain/` | Domain layer: business rules (credits, reports) |
| `backend/src/hindsight/repositories/` | Data-source layer: repository interfaces and their PostgreSQL implementations |
| `backend/tests/` | Automated tests |
| `frontend/` | Small web page for testing the service |
| `docs/` | Design notes and diagrams |

## Features

- Sign in with email and password, get a 15-minute Bearer token (JWT)
- Portfolios and positions; you only ever see your own (someone else's is a 404, like a missing one)
- Plans with credits: personal plans, and shared plans whose owner adds and removes members
- Request a hindsight report: holds one credit per ticker on your plan and queues the work
  (202 + polling). Safe under concurrency (`SELECT ... FOR UPDATE`) and safe to retry
  (`Idempotency-Key`)
- Health checks: `/health/live` (process up) and `/health/ready` (database reachable)

Next: the background worker that computes the reports from market prices.

## Running it

Requires Docker Desktop.

```bash
cp .env.example .env                              # first time only; local development values
docker compose up --build                         # migrates the database, then starts the API
docker compose exec api python -m hindsight.seed  # demo users and portfolios (once)
```

- API docs (the contract): http://localhost:8000/docs
- Health: http://localhost:8000/health/live and /health/ready
- Stop: `Ctrl+C`, or `docker compose down` (add `-v` to also delete the database)

Demo accounts (password: `HINDSIGHT_SEED_PASSWORD` from `.env`):

| Email | Plan |
|---|---|
| alice@example.com | Owns the shared "family" plan (10 credits) |
| bob@example.com | Member of Alice's plan |
| carol@example.com | Personal plan with 1 credit (shows `402 insufficient_credits`) |

### Without Docker (API and tests)

Needs PostgreSQL running (`docker compose up -d db` is enough).

```bash
cd backend
python -m uv run alembic upgrade head                     # apply migrations
python -m uv run python -m hindsight.seed                 # demo data
python -m uv run uvicorn hindsight.main:app --reload
python -m uv run pytest                                   # tests use their own hindsight_test database
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
