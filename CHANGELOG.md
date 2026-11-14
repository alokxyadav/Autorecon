# Changelog

All notable changes to AutoRecon are documented here. For the full,
unabridged development log (including bugs found and exact test counts at
each stage), see `HANDOFF.md`.

## [Unreleased]

### Added
- **"The problem we're solving" section** in `README.md` — a concrete
  before/after comparison table (manual spreadsheet reconciliation vs.
  AutoRecon), replacing a single-paragraph summary with something a judge
  can actually evaluate against
- Dashboard problem banner now links to the Audit Trail and README for
  readers who want the fuller picture, without cluttering the in-app UI
- `LICENSE` (MIT), `CHANGELOG.md`, `PRODUCTION_READINESS.md`
- **CSV export** for reconciliation results and the full audit trail
  (`GET /reconciliation/results/export`, `GET /audit-log/export`) — a real
  requirement for finance teams who need to hand data to auditors or import
  it into existing spreadsheets, not just view it in a dashboard
- `X-Total-Count` response header on both list endpoints, enabling proper
  pagination UI (page N of M) without changing the existing response shape
- **Custom 404 and error pages** (`frontend/app/not-found.tsx`,
  `frontend/app/error.tsx`) — previously absent, meaning any broken link or
  runtime error fell through to Next.js's default unstyled error screen
- Backend-side unified HTTP exception handler: every raised `HTTPException`
  (404s, 401s, 429s, and genuinely unmatched routes) is now logged through
  the same structured logging pipeline as everything else, tagged with a
  request ID, instead of disappearing silently
- `SETUP_GUIDE.md` — complete zero-to-running setup guide including OS-level
  prerequisite installation (Python/Node/Docker on macOS/Windows/Linux),
  distinct from `RUN_AND_DEPLOY.md` which assumes tools are already installed
- **Footer component** with a live backend status indicator (polls
  `/health` every 30s, fails fast rather than using the retrying API
  client), version tag, and an API docs link — present on every page
- **Logo mark** (`AR` monogram badge) — shared `BrandLockup` component used
  consistently across the mobile top bar, mobile drawer, desktop sidebar,
  and the 404 page, replacing plain text-only branding

## [0.5.0] — Deployment Orchestration

### Added
- `deploy.sh` — one-command orchestrated startup with real health-check polling
- `Makefile` — `make test`, `make dev`, `make deploy`, `make docker-up`, etc.
- Docker Compose healthcheck on the backend service; frontend now waits for
  backend *readiness*, not just container start

### Changed
- Frontend API client retries transient failures (502/503/504, network
  errors) with backoff; never retries 4xx client errors

## [0.4.0] — Mobile Responsiveness & Security Hardening

### Added
- Mobile-responsive navigation (hamburger drawer) and responsive layouts
  across all four pages
- Explicit viewport configuration for correct mobile rendering
- Bound on `/demo/seed` dataset size (1–5,000) to prevent resource exhaustion
- Problem-statement banner and improved empty-state copy on the dashboard

## [0.3.0] — Production Hardening

### Added
- Structured JSON logging with request correlation IDs
- Global exception handlers (no raw stack traces ever reach the client)
- Real readiness probe (`GET /health/ready`) checking database connectivity
- Postgres connection pooling (`pool_pre_ping`, `pool_recycle`)
- Exponential backoff on AI reasoning API retries
- Explicit Decimal-as-string serialization for all monetary API fields
- Configurable CORS origins, request field validation constraints

### Fixed
- **Critical:** naive/timezone-aware datetime mismatch that would have
  crashed reconciliation the moment the app ran against real Postgres
- Malformed environment variables no longer crash the policy gate
- Rate limiter memory leak and race condition under concurrent load
- Orphan settlements (no matching transaction) were silently dropped instead
  of being flagged as discrepancies
- Boolean values could bypass AI-response confidence validation due to a
  Python type-system quirk (`bool` is a subclass of `int`)

## [0.2.0] — Security & Infrastructure

### Added
- API key authentication and in-memory rate limiting
- Docker Compose stack (backend, Postgres, frontend)
- Alembic database migrations
- GitHub Actions CI running the full test suite on every push

## [0.1.0] — Initial Release

### Added
- Deterministic three-tier reconciliation engine (exact / fuzzy / unmatched
  matching across transactions, settlements, and bank statements)
- Claude-powered reasoning layer with a deterministic policy gate — the AI
  proposes explanations, it never has final authority over money movement
- Human review workflow with a full, append-only audit trail
- Natural-language query interface grounded strictly in the audit log
- Cash-flow forecasting from verified (reconciled) data only
- Next.js + Tailwind dashboard: reconciliation overview, review queue,
  audit trail viewer, natural-language query
- Full test suite (90 tests across matching logic, policy decisions, AI
  reasoning, forecasting, security, and adversarial edge cases)

---

Built for the **Razorpay AI Buildathon 2026** — Track 4: AI Finance Controller.
