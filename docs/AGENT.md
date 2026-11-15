# Agent

## Shape of a run

`POST /agent/chat` streams Server-Sent Events:

`start` -> `plan` (checklist) -> `tool_call` / `tool_result` / `plan_progress` ... -> `verify` -> `proposal` -> `answer_delta` ... -> `done`. A `clarify` event ends a run early with chips; a `refusal` event is sent for prompt-injection patterns. Every event is written to the audit log.

## Tools (`agent/tools.py`)

Read: `declare_plan`, `resolve_entity`, `get_timetable`, `search_free_rooms`, `busy_reasons`, `find_common_free_slots`, `check_policy`, `check_guesthouse`, `check_parking`, `suggest_related`, `recommend_alternatives`, `assess_disruption`, `utilisation_report`, `detect_ghost_classes`, `search_policies`, `explain`, `get_booking`, `my_bookings`.

Propose (nothing stored): `plan_bundle`, `propose_release`, `propose_rehome`.

There is no submit, confirm, approve, release, import or issue tool. `execute()` checks the user's role against each tool's allowed roles in code; students get free-room search without private details, policy search and their own bookings.

## Orchestration

1. Parse the sentence with the deterministic parser (dates, times, counts, venue codes, sections, buildings).
2. Missing date, time, attendee count or entity -> `clarify` chips (no model call spent).
3. Known intent -> a scripted plan that calls the same tools the model would (at most six tool executions).
4. Unknown intent and a usable Gemini key -> manual function-calling loop (`automatic_function_calling` disabled, at most three tool turns); the first turn must call `declare_plan`.
5. Verification without a model: every proposal re-runs the policy engine and the independent validator; an invalid proposal is never described as ready.
6. The final answer is streamed from Gemini without tools when available; its numbers must appear in the tool results, otherwise a template answer replaces it.

A run uses at most four model calls.

## Offline mode

No key, an open circuit, a 429 or an exhausted daily quota all end in the same place: the deterministic parser, extractive policy answers (top rule verbatim with its ID) and template explanations. `GET /agent/status` reports `live`, `degraded` or `offline`.

## `llm.py`

Token-bucket RPM limit, persisted daily counter (`LLMUsage`), retry-delay-aware backoff on 429, model fallback chain, circuit breaker (three failures -> offline for 60 s), response cache for deterministic calls.

## Policy Q&A (`rag.py`)

Rules are split by ID, BM25 retrieval, and an overlap check against the question's terms. Below the threshold the answer is exactly `Not covered in the approved policies.` Gemini may only rephrase retrieved rules; cited IDs must be among the retrieved rules and every number must occur in a cited rule.

## Safety tests

`tests/test_agent.py` covers eleven scripted prompts, the tool registry, a no-DB-write check, role limits, an injection attempt and audit coverage. `tests/test_grounding.py` covers 15 answered and 8 refused questions.
