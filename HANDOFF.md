# AutoRecon — Build Handoff Log

## Project
AutoRecon: AI-assisted reconciliation + cash-flow agent for Razorpay Buildathon
(Track: AI Finance Controller). LLM proposes explanations; deterministic engine
makes all matching/approval decisions.

## Repo
<paste your GitHub URL here after first push>

## Status: PHASES 1–5 & 7 BUILT (backend fully tested; frontend/Docker/CI written but not run — see per-phase notes); Phase 6 documented as roadmap only

---

## Phase 1 Log

**Built:**
- `app/services/matching_engine.py` — pure, dependency-free three-tier matching
  logic (exact / fuzzy-within-fee-tolerance / unmatched), plus missing-settlement
  classification (pending vs. genuinely overdue) and duplicate bank line detection.
- `app/models/` — SQLAlchemy models for `transactions`, `settlements`,
  `bank_statement_lines`, `reconciliation_results`, `audit_log`. `audit_log` is
  append-only by convention — no update/delete route exists for it anywhere.
- `app/services/data_generator.py` — synthetic dataset generator with
  deliberately injected discrepancies (missing settlements ~8%, fee drift ~12%,
  duplicate bank lines ~3%, timing lags ~8%, independently sampled).
- `app/services/reconciliation_service.py` — the only place DB writes for
  reconciliation happen; converts DB rows to matching-engine dataclasses, runs
  `engine.reconcile()`, persists `reconciliation_results` + one `audit_log`
  entry per result in the same pass.
- `app/routers/reconciliation.py` — `POST /reconcile/run`, `POST /demo/seed`,
  `GET /reconciliation/results` (filterable by `status`/`match_type`),
  `GET /reconciliation/results/{id}`.
- `app/routers/audit.py` — `GET /audit-log` (read-only, filterable by `event_type`).
- `app/main.py` — FastAPI app, permissive CORS for dev, `/health` endpoint,
  creates tables on startup via `init_db()`.
- `tests/test_matching_engine.py` — 15 tests, **all passing**, covering every
  tier plus edge cases (wrong-order-id-same-amount rejection, duplicate
  detection false-positive avoidance, end-to-end mixed scenario).

**How to run locally:**
```bash
pip install -r requirements.txt
pytest tests/ -v                          # 15 passed, 0 failed, verified
uvicorn app.main:app --reload
curl -X POST http://localhost:8000/demo/seed
curl -X POST http://localhost:8000/reconcile/run
```

**Verified correctness (not just "should work"):**
The matching engine has zero external dependencies, so I ran the full test
suite directly in this environment (not just syntax-checked) — all 15 tests
pass against real assertions, including a full end-to-end mixed scenario with
clean matches, fee drift, missing settlements, pending-not-yet-due
transactions, and duplicate bank lines. The FastAPI/SQLAlchemy layer around it
was syntax-verified (`py_compile`, zero errors) but **could not be
integration-tested in this sandbox** — no network access was available to
`pip install` fastapi/sqlalchemy here. Run `pytest` and `uvicorn` locally
before building Phase 2 on top of this, and fix anything that surfaces —
the matching engine logic itself is solid, but I want to be honest that the
DB/API wiring hasn't been executed end-to-end yet, only reasoned through
carefully line by line.

**Important interfaces Phase 2 needs to know about:**
- `engine.find_items_needing_review(run: ReconciliationRun) -> list[MatchResult]`
  — call this to get exactly the items that need an LLM explanation. It
  returns everything with status `UNMATCHED` or `PARTIAL`, including
  duplicate bank lines (which have `transaction_id=None` — handle that case).
- `ReconciliationResultRecord` already has nullable columns ready for you:
  `ai_proposed_resolution` (Text), `ai_confidence` (Integer), `reviewer_name`
  (String). Don't add new columns for these — they're already there.
- `AuditLogRecord.event_type` convention to follow: use `"ai_proposal"` when
  Claude proposes something, `"human_decision"` when a reviewer approves/
  rejects. (`"match_attempt"` and `"system_error"` are Phase 1/reserved.)
- Tunable constants live at the top of `matching_engine.py`
  (`EXACT_MATCH_TOLERANCE`, `FEE_FUZZY_TOLERANCE`, `BANK_AMOUNT_TOLERANCE`,
  `SETTLEMENT_GRACE_PERIOD_DAYS`) — reference these rather than hardcoding
  new copies of the same numbers in the policy gate.
- `.env.example` already has placeholders for `ANTHROPIC_API_KEY`,
  `AUTO_APPROVE_CONFIDENCE_THRESHOLD`, `AUTO_APPROVE_MAX_AMOUNT` — wire your
  policy gate to read from these rather than hardcoding thresholds.

