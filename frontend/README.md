# AutoRecon Frontend

Next.js 14 (App Router) + Tailwind dashboard for AutoRecon.

## Setup

```bash
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL if backend isn't on localhost:8000
npm run dev
```

Open http://localhost:3000. Requires the backend running (see the root README.md).

## Note on this build

This code was written and reviewed carefully but **not run through `npm install`/`next build`**
in the environment that generated it (no network access there). Syntax was verified where
possible (`node --check` on the plain JS config files), and the component logic was reviewed
line by line, but you should run `npm install && npm run dev` locally and fix anything that
surfaces before treating this as final — see HANDOFF.md for the honest status.

## Pages

- `/` — Reconciliation Dashboard: summary cards, filterable results table, detail panel
- `/review` — Human Review Queue: approve/reject items the policy gate didn't auto-resolve
- `/audit` — Audit Trail: chronological log of every match attempt, AI proposal, human decision
- `/ask` — Ask AutoRecon: natural-language query grounded in the audit trail
