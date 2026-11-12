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

Work in progress. Planned for the milestone: portfolios and positions, sign-in with tokens, shared
credit plans, and requesting a hindsight report with credits protected under concurrency.

## Running it

Coming soon (one command with Docker Compose).
