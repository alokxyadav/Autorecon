"""
FastAPI-specific wiring for app/security.py. Split out so security.py itself
stays free of FastAPI imports and testable in complete isolation (see
tests/test_security.py, which imports zero FastAPI/network dependencies).
"""

from fastapi import Header, HTTPException, Request

from app.security import verify_api_key, get_expected_api_key, RateLimiter

# Single shared instance for the process. Documented limitation: this is
# in-memory and per-process — fine for a single-instance deploy, not for
# multiple replicas behind a load balancer (see PHASE_6_ROADMAP.md).
_rate_limiter = RateLimiter(max_requests=60, window_seconds=60)


def require_api_key(x_api_key: str | None = Header(default=None)):
    expected = get_expected_api_key()
    if not verify_api_key(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def enforce_rate_limit(request: Request):
    client_key = request.client.host if request.client else "unknown"
    if not _rate_limiter.allow(client_key):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again shortly.",
        )
