# Security and governance

- **Synthetic only.** Campus, people, policies, calendars, e-mail, WhatsApp and payments are mocks. A banner and footer say so in every view.
- **Human in the loop.** The model has no commit tool. Submitting, approving, rejecting, releasing, importing, issuing and scanning are HTTP endpoints that need an authenticated human role.
- **RBAC on the server.** JWT (HS256, 8 h) with bcrypt-hashed passwords. `require_roles` guards endpoints; approval steps also check the user's scopes (`hod:CSE`, `lab_incharge:cs`, `estate`, `dean`, `guesthouse_mgr`, `parking_officer`). Wrong scope returns 403 and is audited. Tests: `tests/test_workflow.py`.
- **Privacy by design.** Non-admin users see "Busy" only on timelines, searches and ICS venue feeds; students see only their own bookings; only synthetic data and short prompts go to Gemini.
- **Audit.** Append-only table with a SHA-256 hash chain and database triggers that refuse UPDATE and DELETE. `GET /audit/verify` recomputes the chain; `scripts/tamper_demo.py` edits a copy of the database and shows verification failing at the edited row.
- **Prompt injection.** User text is data. Known attack phrases are refused before any tool runs; role checks run in code; the system prompt wraps user text in `<user_request>` tags. A test sends an injection and asserts no tool call and no state change.
- **Secrets.** Only environment variables; `.env` is git-ignored and `.env.example` ships. `git grep -i AIza` is empty.
- **Transport and abuse.** CORS restricted to `FRONTEND_ORIGINS` (plus an optional regex for preview deployments), rate limits on login and agent endpoints, `X-Forwarded-*` honoured behind a proxy.
- **Known gaps.** No password reset or MFA (demo accounts share one password); in-memory rate limits reset on restart; the Postgres locking path has not been exercised in this environment.
