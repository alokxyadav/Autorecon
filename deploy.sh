#!/usr/bin/env bash
# AutoRecon — orchestrated local startup, in the correct order.
#
# Order matters here and this script enforces it: tests first (fail fast
# before anything else runs), then the backend starts, then we POLL its
# real readiness endpoint (not a blind `sleep 5` — a slow machine or a cold
# Postgres connection can easily take longer than a guessed delay, which is
# exactly the kind of flaky "works on my machine" bug this avoids), and
# only once the backend is confirmed ready do we seed data and reconcile.

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
MAX_WAIT_SECONDS=60
POLL_INTERVAL_SECONDS=2

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
fail() { echo -e "${RED}[deploy]${NC} $1"; exit 1; }

# ---------------------------------------------------------------------------
# Step 1: run the test suite first. If the code is broken, nothing past
# this point should run — no point starting a server on top of failing logic.
# ---------------------------------------------------------------------------
log "Step 1/5 — running backend test suite..."
if command -v pytest >/dev/null 2>&1; then
    pytest tests/ -v || fail "Tests failed — fix them before deploying. Aborting."
else
    warn "pytest not found, falling back to per-file test runners..."
    for f in tests/test_*.py; do
        python3 "$f" || fail "Test failure in $f — fix it before deploying. Aborting."
    done
fi
log "All tests passed."

# ---------------------------------------------------------------------------
# Step 2: start the backend in the background, capture its PID so we can
# report it (and so a caller could kill it later if scripting this further).
# ---------------------------------------------------------------------------
log "Step 2/5 — starting backend (uvicorn)..."
uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/autorecon-backend.log 2>&1 &
BACKEND_PID=$!
log "Backend starting with PID $BACKEND_PID (logs: /tmp/autorecon-backend.log)"

# ---------------------------------------------------------------------------
# Step 3: poll /health/ready — the REAL readiness probe that actually checks
# database connectivity (see app/main.py) — rather than guessing how long
# startup takes. This is the core of "smooth deployment order": nothing
# downstream runs until this step confirms the backend can actually serve
# a database-backed request, not just that the process is running.
# ---------------------------------------------------------------------------
log "Step 3/5 — waiting for backend readiness at ${BACKEND_URL}/health/ready ..."
elapsed=0
ready=false
while [ "$elapsed" -lt "$MAX_WAIT_SECONDS" ]; do
    if curl -sf "${BACKEND_URL}/health/ready" > /dev/null 2>&1; then
        ready=true
        break
    fi
    sleep "$POLL_INTERVAL_SECONDS"
    elapsed=$((elapsed + POLL_INTERVAL_SECONDS))
    echo -n "."
done
echo ""

if [ "$ready" != true ]; then
    kill "$BACKEND_PID" 2>/dev/null || true
    fail "Backend did not become ready within ${MAX_WAIT_SECONDS}s. Check /tmp/autorecon-backend.log for errors."
fi
log "Backend is ready."

# ---------------------------------------------------------------------------
# Step 4: seed demo data and run reconciliation — only now that we KNOW the
# backend and database are both actually working, not just "probably started."
# ---------------------------------------------------------------------------
log "Step 4/5 — seeding demo data and running reconciliation..."
curl -sf -X POST "${BACKEND_URL}/demo/seed" > /dev/null || fail "Seeding demo data failed."
curl -sf -X POST "${BACKEND_URL}/reconcile/run" > /dev/null || fail "Reconciliation run failed."
log "Demo data seeded and reconciled."

if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    log "ANTHROPIC_API_KEY detected — running AI analysis..."
    curl -sf -X POST "${BACKEND_URL}/reconciliation/analyze" > /dev/null \
        && log "AI analysis complete." \
        || warn "AI analysis call failed — check ANTHROPIC_API_KEY and /tmp/autorecon-backend.log. Continuing anyway."
else
    warn "ANTHROPIC_API_KEY not set — skipping AI analysis step. The rest of the app still works."
fi

# ---------------------------------------------------------------------------
# Step 5: summary — tell the person exactly what's running and what to do next.
# ---------------------------------------------------------------------------
log "Step 5/5 — backend is up and populated."
echo ""
echo "  Backend:      ${BACKEND_URL}"
echo "  API docs:     ${BACKEND_URL}/docs"
echo "  Backend PID:  ${BACKEND_PID} (stop with: kill ${BACKEND_PID})"
echo ""
echo "  Next: in another terminal, run the frontend:"
echo "    cd frontend && npm install && npm run dev"
echo ""
log "Done."