**Known simplifications (intentional, not oversights):**
- One settlement maps to exactly one transaction (`transaction_order_id` on
  `SettlementRecord`). Real Razorpay settlements can batch multiple
  transactions — out of scope for this buildathon window, mention it in the
  final README's "out of scope" section if not already there.
- Each `/reconcile/run` call replaces the entire `reconciliation_results`
  table rather than doing an incremental diff. Fine for a demo; a real
  production version would need incremental reconciliation.

## Phase 2 should start by:
1. Cloning the repo and running `pytest tests/ -v` locally to confirm Phase 1
   actually passes in a real environment (it was only verified for the pure
   matching-engine tests in the sandbox that built it — see note above).
2. Running `uvicorn app.main:app --reload`, then `POST /demo/seed` and
   `POST /reconcile/run`, and checking `GET /reconciliation/results?status=unmatched`
   to see real discrepancies to build the reasoning layer against.
3. Building the Claude reasoning layer + policy gate as specified in the
   Phase 2 prompt (see `autorecon-master-prompts.md`), calling
   `engine.find_items_needing_review()` to get the exact item list.

---

## Phase 2 Log — DONE

**Built:**
- `app/services/policy_gate.py` — pure, dependency-free decision function.
  `evaluate_policy()` is the ONLY thing that may return `AUTO_RESOLVED`.
  7 tests, all passing (boundary conditions, invalid-proposal override,
  negative-delta magnitude handling).
- `app/services/ai_reasoning_service.py` — Claude reasoning layer designed
  around an injected `complete_fn` so it's testable with zero network and
  zero `anthropic` package installed. 11 tests passing, including retry
  logic, malformed-JSON fallback, and API-exception fallback — the function
  is guaranteed to never raise, always degrading to "needs manual review."
  `make_claude_complete_fn()` is the only place that imports `anthropic`,
  and it does so lazily.
- `app/services/ai_analysis_service.py` — bridges DB rows to the reasoning
  layer + policy gate, writes `ai_proposal` and policy-decision audit log
  entries, updates `reconciliation_results` status accordingly.
- `app/services/query_utils.py` + `query_service.py` — natural-language
  query, split so the regex extraction (`extract_order_id`) is dependency-free
  and testable (4 tests passing) while the DB-touching retrieval logic lives
  separately. Answers are strictly grounded in retrieved audit_log entries —
  explicitly says "couldn't find" rather than guessing when nothing matches.
- New router endpoints: `POST /reconciliation/analyze`,
  `POST /reconciliation/{id}/approve`, `POST /reconciliation/{id}/reject`,
  `POST /query`.

**Verified:** 19 new tests (7 + 11 + 4 minus 3 overlap... see exact count
below), all passing for real in the sandbox. Total backend suite: 44/44
passing (`test_matching_engine.py` 15, `test_policy_gate.py` 7,
`test_ai_reasoning_service.py` 11, `test_query_service.py` 4,
`test_forecast_service.py` 7).

**Not yet verified (needs your local run):**
- The actual FastAPI endpoints wiring these services together
  (`/reconciliation/analyze`, `/approve`, `/reject`, `/query`) — syntax
  checked only, same limitation as Phase 1's router layer.
- A real call to the Claude API (`make_claude_complete_fn`) — the retry/
  parsing/fallback logic around it is fully tested, but the actual HTTP
  call to `api.anthropic.com` has not been exercised. Set
  `ANTHROPIC_API_KEY` in `.env` and test `/reconciliation/analyze` against
  real discrepancies before demoing.

**Important for Phase 3:**
- `GET /reconciliation/results` already returns `ai_proposed_resolution`,
  `ai_confidence`, `reviewer_name` — no schema changes needed.
- Policy thresholds are read from env vars `AUTO_APPROVE_CONFIDENCE_THRESHOLD`
  and `AUTO_APPROVE_MAX_AMOUNT` (see `.env.example`).

---

## Phase 3 Log — BUILT, NOT NPM-INSTALLED/BUILT

**Built:** full Next.js 14 App Router + Tailwind frontend in `/frontend`:
- `app/page.tsx` — Dashboard (summary cards, filterable table, detail panel)
- `app/review/page.tsx` — Human Review Queue (approve/reject with reviewer name)
- `app/audit/page.tsx` — Audit Trail (filterable by event type)
- `app/ask/page.tsx` — Ask AutoRecon (natural-language query UI)
- `lib/api.ts` — typed API client hitting the FastAPI backend
- `components/StatusBadge.tsx`, `SummaryCard.tsx`, `Sidebar.tsx`
- Design tokens (Tailwind config) match the palette from
  `autorecon-master-prompts.md` exactly.

