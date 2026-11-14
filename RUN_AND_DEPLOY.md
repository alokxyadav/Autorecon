# Run & Deploy Guide

Everything you need to go from a fresh clone to a live, working demo. Follow the
sections in order — each one assumes the previous one succeeded.

---

## Prerequisites

| Tool | Version | Check with |
|---|---|---|
| Python | 3.10+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| npm | 10+ | `npm --version` |
| Docker (optional, for Option B) | any recent | `docker --version` |
| Git | any recent | `git --version` |

You'll also need an **Anthropic API key** for the AI reasoning layer (Phase 2) —
get one at https://console.anthropic.com. Everything else (matching engine, dashboard,
audit trail) works without it; only `/reconciliation/analyze` and `/query` need it.

---

## Option A — Run directly (fastest to first result)

### Fastest path: one orchestrated command

```bash
cd autorecon
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # set ANTHROPIC_API_KEY for the AI analysis step
./deploy.sh
```
This runs the full test suite, starts the backend, **polls the real `/health/ready`
endpoint** until the database connection is confirmed working (not a blind `sleep`),
then seeds demo data and runs reconciliation — in the correct order, failing fast
with a clear message at whichever step breaks rather than leaving you to guess.
Or use `make deploy` if you have `make` installed (`make help` lists every shortcut).

When it finishes, start the frontend in a second terminal:
```bash
cd frontend && npm install && npm run dev
```

### Step-by-step (if you want to see/control each stage)

### A1. Backend

```bash
cd autorecon
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Run the tests first** — confirms your environment is set up correctly before you
touch anything else:
```bash
pytest tests/ -v
```
Expected: `72 passed` (or run `python3 tests/test_matching_engine.py` etc. individually
if you don't have pytest yet — every test file has a built-in runner as a fallback).

**Configure environment variables:**
```bash
cp .env.example .env
```
Open `.env` and set at minimum:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Leave `DATABASE_URL` and `AUTORECON_API_KEY` unset for now — SQLite and no-auth are
the zero-config defaults for local dev.

**Start the server:**
```bash
uvicorn app.main:app --reload
```
You should see `Uvicorn running on http://127.0.0.1:8000`.

**Smoke-test it** (in a second terminal):
```bash
curl http://localhost:8000/health
# {"status":"ok","service":"autorecon-api"}

curl -X POST http://localhost:8000/demo/seed
curl -X POST http://localhost:8000/reconcile/run
curl "http://localhost:8000/reconciliation/results?status=unmatched"
```
If the last command returns a JSON array of discrepancies, the backend is fully working.

**Test the AI layer** (needs `ANTHROPIC_API_KEY` set and the server restarted after
setting it):
```bash
curl -X POST http://localhost:8000/reconciliation/analyze
```
Expected: `{"items_analyzed": N, "auto_resolved": X, "pending_human_review": Y}` with
N > 0. If you get a 503, check your API key is set and the `anthropic` package installed
correctly (`pip show anthropic`).

Full interactive API docs: **http://localhost:8000/docs** — useful for exploring every
endpoint without writing curl commands by hand.

### A2. Frontend

Open a new terminal:
```bash
cd autorecon/frontend
npm install
cp .env.local.example .env.local
npm run dev
```
Open **http://localhost:3000**. You should see the AutoRecon dashboard sidebar.

Click through each page in order:
1. **Dashboard** — click "Seed data & reconcile", then "Run AI analysis". Confirm the
   summary cards populate and the forecast table shows numbers.
2. **Review Queue** — enter a name, approve one item.
3. **Audit Trail** — confirm you see `match_attempt`, `ai_proposal`, and
   `human_decision` entries.
4. **Ask AutoRecon** — ask "why didn't order_00003 reconcile?" (check the Dashboard
   table for a real unmatched order_id first, since IDs are randomly generated per seed).
5. **404 handling** — visit a nonexistent route like `http://localhost:3000/xyz` and
   confirm the custom 404 page renders (see `frontend/app/not-found.tsx`) rather than
   a default Next.js error screen.

**Mobile check:** open Chrome/Firefox DevTools, toggle device toolbar (phone icon),
pick an iPhone or Android preset, and click through all four pages again. Confirm:
the hamburger menu opens/closes the nav drawer, the summary cards show 2 per row not
4 squashed together, and both tables (results, forecast) scroll horizontally instead
of squeezing columns unreadably. This was written carefully but — same as everything
else on this list — never actually opened in a browser before reaching you.

**If something breaks here:** this frontend was written carefully but has genuinely
never been executed before it reaches you (see `HANDOFF.md` for why). Treat the first
error you hit as expected work, not a sign of a deep problem — most likely causes are
listed in Troubleshooting below.

---

