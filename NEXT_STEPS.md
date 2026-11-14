# Next Steps — What To Actually Do Now

`HANDOFF.md` is written for the next Claude session/account to read. This file is
for you — a plain checklist, in order, to go from "code exists" to "submitted."

---

## 1. Verify the backend runs (10 min)

```bash
cd autorecon
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pytest tests/ -v          # expect 44 passed
uvicorn app.main:app --reload
```

In another terminal:
```bash
curl -X POST http://localhost:8000/demo/seed
curl -X POST http://localhost:8000/reconcile/run
curl "http://localhost:8000/reconciliation/results?status=unmatched"
```
If you see JSON results back, the backend works end to end. If something breaks,
fix it here before moving on — don't build the frontend against a broken API.

## 2. Push to GitHub (5 min)

```bash
git init
git add .
git commit -m "Phases 1-4: matching engine, AI reasoning, policy gate, forecast, frontend"
git remote add origin <your-repo-url>
git push -u origin main
```
Update the `## Repo` line at the top of `HANDOFF.md` with the real URL.

## 3. Add your real Anthropic API key and test Phase 2 (10 min)

```bash
cp .env.example .env
# edit .env, set ANTHROPIC_API_KEY=sk-ant-...
```
Restart `uvicorn`, then:
```bash
curl -X POST http://localhost:8000/reconciliation/analyze
```
Check the response — `items_analyzed`, `auto_resolved`, `pending_human_review`
should all be non-zero if the seed data has discrepancies (it does, by design).
This is the one piece of Phase 2 that genuinely hasn't been run yet — do this
before anything else, since if it fails you want time to fix it.

## 4. Get the frontend running (15–30 min — most likely place for real bugs)

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```
Open `http://localhost:3000`. Click through all four pages:
- Dashboard → "Seed data & reconcile" → "Run AI analysis" → click a row
- Review Queue → enter your name → approve one item
- Audit Trail → confirm you see match_attempt, ai_proposal, human_decision entries
- Ask AutoRecon → ask "why didn't order_00003 reconcile?" (pick a real seeded order_id)

This was written carefully but never executed — treat any error here as expected
work, not a sign something's fundamentally wrong. Most likely issues: an import
path typo or a Tailwind class that needs adjusting. Fix and move on.

## 5. Wire the forecast into the dashboard (30 min, optional but strong differentiator)

The `/forecast` endpoint exists but isn't rendered anywhere in the UI yet. Add
a simple section to `frontend/app/page.tsx` that calls `api.getForecast()` and
shows the daily expected/low/high figures — even a plain table is fine, a chart
is a nice-to-have.

## 6. Deploy (30–45 min)

- Backend: Railway, Render, or Fly.io — set `DATABASE_URL` to their managed
  Postgres, set `ANTHROPIC_API_KEY`.
- Frontend: Vercel — set `NEXT_PUBLIC_API_URL` to your deployed backend URL.
- Confirm the live URL works exactly like your local run did.

## 7. Record the pitch video

Use `PITCH.md` as your script. Screen-record the live demo flow from Step 4,
using your deployed URL, not localhost, so it matches what judges will see if
they click through themselves.

## 8. Final submission checklist

- [ ] GitHub repo is public, README.md is current, HANDOFF.md shows all phases complete
- [ ] Live backend URL works
- [ ] Live frontend URL works and talks to the live backend
- [ ] Pitch video recorded and uploaded
- [ ] Submitted before 5 September 2026

---

## If you're short on time, prioritize in this order:
1. Backend running + tests passing (Step 1) — non-negotiable, this is your proof of work
2. Frontend running locally (Step 4) — judges need to *see* something
3. Deploy (Step 6) — a live link is worth more than perfect polish
4. Forecast in UI (Step 5) — nice differentiator, cut first if pressed for time
5. Pitch video (Step 7) — can be rougher than the product itself, still needs to exist
