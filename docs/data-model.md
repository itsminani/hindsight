# Data model

Status: **accepted**, implemented by migration `001_initial_schema` (`backend/migrations/versions/`).
Database: PostgreSQL 18. IDs are opaque random strings with a type prefix (`us_`, `pl_`, `pf_`, `ps_`, `rp_`, `jb_`).

## UML class diagram

Each class is a table. `PK` = primary key, `FK` = foreign key. Numbers on the lines are multiplicities.

```mermaid
classDiagram
    direction LR

    class User {
        <<table users>>
        +id : text PK
        +email : text UNIQUE
        +password_hash : text
        +created_at : timestamptz
    }

    class Plan {
        <<table plans>>
        +id : text PK
        +owner_id : text FK
        +kind : personal | shared
        +credits_available : int CHECK >= 0
        +credits_held : int CHECK >= 0
        +created_at : timestamptz
    }

    class PlanMember {
        <<table plan_members>>
        +user_id : text PK, FK
        +plan_id : text FK
        +role : owner | member
        +joined_at : timestamptz
    }

    class Portfolio {
        <<table portfolios>>
        +id : text PK
        +owner_id : text FK
        +name : text
        +created_at : timestamptz
    }

    class Position {
        <<table positions>>
        +id : text PK
        +portfolio_id : text FK
        +ticker : text
        +shares : int CHECK > 0
        +buy_date : date
        +sell_date : date NULL, CHECK >= buy_date
    }

    class Report {
        <<table reports>>
        +id : text PK
        +portfolio_id : text FK
        +requested_by : text FK
        +plan_id : text FK
        +status : pending | done | failed
        +credits_held : int
        +credits_charged : int
        +failure_reason : text NULL
        +created_at : timestamptz
        +completed_at : timestamptz NULL
    }

    class ReportItem {
        <<table report_items>>
        +report_id : text PK, FK
        +position_id : text PK, FK
        +sold_for : numeric(14,2) NULL
        +worth_today : numeric(14,2) NULL
        +difference : numeric(14,2) NULL
    }

    class IdempotencyKey {
        <<table idempotency_keys>>
        +user_id : text PK, FK
        +key : text PK
        +request_hash : text
        +response_status : int
        +response_body : jsonb
        +created_at : timestamptz
    }

    class Job {
        <<table jobs>>
        +id : text PK
        +report_id : text FK UNIQUE
        +status : queued | running | done | failed
        +attempts : int
        +run_after : timestamptz
        +locked_at : timestamptz NULL
        +last_error : text NULL
    }

    User "1" --> "1..*" Plan : owns
    User "1" --> "1" PlanMember : belongs via
    Plan "1" --> "1..*" PlanMember : has members
    User "1" --> "0..*" Portfolio : owns
    Portfolio "1" *-- "0..*" Position : contains
    Portfolio "1" --> "0..*" Report : reports on
    User "1" --> "0..*" Report : requested
    Plan "1" --> "0..*" Report : pays for
    Report "1" *-- "1..*" ReportItem : one per position
    Position "1" --> "0..*" ReportItem : appears in
    User "1" --> "0..*" IdempotencyKey : scoped to
    Report "1" --> "0..1" Job : processed by
```

## Key rules (enforced by the database, not only by the code)

| Rule | How |
|---|---|
| A plan's credits can never go negative | `CHECK (credits_available >= 0)`, `CHECK (credits_held >= 0)` |
| A user belongs to exactly one plan at a time | `plan_members.user_id` is the primary key |
| Each user has exactly one personal plan | Unique index on `plans(owner_id) WHERE kind = 'personal'` |
| Shares are whole and positive; a sale can't be before the buy | `CHECK (shares > 0)`, `CHECK (sell_date IS NULL OR sell_date >= buy_date)` |
| An Idempotency-Key is private to the user who sent it | Primary key `(user_id, key)` |
| A report has at most one job | `UNIQUE (report_id)` on `jobs` |
| Status values are only the allowed ones | `CHECK (status IN (...))` on `reports` and `jobs` |

## Design decisions

| Decision | Why | Source |
|---|---|---|
| Credits live on the `plans` row | That row is the contended resource; requesting a report locks it with `SELECT ... FOR UPDATE` | Proposal §5, Ch7 |
| `CHECK` constraints on credits | Defense in depth: even with a bug in the code, PostgreSQL refuses an oversell | Book Ch6 p.90 |
| `plan_members` keyed by user | Removing a member moves them back to their personal plan; they never belong to two plans | Proposal §2, §7 |
| Idempotency keys scoped per user | Two users with the same key never see each other's responses | Ch3 notes p.2, 4; Book p.83-84 |
| Money as `numeric(14,2)` | Exact decimals, never floats | Contract (`Money` as string) |
| `jobs` table in the first migration | Holding credits and queueing the job happen in one transaction (outbox) | Proposal §6, Ch9 |
| Random prefixed IDs | Counters are guessable; random IDs plus 404-for-not-yours stops ID probing | Ch2 slides p.6 |

## Credit flow on one plan

```mermaid
stateDiagram-v2
    direction LR
    [*] --> Available
    Available --> Held : report requested (locked transaction)
    Held --> Charged : report done
    Held --> Available : report failed (compensation)
    Charged --> [*]
```

## Migrations

| # | Name | Contents |
|---|---|---|
| 001 | `initial_schema` | All tables above |
| 002 | `report_dividends` | `reports.include_dividends` (backward-compatible contract change) |
| 003 | `price_cache` | Cached closes and split events (after the milestone) |
