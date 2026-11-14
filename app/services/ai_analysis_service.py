"""
Bridges `reconciliation_results` DB rows to the AI reasoning layer and
policy gate. Mirrors the structure of reconciliation_service.py: this is
the only place that writes ai_proposed_resolution / ai_confidence / status
based on an LLM's output, and it never does so without going through
evaluate_policy() first and logging to audit_log.
"""

import json
from decimal import Decimal
from typing import Callable

from sqlalchemy.orm import Session

from app.models.reconciliation_result import ReconciliationResultRecord
from app.models.transaction import TransactionRecord
from app.models.settlement import SettlementRecord
from app.models.bank_statement_line import BankStatementLineRecord
from app.models.audit_log import AuditLogRecord
from app.services.ai_reasoning_service import get_ai_explanation
from app.services.policy_gate import (
    PolicyGateInput, PolicyDecision, evaluate_policy, load_thresholds_from_env,
)
from app.services.matching_engine import ReconciliationStatus


def _build_item_context(db: Session, result: ReconciliationResultRecord) -> dict:
    txn = db.get(TransactionRecord, result.transaction_id) if result.transaction_id else None
    settlement = db.get(SettlementRecord, result.settlement_id) if result.settlement_id else None
    bank_line = db.get(BankStatementLineRecord, result.bank_line_id) if result.bank_line_id else None

    return {
        "order_id": txn.order_id if txn else None,
        "transaction_amount": str(txn.amount) if txn else None,
        "transaction_created_at": txn.created_at.isoformat() if txn else None,
        "settlement_amount": str(settlement.amount) if settlement else None,
        "settlement_fees": str(settlement.fees) if settlement else None,
        "settlement_utr": settlement.utr if settlement else None,
        "settlement_settled_at": settlement.settled_at.isoformat() if settlement else None,
        "bank_line_amount": str(bank_line.amount) if bank_line else None,
        "bank_line_description": bank_line.description if bank_line else None,
        "bank_line_value_date": bank_line.value_date.isoformat() if bank_line else None,
        "delta_amount": str(result.delta_amount),
        "match_type": result.match_type,
        "notes": result.notes,
    }


def analyze_unresolved_items(
    db: Session,
    complete_fn: Callable[[str, str], str],
    reanalyze: bool = False,
) -> dict:
    """Runs the AI reasoning layer + policy gate over every reconciliation
    result currently in UNMATCHED or PARTIAL status. Returns a summary of
    how many were auto-resolved vs. routed to human review.
    """
    query = db.query(ReconciliationResultRecord).filter(
        ReconciliationResultRecord.status.in_([
            ReconciliationStatus.UNMATCHED.value,
            ReconciliationStatus.PARTIAL.value,
        ])
    )
    if not reanalyze:
        query = query.filter(ReconciliationResultRecord.ai_proposed_resolution.is_(None))

    items = query.all()
    confidence_threshold, max_amount = load_thresholds_from_env()

    auto_resolved_count = 0
    pending_review_count = 0

    for item in items:
        context = _build_item_context(db, item)
        explanation = get_ai_explanation(context, complete_fn)

        db.add(AuditLogRecord(
            event_type="ai_proposal",
            payload_json=json.dumps({
                "reconciliation_result_id": item.id,
                "hypothesis": explanation.hypothesis,
                "proposed_resolution": explanation.proposed_resolution,
                "confidence": explanation.confidence,
                "is_valid": explanation.is_valid,
                "raw_error": explanation.raw_error,
            }),
            reasoning_text=explanation.hypothesis,
            decided_by="claude",
        ))

        gate_result = evaluate_policy(
            PolicyGateInput(
                ai_confidence=explanation.confidence,
                delta_amount=item.delta_amount,
                has_valid_proposal=explanation.is_valid,
            ),
            confidence_threshold=confidence_threshold,
            max_amount=max_amount,
        )

        item.ai_proposed_resolution = explanation.proposed_resolution
        item.ai_confidence = explanation.confidence

        if gate_result.decision == PolicyDecision.AUTO_RESOLVED:
            item.status = ReconciliationStatus.AUTO_RESOLVED.value
            auto_resolved_count += 1
        else:
            item.status = ReconciliationStatus.PENDING_HUMAN_REVIEW.value
            pending_review_count += 1

        db.add(AuditLogRecord(
            event_type="match_attempt",  # policy gate decision, logged distinctly from the AI proposal above
            payload_json=json.dumps({
                "reconciliation_result_id": item.id,
                "policy_decision": gate_result.decision.value,
                "reason": gate_result.reason,
            }),
            reasoning_text=gate_result.reason,
            decided_by="system",
        ))

    db.commit()

    return {
        "items_analyzed": len(items),
        "auto_resolved": auto_resolved_count,
        "pending_human_review": pending_review_count,
    }


def record_human_decision(
    db: Session,
    result_id: int,
    approve: bool,
    reviewer_name: str,
) -> ReconciliationResultRecord:
    result = db.query(ReconciliationResultRecord).filter(
        ReconciliationResultRecord.id == result_id
    ).first()
    if result is None:
        return None

    result.status = ReconciliationStatus.APPROVED.value if approve else ReconciliationStatus.REJECTED.value
    result.reviewer_name = reviewer_name

    db.add(AuditLogRecord(
        event_type="human_decision",
        payload_json=json.dumps({
            "reconciliation_result_id": result.id,
            "decision": "approved" if approve else "rejected",
            "ai_proposed_resolution": result.ai_proposed_resolution,
            "ai_confidence": result.ai_confidence,
        }),
        reasoning_text=f"{'Approved' if approve else 'Rejected'} by {reviewer_name}.",
        decided_by=reviewer_name,
    ))

    db.commit()
    db.refresh(result)
    return result
