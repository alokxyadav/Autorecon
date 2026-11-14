# Phase 6 — Post-Buildathon Roadmap

Everything through Phase 5 is buildathon-scoped and demo-ready. This phase is
what a real production rollout would need next — written as an honest
technical plan, not aspirational bullet points, so it's usable if this
project continues past the submission deadline.

## 6.1 Multi-transaction settlements

**Problem:** Phase 1's model assumes one settlement maps to exactly one
transaction (`transaction_order_id` on `SettlementRecord`). Real Razorpay
settlements batch many transactions into one payout.

**Plan:** Introduce a `settlement_transaction_links` join table
(`settlement_id`, `transaction_id`, `allocated_amount`). Razorpay's actual
settlement report format includes a line-item breakdown per transaction
within a settlement batch — ingest that directly rather than inferring
allocation. `match_transaction_to_settlement()` in the matching engine
becomes `match_transaction_to_settlement_batch()`, summing allocated amounts
across all transactions in a batch before comparing to the net payout.

## 6.2 Real Razorpay API integration (beyond Test Mode)

**Plan:**
- Settlement data: Razorpay Settlements API (`/v1/settlements`) instead of
  synthetic data — the existing `SettlementRecord` schema maps directly.
- Bank statement: most banks expose statement data via account aggregator
  APIs (India's AA framework) or manual CSV upload for banks without API
  access — build both ingestion paths, since real deployments will need
  the manual fallback regardless.
- Webhooks: subscribe to Razorpay's `settlement.processed` webhook to
  trigger reconciliation incrementally rather than only on manual
  `/reconcile/run` calls.

## 6.3 Incremental reconciliation (not full-replay)

**Problem:** Phase 1's `/reconcile/run` deletes and rebuilds all
`reconciliation_results` on every call — fine for a demo, wrong for
production once there's history worth preserving (e.g. audit continuity,
already-reviewed items shouldn't be reset).

**Plan:** Track a `last_reconciled_at` watermark. Each run only processes
transactions/settlements/bank lines created or modified since the watermark,
and only touches `reconciliation_results` rows tied to that new data —
existing APPROVED/REJECTED/AUTO_RESOLVED rows are left untouched unless
explicitly re-triggered.

## 6.4 Multi-currency support

**Plan:** Add a `base_currency` concept per merchant account. Store
transaction/settlement amounts in their original currency plus a converted
`base_currency_amount` using the FX rate at transaction time (needs an FX
rate table or a live rate API call, cached). The matching engine's tolerance
comparisons all need to happen in `base_currency_amount`, since fee
structures and tolerances don't translate cleanly across currencies.

## 6.5 Full ERP / accounting integration

**Plan:** Rather than building bespoke connectors per ERP, target a common
intermediate format first — most accounting systems (Tally, Zoho Books,
QuickBooks) support CSV/JSON import for journal entries. Export
`reconciliation_results` as a standard journal-entry format
(debit/credit/account-code) and let the finance team import that, before
investing in direct API integrations with any single ERP vendor.

## 6.6 Multi-tenancy

**Problem:** Current schema has no `merchant_id`/`account_id` — it assumes
a single business's data.

**Plan:** Add `merchant_id` as a foreign key on every table, scope every
query in every service by the authenticated merchant's ID, and add a
proper auth layer (JWT-based, likely via Razorpay's own OAuth if this were
to become an actual Razorpay-integrated product) in front of the API.

## 6.7 Real fraud-adjacent signals (explicitly NOT Track 2's fraud detection)

**Scope boundary:** this stays a reconciliation tool, not a fraud detector.
The only fraud-adjacent signal worth adding here is flagging reconciliation
patterns that *look* like fraud for a human to investigate — e.g. an
unusually high rate of "genuinely missing settlement" discrepancies from
one specific payment method, or a spike in duplicate bank lines. This is a
downstream consumer of `audit_log` data, not a new detection model.

## 6.8 Alerting

**Plan:** A background job (Celery or a simple cron + FastAPI background
task) that checks the forecast module's `anomalies` list and the review
queue's age (items sitting in `pending_human_review` for >48h) and sends a
Slack/email digest. This is a small addition on top of what already exists
in `forecast_service.py` and `ai_analysis_service.py` — no new architecture
needed, just a scheduled reader of data that's already being produced.

---

## What NOT to build, and why

- **A vector database / embeddings for the query service** — at the data
  volume this system handles (a merchant's own reconciliation history),
  the regex + recency-based retrieval in `query_service.py` is transparent,
  debuggable, and sufficient. Adding a vector DB here would be complexity
  without a corresponding accuracy gain, until data volume is orders of
  magnitude larger.
- **Letting the LLM auto-approve at any confidence level without an amount
  ceiling** — even at 99% confidence, the amount ceiling in `policy_gate.py`
  stays. An LLM being consistently right is not the same as it being safe to
  remove the ceiling; the ceiling protects against the one time it's
  confidently wrong on a large amount.
- **A generic "connect any bank" integration** before the account
  aggregator vs. manual-CSV question above is resolved — building broad
  before that scope is settled means rebuilding it anyway.
