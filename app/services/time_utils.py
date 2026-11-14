"""
Timezone normalization.

CRITICAL PRODUCTION BUG THIS FILE FIXES: SQLAlchemy's DateTime(timezone=True)
columns (used throughout this project's models) return timezone-AWARE
datetime objects when read back from Postgres via psycopg2, but SQLite
(the local dev default) typically returns timezone-NAIVE ones. Code that
mixed `datetime.utcnow()` (naive) with values read from the database would
work fine against SQLite in local dev and then crash with
`TypeError: can't subtract offset-naive and offset-aware datetimes` the
moment it was pointed at the real Postgres deployment target — exactly the
kind of bug that only shows up in production, after a demo has looked fine
locally the whole time.

Pure stdlib, dependency-free, so it's testable the same way as
matching_engine.py.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Always timezone-aware. Never use datetime.utcnow() (naive, and
    deprecated as of Python 3.12) anywhere in this codebase — use this
    instead.
    """
    return datetime.now(timezone.utc)


def to_utc(dt: datetime) -> datetime:
    """Normalizes any datetime — naive or aware, from SQLite or Postgres —
    to timezone-aware UTC. Call this on BOTH sides of any datetime
    subtraction/comparison in this codebase before doing the arithmetic.
    A naive datetime is assumed to already represent UTC (true for every
    naive datetime this codebase produces or reads from SQLite).
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
