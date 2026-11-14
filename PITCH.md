# AutoRecon — Pitch Video Script (5 min)

**0:00–0:30 — Problem**
Finance teams reconcile transactions, settlements, and bank statements by hand.
Discrepancies — fee errors, duplicate credits, missing settlements — go unnoticed
for weeks. Show the "Sheet1 → Sheet17 → Final_Final_2_NEW" joke as a visual gag.

**0:30–2:00 — Architecture**
Walk through the diagram in README.md: deterministic matching engine decides;
Claude only explains and proposes; policy gate is the only thing that can act.
Emphasize: *the LLM never has final authority over money.*

**2:00–4:00 — Live demo**
1. `Seed data & reconcile` on the dashboard → show match rate, unmatched value.
2. Click an unmatched row → show deterministic notes.
3. `Run AI analysis` → item gets an AI-proposed explanation + confidence.
4. Go to Review Queue → approve one item as a named reviewer.
5. Go to Audit Trail → show the full chain: match attempt → AI proposal → human decision.
6. Go to Ask AutoRecon → ask "why didn't order_XXXXX reconcile?" → grounded answer.
7. Show the cash-flow forecast (`GET /forecast`) with the confidence band.

**4:00–5:00 — What broke, what's next**
- Duplicate detection false-positived on same-amount transactions → fixed with
  a compound key (amount + date + UTR).
- Synthetic data generator correlated two scenarios that should've been
  independent → fixed by sampling them separately.
- Amount-based settlement matching was tempting but rejected — silent wrong
  matches on money data are worse than a correctly flagged non-match.
- Next: multi-transaction settlements, Alembic migrations, real merchant
  data integration.

**Close:** "AutoRecon reconciles automatically, explains every mismatch in plain
English, and never lets an AI touch the ledger without a human sign-off."
