# Build prompt (condensed)

This is a condensed copy of the brief CampusFlow was built from.

**Mission.** A demo-ready agentic system for a university campus that (1) reads semester timetables (CSV, Excel grid, PDF) and finds genuinely free classrooms for any slot, including rooms freed by cancelled, released or ghost classes; (2) manages classrooms, labs, amphitheatres, MDC guest-house rooms and visitor parking through one interface with conflict detection, policy checks, ranked alternatives and bundles; (3) finds common free time across sections for extra lectures, quizzes and workshops; (4) enforces human approval for every state change, RBAC everywhere and a tamper-evident audit log.

**Rubric (100).** Agentic capabilities 30 (planning 10, tools 10, recovery 10); domain accuracy 25 (correctness 10, grounding 10, optimisation 5); architecture 20 (code 10, performance 5, scalability 5); safety 15 (approval gates 5, RBAC 5, audit 5); demo and UX 10.

**Organiser rules.** True agent behaviour (no plain LLM wrapper); zero hallucination on institutional rules (answers only from `data/booking_policies.md`, otherwise "Not covered in the approved policies."); human-in-the-loop (the model has no submit, confirm, approve, release, import or issue tool); synthetic data only; server-side RBAC; audit of reasoning steps, tool calls, approvals; a repository that runs from a clean clone.

**Stack.** FastAPI, SQLModel (SQLite or PostgreSQL), numpy, OR-Tools CP-SAT, rank_bm25, rapidfuzz, openpyxl, pdfplumber, google-genai; Next.js, TypeScript strict, Tailwind, TanStack Query, zustand, Recharts. Frontend on Vercel, backend on Render.

**Phases.** 0 scaffold; 1 data; 2 engine; 3 workflow and API; 4 ingestion; 5 agent; 6 frontend core; 7 wow features; 8 exports and reports; 9 deploy; 10 polish. P0 before P1 before P2.

The full acceptance checklist and its results are in `BUILD_REPORT.md`.
