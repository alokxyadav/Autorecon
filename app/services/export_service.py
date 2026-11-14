"""
Export service — converts reconciliation results and audit log entries to
CSV. Pure stdlib (csv + io), no FastAPI/SQLAlchemy dependency, so the actual
row-formatting logic is testable in isolation the same way as
matching_engine.py.

WHY THIS MATTERS: a reconciliation tool that only shows data in a dashboard
isn't something a real finance team can use — they need to hand numbers to
auditors, import them into existing spreadsheets, or attach them to a
month-end close email. Locking every workflow behind a UI is a common way
an otherwise well-built internal tool never actually gets adopted.
"""

import csv
import io
from typing import Iterable


RECONCILIATION_CSV_COLUMNS = [
    "id", "transaction_id", "settlement_id", "bank_line_id",
    "match_type", "status", "confidence", "delta_amount", "notes",
    "ai_proposed_resolution", "ai_confidence", "reviewer_name",
    "created_at", "updated_at",
]

AUDIT_LOG_CSV_COLUMNS = [
    "id", "event_type", "decided_by", "reasoning_text", "created_at",
]


def _row_to_csv_dict(row: dict, columns: list[str]) -> dict:
    """Builds a dict with exactly the target columns, missing keys becoming
    empty strings rather than raising — export must never fail on a
    partially-populated row (e.g. a result with no AI proposal yet).
    """
    return {col: ("" if row.get(col) is None else str(row.get(col))) for col in columns}


def reconciliation_results_to_csv(results: Iterable[dict]) -> str:
    """`results` is an iterable of plain dicts (already-serialized rows —
    the caller converts ORM objects to dicts first, keeping this function
    free of any DB dependency). Returns a complete CSV document as a string.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RECONCILIATION_CSV_COLUMNS)
    writer.writeheader()
    for row in results:
        writer.writerow(_row_to_csv_dict(row, RECONCILIATION_CSV_COLUMNS))
    return buffer.getvalue()


def audit_log_to_csv(entries: Iterable[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=AUDIT_LOG_CSV_COLUMNS)
    writer.writeheader()
    for row in entries:
        writer.writerow(_row_to_csv_dict(row, AUDIT_LOG_CSV_COLUMNS))
    return buffer.getvalue()
