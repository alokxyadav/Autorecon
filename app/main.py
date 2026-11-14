import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import text

from app.database import init_db, SessionLocal
from app.logging_config import configure_logging, get_logger, request_id_var
from app.routers import reconciliation, audit, forecast
from app.security_deps import require_api_key, enforce_rate_limit

configure_logging()
logger = get_logger("autorecon")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables for local/demo convenience (see database.init_db
    # docstring — production deployments should run `alembic upgrade head`
    # instead, which the Docker image's CMD already does).
    init_db()
    logger.info("AutoRecon API starting up")
    yield
    logger.info("AutoRecon API shutting down")


app = FastAPI(
    title="AutoRecon API",
    description=(
        "Deterministic reconciliation + AI-assisted explanation engine for "
        "the Razorpay AI Buildathon (Track: AI Finance Controller). "
        "The LLM never has final authority over money movement — see "
        "README.md for the full architecture rationale."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS origins: defaults to "*" for zero-config local dev/demo. Set
# CORS_ALLOWED_ORIGINS to a comma-separated list of real domains (e.g.
# "https://autorecon.vercel.app") before any real production deployment —
# a wildcard origin is fine here only because this API doesn't use
# cookie-based auth (API-key-in-header auth isn't vulnerable to the same
# cross-site risks that make wildcard + credentials dangerous).
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "*")
_cors_origins = (
    ["*"] if _cors_origins_env == "*"
    else [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id_and_logging(request: Request, call_next):
    """Assigns a correlation ID to every request, makes it available to any
    log line emitted anywhere during processing (via the contextvar in
    logging_config.py), and logs a single structured line per request with
    method/path/status/duration — enough to reconstruct what happened
    without needing per-endpoint logging calls scattered everywhere.
    """
    req_id = str(uuid.uuid4())
    token = request_id_var.set(req_id)
    start = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(f"Unhandled exception processing {request.method} {request.url.path}")
        raise
    finally:
        request_id_var.reset(token)

    duration_ms = round((time.monotonic() - start) * 1000, 2)
    logger.info(
        f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms}ms)"
    )
    response.headers["X-Request-ID"] = req_id
    return response


# Basic security headers on every response. Not a replacement for a proper
# WAF/CDN layer in front of a real deployment, but closes the cheapest gaps.
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Applies to every raised HTTPException across the app — genuinely
    unmatched routes (404), auth failures (401 from security_deps), rate
    limiting (429), and explicit not-found responses from individual
    endpoints (e.g. GET /reconciliation/results/{id} for a missing id).
    Preserves the original status code and detail message; adds structured
    logging and a request_id for consistency with the 500 handler below, so
    a 404 shows up in the same log stream as everything else instead of
    silently returning FastAPI's bare default `{"detail": "Not Found"}`
    with no server-side record it ever happened.
    """
    log = logger.warning if exc.status_code < 500 else logger.error
    log(f"HTTP {exc.status_code} on {request.method} {request.url.path}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id_var.get()},
        headers=exc.headers or {},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Cleaner 422 responses than FastAPI's default, and logged so malformed
    client requests show up in the same structured log stream as everything
    else rather than only in an ad-hoc traceback.
    """
    logger.warning(f"Validation error on {request.method} {request.url.path}: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Invalid request.", "errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort handler: never leak a raw stack trace to the client (an
    information disclosure risk), but always log the full exception
    server-side, tagged with the request ID so it can be cross-referenced
    against the structured log stream.
    """
    logger.exception(f"Unhandled exception on {request.method} {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected error occurred. This has been logged for investigation.",
            "request_id": request_id_var.get(),
        },
    )


# API key + rate limiting applied to every data-touching route. Auth is a
# no-op if AUTORECON_API_KEY isn't set (see security.verify_api_key) so
# local dev and the demo work with zero setup — set the env var before any
# real deployment. /health and /health/ready are intentionally excluded so
# uptime monitors and orchestrators don't need a key.
protected = [Depends(require_api_key), Depends(enforce_rate_limit)]

app.include_router(reconciliation.router, dependencies=protected)
app.include_router(audit.router, dependencies=protected)
app.include_router(forecast.router, dependencies=protected)


@app.get("/health")
def health_check():
    """Liveness probe — just confirms the process is up and responding.
    Does NOT check the database; use /health/ready for that."""
    return {"status": "ok", "service": "autorecon-api"}


@app.get("/health/ready")
def readiness_check():
    """Readiness probe — actually confirms the database is reachable.
    Orchestrators (Kubernetes, Railway, etc.) should use this to decide
    whether to route traffic to this instance, not /health.
    """
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "reason": "database_unreachable"},
        )
    return {"status": "ready", "service": "autorecon-api"}
