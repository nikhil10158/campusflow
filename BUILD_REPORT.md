# Build report

## What was built

- **Engine** (`backend/app/engine`, pure Python): numpy availability index with explanations, free-room search with "why not", independent oracle, policy engine with `BP-x.y` citations, independent validator, ranked alternatives, cohort slot finder, guest-house allocation (CP-SAT vs greedy) with waitlist, parking timelines with passes and no-show release, bundles, batch optimiser, disruption re-homing, ghost-class detection, KPIs.
- **Workflow and governance**: holds with TTL, ordered approval chains with scopes, re-check at approval ("stale - re-run alternatives"), escalation, atomic bundles (PARTIAL, accept, replace, cancel-all), concurrency-safe confirmation, hash-chained audit log with database triggers, demo clock, mock calendar and outbox, ICS feeds, PDF and Excel exports.
- **Ingestion**: CSV, Excel grid (merged cells) and PDF grid parsers, fuzzy header mapping, clarification chips, validation, preview diff, approve, version history and rollback, Gemini PDF fallback.
- **Agent**: 21 tools (3 propose-only), orchestrator with plan, verify and SSE events, offline parser, policy RAG with refusals, Gemini wrapper (rate limit, quota, fallback chain, circuit breaker), number-verified narrative.
- **Frontend**: 26 routes, light and dark themes, command palette, AI badge and quota meter, demo-clock chip, resource timeline with drag-select, campus map, heatmaps, saga board, ingestion page, disruption centre, benchmark and race page, audit viewer.
- **Ops**: `Makefile`, `run.sh`, `run.ps1`, Dockerfile, `docker-compose.yml`, `render.yaml`, `.env.example`, `scripts/` (check_gemini, demo_flow, race_demo, tamper_demo, export_openapi, smoke_deployed).

## Acceptance checklist

| Check | Result |
| --- | --- |
| Clean clone installs, seeds and tests | Done: fresh `git clone` -> `pip install -e backend` -> `python -m app.seed --reset` -> 123 tests pass. Servers were also started by hand (uvicorn + `next start`) and walked through in a browser. `make` itself was not run (not installed on this Windows machine); the Makefile only wraps those commands. |
| No key -> usable offline; key -> "AI: live" | Offline verified (badge shows "AI: offline", every demo command works). **Live mode not verified: no Gemini key was available.** |
| Oracle differential test, 100 % on 500+ queries | 500 seeded-campus queries and 600 hypothesis worlds, all identical. |
| Search p95 < 50 ms over a week, all venues | Measured 0.76 ms p95 over 7 days (Benchmark page) and asserted in `test_search_is_fast_for_all_venues_over_a_week`. |
| Ingestion: three files identical, planted errors, ambiguity, approval, rollback | `tests/test_ingest.py` (4 tests). |
| Ten scripted agent prompts | `tests/test_agent.py` runs eleven offline, including bundle, cohort, impossible request (>= 2 ranked alternatives with citations), clarify chips, cited policy, refusal, denied booking lookup, injection, closure re-home. **Not run with a live key.** |
| Race: 20 concurrent -> 1 confirmed, validator 0 | Test, `scripts/race_demo.py` and the Benchmark page: 1 winner, 19 conflicts, 0 violations (about 2.3 s). |
| No CONFIRMED without all steps; 403 on wrong scope; no LLM commit tool | `test_booking_cannot_confirm_without_every_approval_step`, `test_wrong_scope_and_wrong_role_get_403`, registry and no-write tests. |
| Guest house: overlap rejected, group <= greedy, cancellation -> promotion proposal | `test_overlapping_guest_nights_are_rejected`, `test_group_allocation_beats_or_matches_greedy`, `test_waitlist_promotes_when_room_frees` (cancel returns `waitlist_promotions`). |
| Parking: sweep-line validator, VALID / EXPIRED / WRONG LOT, no-show after DEMO_NOW | `test_parking_respects_walkin_reserve_and_splits`, validator mutation test, `test_pass_scan_results_and_no_show_release`. |
| Ghost classes flagged; release -> FREE_RELEASED | `test_ghost_classes_are_planted_and_busy_until_released`, `test_ghost_release_flips_slot_and_search_returns_it` (6 planted). |
| `/audit/verify` green; tamper turns red at the edited row | `test_audit_chain_detects_tampering`; `scripts/tamper_demo.py` prints "chain turned red at the edited row". |
| Reports and exports open; narrative numbers verified | `tests/test_exports.py` (Excel re-opened, PDFs text-checked, QR link verified, ICS validated, narrative check). |
| pytest, tsc, next build, secrets, DEPLOY.md, smoke script | 123 passed; `tsc --noEmit` clean; `next build` 26 routes; `git grep -i AIza` empty; `docs/DEPLOY.md` written; `scripts/smoke_deployed.py` passes against the local server. **Not run against a local Docker container: the Docker daemon was not running.** |
| DEMO_SCRIPT with screenshots | `docs/DEMO_SCRIPT.md`; four screenshots in `docs/screenshots/` (concierge, bundle saga, timeline selection, free-room finder). |

## Cut or not verified

- Docker image, Render and Vercel deployments, and the PostgreSQL code path (row locks, advisory lock for the audit chain, trigger function) were written but not executed.
- Gemini-backed paths (function-calling loop for free-form requests, streamed answers, PDF extraction, LLM narrative) were not run with a real key; their fallbacks are tested.
- Pre-emption of lower-priority guests (P2) was not built; promotions from the waitlist are.
- The batch optimiser handles venue events only; parking totals are not re-checked afterwards.
- "Split across two venues" exists in the alternatives engine only.
- Voice input and camera QR scanning use browser APIs (Web Speech, BarcodeDetector) and were not exercised in an automated browser.
- API responses are plain JSON objects; only request bodies get generated TypeScript types (`frontend/lib/schema.d.ts`).

## Known limitations

- Everything shares the demo clock; the daily LLM counter uses the real date.
- Rate limits are in memory and reset on restart.
- Demo accounts share one password, there is no MFA or password reset.
- Rolling a timetable back restores the old rows but not exceptions created after the import.
- Seeded holds expire 24 hours after the demo clock; use "Reset demo data" after moving the clock.
- Faculty "leave days" are planted as approved cancellations on Wednesday 25 Nov.

## Commands

```bash
make setup && make seed && make dev      # or ./run.sh, or .\run.ps1 on Windows
make test                                # pytest, tsc, next build
make reset-demo
SCALE=3 make seed
python scripts/demo_flow.py              # scripted end-to-end flow against a running API
python scripts/race_demo.py              # 20-way race
python scripts/tamper_demo.py            # audit tampering on a copy of the database
python scripts/smoke_deployed.py http://localhost:8000
python scripts/check_gemini.py           # lists usable Gemini models
```
