# CampusFlow

An agentic space planner for a synthetic JKLU-like university campus. It finds genuinely free classrooms across every semester, books classrooms, labs, amphitheatres, MDC guest-house rooms and visitor parking through one interface, schedules extra lectures and quizzes by intersecting section timetables, and keeps every state change behind a human approval with a tamper-evident audit log.

**SYNTHETIC DATA ONLY.** Campus, people, policies, calendars, e-mail, WhatsApp and payments are mocks.

## Run it

Needs Python 3.11+ and Node 20+.

```bash
./run.sh            # setup + seed + API on :8000 + web on :3000   (Windows: .\run.ps1)
```

or step by step:

```bash
make setup
make seed           # SCALE=3 make seed  for a 3x campus
make dev            # API :8000, web :3000
make test           # pytest, tsc, next build
make reset-demo     # restore the demo state in a few seconds
```

Open http://localhost:3000 and use a one-click chip on the login page. All demo accounts use `Demo@1234`: `admin`, `hod.cse`, `labincharge.cse`, `dean`, `estate`, `guesthouse.mgr`, `parking.officer`, `faculty01..10`, `student01..05`, `security01` (all `@jklu.demo`).

No Gemini key is needed. Without one the header shows **AI: offline** and every command runs through the deterministic parser. With `GEMINI_API_KEY` in `backend/.env` it shows **AI: live**; `python scripts/check_gemini.py` lists usable models.

## What is in it

| Area | Where |
| --- | --- |
| Availability, search, policy, validator, alternatives, cohort, guest house, parking, bundles, batch, impact | `backend/app/engine/` (pure Python) |
| Workflow, approvals, holds, audit, passes, exports | `backend/app/services/` |
| Timetable ingestion (CSV, Excel grid, PDF) | `backend/app/ingest/` |
| Agent: tools, orchestrator, offline parser, policy RAG, Gemini wrapper | `backend/app/agent/` |
| API routers | `backend/app/api/` |
| Synthetic campus and sample timetables | `backend/app/seed/`, `data/` |
| Web app | `frontend/` |
| Docs | `docs/` |

Pages: Concierge, Free Rooms (+ map), Venue Timeline (drag to test), Timetables (+ free-room heatmap), Cohort Slots, Labs, Amphitheatres, Guest House, Parking, Gate Scan, Bundles, Approvals, Policies, role dashboards, and for admins Command Center, Timetable Import, Disruptions, Utilisation and Ghost Classes, Benchmark, Audit and Outbox.

## Proof of correctness

`cd backend && python -m pytest` runs 123 tests, among them a differential test of the availability engine against an independent oracle (500 campus queries and 600 random worlds), 14 validator mutation tests, a 20-way concurrency race, parsing equivalence across CSV, Excel and PDF, RBAC and approval-gate tests, tamper detection, 15 grounded policy answers and 8 refusals.

## Docs

[Architecture](docs/ARCHITECTURE.md) | [Agent](docs/AGENT.md) | [Decisions](docs/DECISIONS.md) | [Rubric map](docs/RUBRIC_MAP.md) | [Demo script](docs/DEMO_SCRIPT.md) | [Security](docs/SECURITY.md) | [Deploy](docs/DEPLOY.md) | [Build report](BUILD_REPORT.md)
