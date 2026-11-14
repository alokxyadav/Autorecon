"""
Database engine + session setup.

Local dev: defaults to SQLite (zero setup, works out of the box).
Production: set DATABASE_URL to a Postgres connection string, e.g.
  postgresql+psycopg2://user:password@host:5432/autorecon

No other code in the app should construct an engine or session directly —
always go through `get_db()` so connection handling stays in one place.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./autorecon.db")

if DATABASE_URL.startswith("sqlite"):
    # SQLite doesn't support the pool_size/max_overflow args and only needs
    # check_same_thread disabled for use across FastAPI's threadpool.
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Production Postgres: pre-ping avoids handing out dead connections after
    # a DB restart or idle timeout (a common source of intermittent 500s that
    # are otherwise maddening to diagnose), and pool_recycle avoids holding
    # connections open longer than most managed Postgres providers allow.
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE_SECONDS", "1800")),
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency — yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Creates all tables directly — used for local/demo convenience only.
    In any environment with `alembic.ini` configured (see /migrations),
    prefer `alembic upgrade head` instead and skip calling this. The Docker
    image's CMD runs migrations explicitly rather than relying on this
    function; it remains here so `uvicorn app.main:app --reload` still works
    with zero setup for local development.
    """
    from app.models import (  # noqa: F401 — import so metadata is populated
        transaction, settlement, bank_statement_line,
        reconciliation_result, audit_log,
    )
    Base.metadata.create_all(bind=engine)
