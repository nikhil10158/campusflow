# Decisions

One line per non-obvious choice.

- `rules.yaml` is the single source of truth for numbers; a test fails if any number in it is missing from `data/booking_policies.md`, so the two cannot drift apart.
- Alternative-cost and search weights are written into the policy file (BP-9) so that the "every number appears in the policies" test holds without exceptions.
- Times are stored as naive Asia/Kolkata datetimes (`NaiveDatetime`) because SQLModel's default `UTCDateTime` forces timezone-aware values and the whole campus lives in one zone.
- The availability index is a numpy boolean cube (venue x day x layer x 96 slots); a 54-venue campus over 150 days is about 2 MB and a week-long search takes under a millisecond.
- A class occupies `[floor15(start), ceil15(end))`, so a 09:55 class end still blocks until 10:00; buffers are applied to the requesting side only.
- Classrooms have 0-minute buffers; a 15-minute classroom buffer would make almost every period unbookable because periods are back to back.
- Holiday-freed slots are plain FREE; only a cancelled, released or moved class produces FREE_RELEASED.
- Ghost-candidate slots stay busy until a release is approved; they are only labelled in the "why not" list.
- The oracle re-implements availability with minute intervals and no arrays; hypothesis builds 600 random worlds (exceptions, holds, holidays, maintenance, buffers, midnight crossing) and compares every venue's state.
- The validator shares only the dataclass types with the engine, never its logic, so a bug in the index cannot hide itself.
- The validator is lenient in one direction only: it uses real minutes while the index rounds up to 15 minutes, so the index may be stricter but never looser.
- Guest nights "cover" an event when check-in date <= event start date and check-out date >= event end date; parking must cover the exact event window.
- Holds block other requests; an expired hold stops blocking at once because the snapshot treats `hold_expires_at <= now` as free.
- SQLite runs in WAL mode; write requests start `BEGIN IMMEDIATE`, reads stay deferred, so readers never block the single writer.
- Long-running endpoints (agent, race, benchmark) use a short read session for authentication so they do not hold the SQLite write lock.
- Confirmation re-reads the database with a fresh index inside the approving transaction; the cached index is only used for display and search.
- On Postgres the same code takes `SELECT ... FOR UPDATE` on the resource rows (`db.lock_resource`); this path is written but was not run locally.
- The race simulator races full request-to-confirm cycles, because holds make overlapping HELD rows impossible by design: exactly one submit wins, the rest get alternatives.
- Bundle confirmation is all-or-nothing; a rejected or expired component turns the bundle PARTIAL and stops auto-confirmation until the requester accepts, replaces or cancels.
- Pass verification (`GET /verify/pass/...`) never changes state; only the security-role `POST /passes/scan` marks a pass scanned.
- Passes carry an HMAC-SHA256 over id, type, resource, window and plate; the token is `id.first-24-hex-of-signature`.
- The audit hash is `sha256(prev_hash + canonical_json(row))`, written in the same transaction as the change, with database triggers blocking UPDATE and DELETE.
- Passwords use `bcrypt` directly instead of `passlib`, because passlib is unmaintained and breaks with bcrypt 4+.
- The agent never has a state-changing tool; a registry test checks names and a second test proves the propose tools leave the row counts unchanged.
- The offline parser is the primary path and Gemini enriches it (free-form requests, final answer wording); every demo command works without a key.
- Gemini answers are post-checked: policy answers must cite retrieved rule IDs and use only numbers from them; narratives and answers must use only numbers present in the computed JSON.
- A clarification answer is appended to the original sentence ("... on 17 Nov"), so the stateless parser can continue without server-side conversation state.
- Students must name a faculty sponsor before the agent plans anything for them (policy BP-1.2).
- Timetable uploads for part of the campus merge with the sections they do not mention; exceptions are copied onto identical entries of the new version.
- An import is blocked while any error-level issue or open clarification remains.
- Daily LLM usage is counted by real calendar date, while every booking rule uses the demo clock.
- The frontend calls the API directly (also SSE) with `fetch`; `EventSource` cannot send POST bodies or an Authorization header.
- The resource timeline is plain CSS and pointer events; no paid scheduler library is used.
- `make seed SCALE=3` triples venues, sections and faculty; the committed baseline only covers SCALE=1, larger scales are generated on the fly.
