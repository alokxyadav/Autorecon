"""
Bridges the DB layer (SQLAlchemy rows) to the pure matching engine, and
persists results. This is the ONLY place DB writes happen for reconciliation
data — the matching engine itself never touches the database.

Every result written to `reconciliation_results` is accompanied by an
`audit_log` entry written in the same transaction, so the two tables can
never drift apart (no result should ever exist without a corresponding
audit trail explaining how it was produced).
"""

import json
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.transaction import TransactionRecord
from app.models.settlement import SettlementRecord
from app.models.bank_statement_line import BankStatementLineRecord
from app.models.reconciliation_result import ReconciliationResultRecord
from app.models.audit_log import AuditLogRecord
from app.services import matching_engine as engine
from app.schemas import ReconciliationSummary
from app.services.time_utils import utc_now


def _to_engine_transaction(row: TransactionRecord) -> engine.Transaction:
    return engine.Transaction(
        id=row.id, order_id=row.order_id, amount=row.amount,
        currency=row.currency, status=row.status,
        created_at=row.created_at, source=row.source,
    )


def _to_engine_settlement(row: SettlementRecord) -> engine.Settlement:
    return engine.Settlement(
        id=row.id, razorpay_settlement_id=row.razorpay_settlement_id,
        transaction_order_id=row.transaction_order_id,
        amount=row.amount, fees=row.fees, utr=row.utr,
        settled_at=row.settled_at,
    )


def _to_engine_bank_line(row: BankStatementLineRecord) -> engine.BankStatementLine:
    return engine.BankStatementLine(
        id=row.id, amount=row.amount, description=row.description,
        value_date=row.value_date, utr_reference=row.utr_reference,
    )


def run_reconciliation(db: Session, now: datetime | None = None) -> tuple[ReconciliationSummary, int]:
    """Loads all source data, runs the deterministic engine, and persists
    every result plus a matching audit_log entry. Clears any previous
    reconciliation_results first (Phase 1 treats each run as a full replay;
    Phase 2+ may want incremental runs, noted in HANDOFF.md).
    """
    now = now or utc_now()

    txn_rows = db.query(TransactionRecord).all()
    settlement_rows = db.query(SettlementRecord).all()
    bank_line_rows = db.query(BankStatementLineRecord).all()

    transactions = [_to_engine_transaction(r) for r in txn_rows]
    settlements = [_to_engine_settlement(r) for r in settlement_rows]
    bank_lines = [_to_engine_bank_line(r) for r in bank_line_rows]

    run = engine.reconcile(transactions, settlements, bank_lines, now=now)

    db.query(ReconciliationResultRecord).delete()
    db.commit()

    for result in run.results:
        record = ReconciliationResultRecord(
            transaction_id=result.transaction_id,
            settlement_id=result.settlement_id,
            bank_line_id=result.bank_line_id,
            match_type=result.match_type.value,
            status=result.status.value,
            confidence=result.confidence,
            delta_amount=result.delta_amount,
            notes=result.notes,
        )
        db.add(record)

        audit_entry = AuditLogRecord(
            event_type="match_attempt",
            payload_json=json.dumps({
                "transaction_id": result.transaction_id,
                "settlement_id": result.settlement_id,
                "bank_line_id": result.bank_line_id,
                "match_type": result.match_type.value,
                "status": result.status.value,
                "confidence": result.confidence,
                "delta_amount": str(result.delta_amount),
            }),
            reasoning_text=result.notes,
            decided_by="system",
        )
        db.add(audit_entry)

    db.commit()

    summary = _build_summary(run, transactions)
    return summary, len(run.results)


def _build_summary(run: engine.ReconciliationRun, transactions: list[engine.Transaction]) -> ReconciliationSummary:
    counts = {status: 0 for status in engine.ReconciliationStatus}
    unmatched_value = sum(
        (r.delta_amount for r in run.results if r.status == engine.ReconciliationStatus.UNMATCHED),
        start=Decimal("0.00"),
    )
    for r in run.results:
        counts[r.status] = counts.get(r.status, 0) + 1

    return ReconciliationSummary(
        total_transactions=len([t for t in transactions if t.status == "captured"]),
        matched_count=counts.get(engine.ReconciliationStatus.MATCHED, 0),
        partial_count=counts.get(engine.ReconciliationStatus.PARTIAL, 0),
        unmatched_count=counts.get(engine.ReconciliationStatus.UNMATCHED, 0),
        pending_settlement_count=counts.get(engine.ReconciliationStatus.PENDING_SETTLEMENT, 0),
        total_unmatched_value=unmatched_value,
        duplicate_bank_lines=len(run.duplicate_bank_line_ids),
        orphan_settlements=len(run.orphan_settlement_ids),
    )