**Verified:** `package.json` and `tsconfig.json` are valid JSON (checked with
Python's `json` module). `tailwind.config.js`, `postcss.config.js`, and
`next.config.js` are syntactically valid (checked for real with
`node --check`, which works since they're plain CommonJS with no JSX).

**NOT verified:** the `.tsx` component files themselves were never run
through `next build` or a TypeScript compiler — there was no network access
to `npm install` the actual dependencies (`next`, `react`, `tailwindcss`,
etc.) in the sandbox that built this. They were written carefully and
reviewed by eye, but treat this as "should work" rather than "proven to
work." **Run `npm install && npm run dev` locally first and fix whatever
surfaces** before this goes in front of judges.

## Phase 3 should start by (if picking this up fresh):
1. `cd frontend && npm install && npm run dev` — see what breaks, fix it.
2. Confirm the backend is running (`uvicorn app.main:app --reload` from repo
   root) and `NEXT_PUBLIC_API_URL` in `.env.local` points to it.
3. Add the cash-flow forecast chart to the dashboard (Phase 4 built the
   `/forecast` endpoint but the frontend doesn't render it yet — a small
   addition to `app/page.tsx` using a simple bar/line chart).

---

## Phase 4 Log — Forecast module DONE; polish/deploy NOT done

**Built:**
- `app/services/forecast_service.py` — pure, dependency-free cash-flow
  forecast with historical settlement-lag stats, anomaly detection for
  late settlements, and a confidence band (low/expected/high) rather than
  a false-precision single number. 7 tests, all passing.
- `app/services/forecast_bridge_service.py` — bridges DB rows to the
  forecast module, deliberately restricted to `VERIFIED_STATUSES` only
  (matched/partial/auto_resolved/approved) — never forecasts off raw
  unreconciled transactions.
- `GET /forecast?horizon_days=N` endpoint.
- `PITCH.md` — 5-minute video script/storyboard, including the honest
  "what broke" section for the judges' explicit question.

**NOT done yet (real work remaining for whoever picks this up next):**
- Demo data volume/realism polish beyond what `data_generator.py` already
  does (it's reasonable for a demo, but a dedicated polish pass would help).
- Actual deployment (Vercel for frontend, Railway/Render/Fly.io for backend
  + Postgres) — nothing has been deployed anywhere, this is still fully local.
- Final end-to-end walkthrough by a human, as a judge would experience it —
  this has NOT happened yet because the frontend has never been run.
- Wiring the `/forecast` endpoint into the dashboard UI (noted above).

## Next steps for whoever continues this:
1. Get the backend running locally, confirm all 72 tests pass on your
   machine too (should — they're dependency-light — but confirm).
2. Get the frontend running locally (`npm install && npm run dev`), connect
   it to the backend, and actually click through all four pages end to end.
   This is the single most important remaining step — nothing in Phase 3
   has been visually confirmed to render correctly yet.
3. Set a real `ANTHROPIC_API_KEY` and confirm `/reconciliation/analyze`
   produces sensible explanations against the seeded demo discrepancies.
4. Add the forecast chart to the dashboard.
5. Deploy both halves and update this file with the live URL.
6. Record the pitch video using `PITCH.md` as the script.

---

## Phase 5 Log — Production hardening (written, not executed)

**Built:**
- `Dockerfile` (backend) — runs `alembic upgrade head` then `uvicorn` on boot.
- `frontend/Dockerfile` — multi-stage Next.js build.
- `docker-compose.yml` — backend + Postgres + frontend, one-command local
  stack. Validated as syntactically correct YAML.
- `migrations/` — Alembic setup replacing the dev-only `Base.metadata.create_all()`.
  `migrations/versions/0001_initial.py` is a hand-written migration matching
  the SQLAlchemy models exactly (alembic isn't installed in this sandbox to
  autogenerate it, so it was written by hand and syntax-checked with
  `py_compile` — **run `alembic upgrade head` locally and confirm it
  actually creates the right schema before relying on it**).
- `.github/workflows/ci.yml` — runs `pytest` on every push, plus a
  `next build` check for the frontend. Validated as syntactically correct
  YAML. Not run for real (would require GitHub itself).
- `.dockerignore` — excludes venv/tests/frontend from the backend image.

**NOT verified (no Docker available in this sandbox):**
- Neither Dockerfile has been built or run (`docker` command doesn't exist
  in this environment). Run `docker compose up --build` locally and fix
  whatever surfaces — Dockerfiles are a common place for small path/naming
  mistakes even when the logic is sound.
- The Alembic migration has not been applied against a real database.
  Run `alembic upgrade head` against a fresh Postgres instance and confirm
  the resulting schema matches what `create_all()` would have produced,
  before switching over from the dev convenience path.

## Phase 6: see `PHASE_6_ROADMAP.md`

Post-buildathon scope (multi-transaction settlements, real Razorpay API
integration, incremental reconciliation, multi-currency, ERP export,
multi-tenancy, alerting) — documented as a technical plan, not built, since
none of it is needed for the buildathon submission itself. Written so this
project has a credible answer if judges ask "what would you build next."

---

## Phase 7 Log — Security hardening (API key auth + rate limiting)

**Built:**
- `app/security.py` — `verify_api_key()` (constant-time comparison, disabled
  when no key is configured) and `RateLimiter` (fixed-window, in-memory),
  both pure/dependency-free like `matching_engine.py` and `policy_gate.py`.
  **10 tests, all passing** — including a specific test for a prefix-match
  bug class (`"secret"` must NOT satisfy an expected key of `"secret123"`).
- `app/security_deps.py` — FastAPI-specific wiring (`require_api_key`,
  `enforce_rate_limit`) kept separate so the pure logic in `security.py`
  never imports FastAPI.
- Wired into `main.py`: every router except `/health` now requires
  `X-API-Key` (if `AUTORECON_API_KEY` is set) and is rate-limited to 60
  req/min per client IP.

**Honest limitation documented in the code itself:** the rate limiter is
in-memory and per-process — correct for a single-instance deploy, wrong for
multiple replicas behind a load balancer (each replica would track its own
budget). Noted in `security_deps.py`'s docstring and cross-referenced to
`PHASE_6_ROADMAP.md`, not hidden.

**NOT verified:** the FastAPI dependency wiring itself (same limitation as
every other router in this project — no network access to install FastAPI
in this sandbox). Set `AUTORECON_API_KEY` locally, restart `uvicorn`, and
confirm a request without the header gets a 401 before deploying.

---

## QA Pass Log — bugs found and fixed by dedicated adversarial testing

Ran `tests/test_qa_edge_cases.py` (18 new tests targeting boundary conditions,
adversarial inputs, and cross-module integration scenarios) against the
existing code. Found and fixed 2 real bugs:

1. **Orphan settlement silently dropped.** `reconcile()` only ever looped
   over transactions and looked up each one's settlement — a settlement
   referencing an `order_id` with NO corresponding transaction anywhere
   (e.g. a data sync gap) produced zero results instead of being flagged.
   Fixed: `reconcile()` now also checks for settlements with no matching
   transaction and surfaces them as `UNMATCHED` results, plus a new
   `orphan_settlement_ids` field on `ReconciliationRun` and a corresponding
   `orphan_settlements` count in `ReconciliationSummary`. Regression test:
   `test_orphan_settlement_with_no_matching_transaction_is_flagged_not_dropped`.

2. **Boolean confidence values silently accepted.** Python's `bool` is a
   subclass of `int`, so `isinstance(True, int)` is `True`. The AI response
   parser's `isinstance(confidence, int)` check let a malformed
   `"confidence": true` from the model through as `confidence=1` instead of
   being rejected. Fixed: explicitly excludes `bool` before the `int` check
   in `parse_reasoning_response()`. Regression test:
   `test_reasoning_parser_rejects_boolean_confidence_despite_bool_being_an_int_subclass`.

**Also modernized** (not bugs, but real production-readiness gaps found
during the same pass):
- `db.query(Model).get(id)` → `db.get(Model, id)` in `ai_analysis_service.py`
  and `forecast_bridge_service.py` — the former is deprecated legacy API in
  SQLAlchemy 2.0.
- `@app.on_event("startup")` → a `lifespan` context manager in `main.py` —
  the former is deprecated in current FastAPI/Starlette.
- Fixed a placeholder model name (`claude-sonnet-4-6`, which isn't a real
  model) to `claude-sonnet-5` in `make_claude_complete_fn()`, with a comment
  to verify against current docs before deploying, since model names change.
- Added basic security response headers (`X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`) to every response.
- Wired the `/forecast` endpoint into the dashboard UI (previously built
  but not rendered anywhere) and wired the frontend to send `X-API-Key`
  when `NEXT_PUBLIC_API_KEY` is set, matching Phase 7's backend auth.

**Current verified test count: 72/72 passing** across
`test_matching_engine.py` (15), `test_policy_gate.py` (7),
`test_ai_reasoning_service.py` (11), `test_query_service.py` (4),
`test_forecast_service.py` (7), `test_security.py` (10), and
`test_qa_edge_cases.py` (18).

See `RUN_AND_DEPLOY.md` for the complete, step-by-step guide to running
this locally, via Docker, and deploying it live — including a
troubleshooting section for the most likely failure points.

---

## Production-Hardening Pass — logging, backoff, precision, pooling

Added real production infrastructure beyond the QA bug-fix pass:

1. **Exponential backoff on AI reasoning retries.** Previously, failed
   Claude API calls were retried instantly with no delay — fine for a
   parsing failure, harmful for a transient rate limit (hammering an
   already-struggling API). `get_ai_explanation()` now backs off
   `base_delay_seconds * 2^attempt` between retries (injectable `sleep_fn`
   keeps this testable — 4 new tests verify exact delay sequences without
   any test actually sleeping).
2. **Decimal precision guaranteed in API responses.** `ReconciliationResultOut.delta_amount`
   and `ReconciliationSummary.total_unmatched_value` now have explicit
   `@field_serializer` methods forcing string output — money is never
   emitted as a JSON number, which could silently lose precision on
   whatever client parses it.
3. **Production-grade DB connection pooling.** `database.py` now sets
   `pool_pre_ping=True` (avoids handing out dead connections after a DB
   restart), `pool_recycle` (avoids exceeding managed Postgres providers'
   idle-connection limits), and configurable pool size — only for Postgres;
   SQLite's dev-mode path is untouched.
4. **Structured JSON logging with request correlation IDs**
   (`app/logging_config.py`, pure stdlib, **6 tests passing for real**).
   Every request gets a UUID (returned as `X-Request-ID` header) available
   to every log line emitted anywhere during that request via a contextvar
   — no need to thread a request ID through every function signature.
5. **Global exception handlers.** Unhandled exceptions are now caught,
   logged in full server-side with the request ID, and returned to the
   client as a generic message — never a raw stack trace (an information
   disclosure risk). Validation errors get a cleaner structured 422.
6. **Real readiness probe.** `GET /health` is a pure liveness check (was
   already correct); added `GET /health/ready`, which actually executes
   `SELECT 1` against the database and returns 503 if unreachable —
   orchestrators (Kubernetes, Railway, etc.) should point health checks
   here, not at `/health`, to avoid routing traffic to an instance whose
   DB connection is broken.

**Current verified test count: 81/81 passing.**

**Still not verified (consistent with every prior phase):** the FastAPI
middleware/exception-handler wiring in `main.py` itself has not been
booted — same sandbox limitation as always. Everything in this pass that
*could* be tested without FastAPI installed (backoff timing, logging
output, decimal serialization logic in isolation) was tested for real;
what remains is confirming the actual HTTP behavior once you run
`uvicorn app.main:app --reload` locally — check that `/health/ready`
returns 503 when you stop your database, and that a request without a
valid body to a POST endpoint returns the new structured 422 format.

---

## Deployment-Blocker Bug Fixes — found via dedicated adversarial audit

This pass specifically hunted for bugs that would only appear once this app
left SQLite/local-dev and hit the actual production target (Postgres +
concurrent traffic), since that gap is exactly where "tests pass locally"
and "actually works in production" diverge.

1. **CRITICAL — naive/aware datetime crash.** `DateTime(timezone=True)`
   columns return timezone-AWARE datetimes under Postgres (psycopg2) but
   typically NAIVE ones under SQLite. Every piece of code that mixed
   `datetime.utcnow()` (naive) with a value read from the database — which
   was all of `matching_engine.py`, `forecast_service.py`,
   `forecast_bridge_service.py`, `data_generator.py`, and
   `reconciliation_service.py` — would have crashed with
   `TypeError: can't subtract offset-naive and offset-aware datetimes` the
   very first time `/reconcile/run` or `/forecast` was called against the
   real Postgres deployment this project's own `docker-compose.yml`
   targets. **Confirmed the crash first** (reproduced it directly in the
   Python REPL) before fixing it. Fix: new `app/services/time_utils.py`
   (pure stdlib, 5 tests passing) with a `to_utc()` normalizer, applied
   everywhere datetime arithmetic happens. Regression test
   `test_reconcile_survives_mixed_naive_and_timezone_aware_datetimes`
   specifically simulates a naive SQLite-style value being reconciled
   against an aware "now", which would have raised before this fix.

2. **Malformed env var crash.** `policy_gate._env_decimal()` had no
   exception handling — unlike its sibling `_env_int()`, which already
   caught `ValueError` — so a typo in `AUTO_APPROVE_MAX_AMOUNT` (e.g.
   accidentally leaving in a currency symbol) would raise
   `decimal.InvalidOperation` on every single `/reconcile/analyze` call.
   Fixed with the same fallback-to-default pattern as `_env_int`.
   Regression test: `test_load_thresholds_falls_back_safely_on_malformed_env_vars`.

3. **Rate limiter memory leak + thread-safety.** The in-memory
   `RateLimiter._windows` dict grew unbounded over the process's lifetime —
   every distinct client key (IP) it ever saw stayed in memory forever,
   even long after that client stopped making requests. Also had no lock,
   so concurrent requests could race on the same dict. Fixed: added a
   `threading.Lock` around all state mutation, and periodic eviction of
   expired windows (`_cleanup()`, triggered every 100 calls). **Tested with
   100 real concurrent threads** hammering the same key
   (`test_thread_safety_under_concurrent_access_from_same_key`) — exactly
   100 allowed, no race-condition over/under-counting — plus a dedicated
   test proving the dict doesn't grow unbounded across many distinct
   short-lived clients.

4. **Anthropic SDK retry conflict.** `make_claude_complete_fn()` previously
   constructed `anthropic.Anthropic()` with default settings, which
   includes the SDK's own built-in retry logic (2 retries with backoff).
   Combined with `get_ai_explanation()`'s own retry/backoff loop, a single
   failure could silently turn into several minutes of nested retrying
   before this codebase's own fallback ever kicked in. Fixed: explicit
   `timeout=30.0, max_retries=0` on the client, making
   `get_ai_explanation()` the single source of truth for retry behavior.

5. **CORS hardcoded to wildcard.** Made configurable via
   `CORS_ALLOWED_ORIGINS` (comma-separated), defaulting to `*` for
   zero-config local dev, so a real deployment can restrict it to the
   actual deployed frontend URL(s) without a code change.

6. **Missing request validation.** `ReviewDecisionRequest.reviewer_name`
   and `QueryRequest.question` had no length constraints at all — an empty
   or whitespace-only reviewer name could be recorded in the audit trail,
   and an unbounded question length had no defense against runaway Claude
   API token usage. Added `Field` constraints plus a validator that
   specifically catches whitespace-only names (which a naive
   `min_length=1` check alone would miss).

**Current verified test count: 90/90 passing.** Full breakdown:
`test_matching_engine.py` (15), `test_policy_gate.py` (8),
`test_ai_reasoning_service.py` (14), `test_query_service.py` (4),
`test_forecast_service.py` (7), `test_security.py` (12),
`test_qa_edge_cases.py` (19), `test_logging_config.py` (6),
`test_time_utils.py` (5).

**What this pass could NOT verify** (unchanged limitation, stated plainly
rather than glossed over): the actual FastAPI request/response cycle,
including the new CORS config and Field validators, has still never been
exercised against a running server — no network access to install FastAPI
in this sandbox. The datetime fix specifically was verified via a REPL
reproduction of the exact crash plus a dedicated regression test using the
pure `matching_engine.reconcile()` function directly (which doesn't need
FastAPI installed) — so the underlying logic bug is definitively fixed,
even though the end-to-end HTTP path around it remains unexercised.

---

## Mobile Responsiveness + Real-World Framing + Final Security Pass

1. **Fixed a real mobile-breaking layout bug.** The sidebar was a static
   224px-wide flex sibling with no responsive behavior at all — on a phone
   this would either crush the main content into a sliver or overflow the
   viewport horizontally. Replaced with a proper pattern: a `md:hidden`
   mobile top bar + hamburger button opening a slide-in drawer (with
   backdrop, close button, and click-outside-to-close), and the original
   static sidebar preserved unchanged at the `md:` breakpoint and above.
   Added an explicit `viewport` export in `layout.tsx` — without it, some
   mobile browsers render at a fixed desktop width and let the user pinch
   to zoom instead of actually reflowing.
2. **Every page audited for narrow-screen behavior:** headers that used to
   force `justify-between` on one line now wrap (`flex-col sm:flex-row`);
   the 4-column summary card grid collapses to 2 columns below `lg`; both
   data tables (results, forecast) are wrapped in `overflow-x-auto` so they
   scroll horizontally instead of squashing columns unreadably; the
   dashboard's results-table-plus-detail-panel split stacks vertically
   below `lg` instead of forcing a cramped 3-column grid.
2. **Verification method for the TSX changes:** since FastAPI/Node still
   can't be installed in this sandbox, every edited file was checked for
   brace/paren balance (all matched) and JSX tag open/close balance via
   regex. One file (`Sidebar.tsx`) initially flagged a false mismatch —
   traced by hand to a known limitation of regex-based tag matching (an
   arrow function's `=>` inside an event handler broke the character-class
   pattern, not an actual bug in the file) and confirmed correct by
   reading the file end-to-end. Documented here rather than silently
   "fixing" something that wasn't broken.
3. **Clearer real-world problem framing**, since a judge or first-time
   viewer should understand the "why" in the first five seconds: added a
   one-paragraph problem statement banner at the top of the dashboard, and
   rewrote the empty-state copy (shown before the first demo-seed) to
   explicitly name what a finance team normally does manually, rather than
   a generic "no results yet."
4. **One more real security gap closed:** `POST /demo/seed`'s
   `num_transactions` parameter was completely unbounded — any caller
   (unauthenticated if `AUTORECON_API_KEY` isn't set) could request an
   arbitrarily large synthetic dataset, a real resource-exhaustion vector
   on an endpoint that otherwise had no guard at all. Bounded to 1–5000 via
   FastAPI's `Query(ge=1, le=5000)`.
5. **Client-side validation now matches server-side constraints**: the
   "Ask AutoRecon" question input and reviewer-name input both have
   `maxLength` attributes matching the backend's `Field` constraints added
   in the previous pass, so a user hits an inline browser limit rather than
   typing a long message only to have it rejected after submission.

**Backend test count unchanged at 90/90** (this pass's backend change —
the `num_transactions` bound — didn't need a new test file since it's a
FastAPI `Query` constraint, which falls into the same "can't run FastAPI
here" category as the rest of the router layer; verify it manually with
`curl -X POST "http://localhost:8000/demo/seed?num_transactions=999999999"`
and confirm you get a 422, not a hung server).

---

## Deployment Ordering + Startup Resilience

Targeted specifically: the gap between "each piece works" and "the pieces
come up in the right order without racing each other."

1. **Docker Compose healthcheck gap fixed.** `frontend` previously only
   depended on `backend` having *started* (`depends_on: - backend`), not on
   it being *ready* — the classic race where the frontend loads before the
   backend can actually serve a database-backed request. Added a real
   healthcheck to the `backend` service hitting `/health/ready` specifically
   (not `/health`, which only checks the process is alive) via Python's
   stdlib `urllib` (no curl/wget needed in the slim base image), and changed
   `frontend`'s dependency to `condition: service_healthy`.
2. **`deploy.sh`** — one script enforcing the correct order for the non-
   Docker path: run tests first (fail fast before starting anything), start
   the backend, **poll** `/health/ready` in a loop (not a blind `sleep N`,
   which is exactly the kind of guess that works on a fast machine and
   flakes on a slow one or a cold Postgres connection), then seed and
   reconcile only once readiness is confirmed. Validated with `bash -n`
   (real syntax check, not just eyeballing it).
3. **`Makefile`** — `make help`, `make test`, `make dev`, `make deploy`,
   `make docker-up`, `make seed`, `make reconcile`, `make clean`. Verified
   for real with `make -n test` and `make -n docker-up` (confirmed the
   tab-indented recipe lines are actual tabs, not spaces — the single most
   common reason a Makefile silently fails).
4. **Frontend retry logic for the exact "backend still warming up" window.**
   `lib/api.ts`'s `request()` now retries up to 3 times with backoff — but
   ONLY on network-level failures or 502/503/504 responses (the specific
   signature of a backend that isn't ready yet), never on 4xx errors, since
   retrying a request that failed due to bad input or invalid auth would
   just fail identically three times instead of surfacing the real problem
   immediately.

**Backend test count unchanged at 90/90** — this pass's changes are
infrastructure/orchestration (Docker Compose YAML, a bash script, a
Makefile, and frontend retry logic), none of which are Python unit-testable
in this sandbox, but each was verified with the appropriate real tool
(`yaml.safe_load`, `bash -n`, `make -n`) rather than left unchecked.

---

## CSV Export — a genuine missing feature, not just more hardening

After six rounds of hardening existing code, this pass added something the
application actually lacked: a way to get data *out* of it. A reconciliation
tool that only shows results in a dashboard isn't something a real finance
team can use day-to-day — they need to hand numbers to auditors, paste them
into an existing spreadsheet, or attach a CSV to a month-end close email.

**Built:**
- `app/services/export_service.py` — pure stdlib (`csv` + `io`), no
  FastAPI/SQLAlchemy dependency, so the row-formatting logic itself is
  fully testable in isolation. **9 tests, all passing**, specifically
  targeting the exact edge cases that break naive CSV implementations:
  embedded commas, embedded quotes, embedded newlines (verified the parsed
  row count stays 1, not 2, when reasoning text spans multiple lines), and
  missing/`None` fields exporting as empty strings rather than the literal
  text `"None"`.
- `GET /reconciliation/results/export` and `GET /audit-log/export` —
  respect the same status/event_type filters as their list-endpoint
  counterparts, but with no page limit (export means everything matching
  the filter, not one page of it).
- **Route ordering verified explicitly**: `/reconciliation/results/export`
  is registered before `/reconciliation/results/{result_id}` — confirmed
  via `grep` on the decorator order — since FastAPI/Starlette matches
  routes in registration order and a static path must come before a
  parameterized one it could otherwise collide with (a request for
  `/export` would otherwise be captured as `result_id="export"` and fail
  int parsing with an unhelpful 422).
- `X-Total-Count` response header added to both list endpoints, closing a
  previously-noted gap: the frontend had no way to render "page 1 of N" or
  know if more results existed beyond the current page, without changing
  the existing response body shape for any current caller.
- **Frontend export wired correctly, not just added as a link.** A plain
  `<a href>` pointing at the export URL would silently skip the
  `X-API-Key` header and 401 whenever `AUTORECON_API_KEY` is set — caught
  this before shipping it, not after. Implemented instead as a `fetch` +
  `Blob` + synthetic download link, going through the same authenticated
  request path as every other API call.

**Current verified test count: 99/99 passing.**

**Not yet verified** (consistent with everything else): the actual HTTP
behavior of the two export endpoints and the frontend download flow — same
sandbox limitation as always. Verify locally with:
```bash
curl -X POST http://localhost:8000/demo/seed
curl -X POST http://localhost:8000/reconcile/run
curl -o results.csv "http://localhost:8000/reconciliation/results/export"
curl -o audit.csv "http://localhost:8000/audit-log/export"
```
and confirm both files open correctly in a spreadsheet application.

---

## Custom Error Pages + Setup Guide

**Confirmed via direct filesystem check** (`ls frontend/app/ | grep not-found`)
that custom 404/error pages were genuinely absent before this pass — any
broken link or unexpected runtime error would have fallen through to
Next.js's default unstyled screens, a rough edge in an otherwise polished
UI. Fixed:

1. **`frontend/app/not-found.tsx`** — Next.js App Router's convention for a
   custom 404, styled consistently with the rest of the app, with links to
   all four working pages so a user isn't stuck.
2. **`frontend/app/error.tsx`** — the App Router's runtime error boundary
   convention (must be a client component per Next.js's own requirement,
   receiving `error`/`reset` props). Logs to console (noted as a stand-in
   for a real error-tracking service like Sentry in production), shows a
   "Try again" button wired to `reset()`, and a link back to the dashboard.
3. **Backend-side consistency**: added a unified `StarletteHTTPException`
   handler in `main.py` so every raised HTTP exception — genuinely
   unmatched routes (404), auth failures (401), rate limiting (429), and
   explicit "not found" responses from individual endpoints — gets logged
   through the same structured pipeline as the existing 500/422 handlers,
   tagged with a request ID. Previously these disappeared silently with no
   server-side record. Preserves the original status code and detail
   message exactly — this is additive logging/consistency, not a behavior
   change to any existing endpoint's response.
4. **`SETUP_GUIDE.md`** — a genuinely complete guide starting from "nothing
   is installed," covering OS-specific instructions for installing Python,
   Node, Git, and Docker on macOS/Windows/Linux, getting an Anthropic API
   key, and a concrete verification checklist (including explicitly
   checking the new 404 page renders) — distinct from `RUN_AND_DEPLOY.md`,
   which assumes those tools already exist and focuses on running/deploying.

**Verified:** removed an unused import introduced while adding the new
exception handler (`FastAPIHTTPException`, superseded by
`StarletteHTTPException` during editing) — caught via the same AST-based
unused-import check used in earlier passes, applied again before shipping
rather than left in. Full backend regression re-run after this change:
**99/99 tests still passing**, confirming the new exception handler didn't
alter any existing behavior the test suite depends on.

**Not yet verified** (unchanged limitation): whether `not-found.tsx` and
`error.tsx` actually render correctly, and whether the new backend
exception handler behaves as designed against a live request — both need
`npm run dev` / `uvicorn` running locally, which remains outside what this
sandbox can execute.

---

## Footer + Navbar Branding Pass

**Confirmed via grep** that no footer component existed anywhere in the
frontend before this pass. Added:

1. **`frontend/components/Footer.tsx`** — appears on every page (wired into
   `layout.tsx`'s flex column so it sits below content, pushed to the
   bottom of the viewport on short pages via flexbox rather than fixed
   positioning). Shows copyright + buildathon attribution, version tag, a
   **live backend status indicator**, and a link to the API docs.
   - The status indicator deliberately uses a plain `fetch()` to `/health`
     rather than the shared `api.ts` `request()` helper — that helper
     retries 3x with backoff, which is correct for actual data operations
     but wrong for a background status check that should fail fast and
     re-poll on its own schedule (every 30s) rather than hang for several
     seconds on each check.
2. **Shared `BrandLockup` component** in `Sidebar.tsx` — a small `AR`
   monogram badge (using the existing `accent-500` design token) paired
   with the "AutoRecon" wordmark, replacing plain text-only branding.
   Used consistently in all three places brand text previously appeared
   (mobile top bar, mobile drawer, desktop sidebar) plus the 404 page, so
   a visual identity element is reused rather than redefined three times
   with slightly different markup each time.

**Verified:** brace/paren balance checked individually on every touched
file (`Sidebar.tsx`, `Footer.tsx`, `layout.tsx`, `not-found.tsx`) — all
balanced. Full backend regression re-run to confirm this frontend-only
change didn't somehow affect backend test results (it didn't and
shouldn't have, but re-running costs nothing and confirms it): **99/99
still passing.**

**Not yet verified:** whether the footer's live status indicator actually
flips between "online"/"offline" correctly against a real running/stopped
backend, and whether the flexbox layout genuinely keeps the footer at the
bottom of short pages while scrolling correctly on long ones — both need
`npm run dev` to see for real.
