# Architecture

```
Next.js (Vercel)  --fetch/SSE-->  FastAPI (Render)  -->  SQLite (WAL) or PostgreSQL
                                     |
        api/  thin routers, RBAC dependencies, rate limits
        services/  workflow: holds, approvals, bundles, audit, passes, exports, ops
        agent/  tools, orchestrator, offline parser, RAG, Gemini wrapper
        ingest/  CSV, Excel grid, PDF grid -> normalise -> validate
        engine/  PURE Python, no web or LLM imports
```

## engine (the part that decides correctness)

| Module | Job |
| --- | --- |
| `availability.py` | numpy index: layers timetable, confirmed, held, maintenance plus a released layer; explains every busy bit |
| `search.py` | filter, availability, score (fit, features, distance, warnings), "why not" |
| `oracle.py` | independent naive implementation used for differential tests |
| `policy.py` | hard and soft violations with `BP-x.y` citations |
| `validator.py` | re-checks the whole state from raw rows; 9 violation codes |
| `alternatives.py` | relaxation moves costed from `rules.yaml`, verified by policy and validator |
| `cohort.py` | AND of section timetables, ranking by least disruption |
| `guesthouse.py`, `parking.py` | nights with turnover, CP-SAT group allocation, waitlist, lot timelines |
| `bundles.py`, `proposal.py` | bundle rules, `suggest_related`, one `check_request` for all resource types |
| `batch.py`, `impact.py` | CP-SAT batch optimiser, disruption re-homing |
| `ghost.py`, `utilisation.py`, `kpis.py` | telemetry, KPIs, heatmaps |

## State machine

```
agent / user drafts -> user submits -> HELD (blocks others, TTL) -> approval steps in order
   -> all approved + fresh re-check inside one transaction -> CONFIRMED (passes, calendar, notices)
   -> any rejection -> REJECTED (reason required)      -> TTL elapsed -> EXPIRED
   -> idle step past due -> ESCALATED to admin
bundle: all components HELD together -> CONFIRMED together, or PARTIAL with accept / replace / cancel-all
```

## Concurrency

Submit and confirm each run in one transaction that first takes the write lock (`BEGIN IMMEDIATE` on SQLite, row locks on PostgreSQL), builds a fresh index from the database, checks, then writes. Twenty racers for one room give one winner and nineteen conflicts with alternatives (`tests/test_workflow.py`, `scripts/race_demo.py`).

## Data

Synthetic campus from `app/seed`, deterministic (`SEED=42`): 10 buildings, 54 venues, 40 sections, 944 weekly timetable entries, 16 guest rooms, 5 parking lots, 29 bookings, 6 planted ghost classes. `data/seed/baseline.json` is the committed snapshot loaded on an empty database.

## Frontend

App Router, strict TypeScript, Tailwind with light and dark tokens, TanStack Query, zustand, Recharts. Pages are listed in `README.md`; the Concierge streams agent events over `fetch`.