## Option B — Docker Compose (one command, once it's working)

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY at minimum
docker compose up --build
```
This starts Postgres, waits for it to report healthy, runs Alembic migrations,
starts the backend, waits for the backend's `/health/ready` to actually confirm
database connectivity (not just that the process started), and only then starts
the frontend — so you should never hit a race where the frontend loads before the
backend can actually serve a request.

**This has not been run in the environment that built it** (no Docker available
there — see `HANDOFF.md`'s Phase 5 log). Run it locally and work through any errors;
Dockerfiles are a common place for small path mistakes even when the underlying code
is correct. If `docker compose up --build` fails, fall back to Option A to confirm the
application logic works, then debug the Docker layer in isolation.

---

## Troubleshooting

**`ModuleNotFoundError` on `pytest tests/`**
→ Your venv isn't activated, or `pip install -r requirements.txt` didn't complete.
Re-run `pip install -r requirements.txt` and check for errors partway through.

**`uvicorn` starts but `/demo/seed` returns a 500**
→ Check the terminal running uvicorn for a traceback. Most likely cause: a stale
`autorecon.db` SQLite file from a previous schema version. Delete it and restart:
`rm autorecon.db && uvicorn app.main:app --reload`.

**Frontend shows "Failed to load reconciliation results"**
→ Open browser dev tools → Network tab → check the actual request URL and error.
Common causes: backend isn't running, `NEXT_PUBLIC_API_URL` in `.env.local` doesn't
match where the backend is actually listening, or CORS (shouldn't happen given the
permissive CORS config, but check the browser console for a CORS error message).

**`/reconciliation/analyze` returns 503**
→ `ANTHROPIC_API_KEY` isn't set, or the `anthropic` package didn't install. Check
with `pip show anthropic` and `echo $ANTHROPIC_API_KEY` (after activating your venv
and loading `.env` — note `.env` isn't auto-loaded by plain `uvicorn`; either
`export $(cat .env | xargs)` first or add `python-dotenv` loading to `app/main.py`
if this trips you up repeatedly).

**Getting a 401 on every request**
→ You set `AUTORECON_API_KEY` on the backend but the frontend isn't sending it.
Set the matching `NEXT_PUBLIC_API_KEY` in `frontend/.env.local` and restart
`npm run dev` (Next.js only reads `.env.local` at startup).

**`npm run build` or `npm run dev` fails with a type error**
→ This is the most likely real bug location, since the `.tsx` files were never
compiled before reaching you. Read the exact error — it will point to a specific
file and line. Common categories: a prop type mismatch, an unused import flagged
by strict mode, or a Tailwind class typo (won't fail the build, just won't style
correctly — check visually).

**Alembic migration fails**
→ Confirm `DATABASE_URL` is set correctly and Postgres is actually reachable
(`docker compose up db` alone, then `psql` in). The migration in
`migrations/versions/0001_initial.py` was hand-written (not autogenerated, since
alembic wasn't installed in the environment that wrote it) — if it errors, compare
it column-by-column against `app/models/*.py` to find the mismatch.

---

## Deploying live

### Backend → Railway (or Render / Fly.io — similar process)

1. Push this repo to GitHub (see below if you haven't yet).
2. Create a new Railway project, add a **Postgres** plugin, and a service pointing
   at this repo's root (it will detect the `Dockerfile`).
3. Set environment variables in Railway's dashboard: `ANTHROPIC_API_KEY`,
   `AUTORECON_API_KEY` (pick a real secret for production), `AUTO_APPROVE_CONFIDENCE_THRESHOLD`,
   `AUTO_APPROVE_MAX_AMOUNT`. Railway auto-injects `DATABASE_URL` from the Postgres
   plugin — confirm the format matches `postgresql+psycopg2://...` (Railway's default
   is `postgresql://...`; you may need to adjust the scheme or set it explicitly).
4. Deploy. Check the live `/health` endpoint once it's up.

### Frontend → Vercel

1. Import the repo into Vercel, set the **root directory** to `frontend/`.
2. Set environment variables: `NEXT_PUBLIC_API_URL` (your live Railway backend URL),
   `NEXT_PUBLIC_API_KEY` (matching the backend's `AUTORECON_API_KEY`, if you set one).
3. Deploy. Vercel auto-detects Next.js — no build config needed.
4. Visit the live URL and repeat the click-through test from A2 against production.

### Pushing to GitHub, if you haven't yet

```bash
cd autorecon
git init
git add .
git commit -m "AutoRecon: Phases 1-5 and 7, full working prototype"
git remote add origin <your-empty-github-repo-url>
git branch -M main
git push -u origin main
```
Update the `## Repo` line at the top of `HANDOFF.md` with the real URL, commit, push
again.

---

## Final pre-submission checklist

- [ ] `pytest tests/ -v` passes locally (72 tests)
- [ ] Backend deployed, `/health` responds on the live URL
- [ ] Frontend deployed, loads and successfully calls the live backend
- [ ] `/demo/seed` → `/reconcile/run` → `/reconciliation/analyze` all work on the
      **live** deployment, not just localhost
- [ ] Clicked through all four frontend pages on the live URL
- [ ] Pitch video recorded using `PITCH.md`, using the live URL in the demo
- [ ] GitHub repo is public with an up-to-date README.md and HANDOFF.md
- [ ] Submitted before **5 September 2026**
