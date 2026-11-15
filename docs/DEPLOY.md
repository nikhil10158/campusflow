# Deploy

Run the live demo locally (or on a paid always-on instance). Keep the deployed link as a backup: the free tiers sleep and are slow.

## Backend on Render (Blueprint)

1. Push the repository to GitHub.
2. Render dashboard -> New -> Blueprint -> pick the repo. `render.yaml` creates a Docker web service (`backend/Dockerfile`, build context = repo root) and a free PostgreSQL database.
3. Set `GEMINI_API_KEY` (optional, leave empty for offline mode). `JWT_SECRET` and `PASS_SECRET` are generated.
4. Copy the service URL, for example `https://campusflow-api.onrender.com`.
5. After the frontend exists, set `FRONTEND_ORIGINS` to the Vercel URL (comma separate several). Previews work through `FRONTEND_ORIGIN_REGEX=https://.*\.vercel\.app`.

`/health` answers instantly; `/health/ready` turns true once the database is seeded. On an empty database `AUTO_SEED_ON_EMPTY=true` loads `data/seed/baseline.json` in a few seconds. `DATABASE_URL` values starting with `postgres://` or `postgresql://` are rewritten to the `psycopg` driver.

## Frontend on Vercel

1. Import the repository, set **Root Directory** to `frontend`.
2. Set the only variable: `NEXT_PUBLIC_API_URL` = the Render URL.
3. Deploy, then add the Vercel URL to `FRONTEND_ORIGINS` on Render and redeploy the backend.

The browser calls Render directly, including the SSE stream. There are no Next API routes. While the free backend wakes up (about a minute) the app shows "Waking up the planner..." and polls `/health/ready`.

## Keep it awake

Free web services sleep after 15 idle minutes. Ping `https://<api>/health` every 5 minutes from any uptime monitor.

## Free-tier facts to plan around

- 512 MB RAM and 0.1 CPU: solves stay small and time-limited (`SOLVER_TIME_LIMIT_S`, `SOLVER_WORKERS`); the index is a few megabytes.
- Ephemeral disk: SQLite would vanish on restart, hence PostgreSQL. No state is written to local disk; exports are generated on demand.
- The free Render PostgreSQL expires after 30 days.

## Check a deployment

```bash
python scripts/smoke_deployed.py https://campusflow-api.onrender.com
```

It checks readiness, login, a free-room search, a short benchmark, an offline-mode agent command and the audit chain.

## Local Docker

```bash
docker compose up --build
```

API on :8000 (SQLite in a volume), web on :3000.
