"""
AutoRecon — Deterministic Matching Engine
==========================================

This module is intentionally dependency-free (no SQLAlchemy, no FastAPI, no
Claude API). It operates on plain dataclasses so it can be:
  1. Unit tested in complete isolation, with zero infrastructure.
  2. Called from the API layer (Phase 1) with real DB-backed data.
  3. Called from the AI reasoning layer (Phase 2) to get the exact list of
     items that need an LLM explanation, via `find_items_needing_review()`.

DESIGN PRINCIPLE (do not violate this in later phases):
This engine is the deterministic source of truth for whether two records
match. An LLM may explain *why* something in `UNMATCHED`/low-confidence
state failed to match, and may *propose* a resolution — but it must never
directly flip a match_type or status. Only this engine (or an explicit
human approval action) may do that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional

from app.services.time_utils import utc_now, to_utc


# ---------------------------------------------------------------------------
# Tunable constants — centralised here so Phase 2's policy gate and Phase 4's
# forecast module reference the same numbers rather than hardcoding copies.
# ---------------------------------------------------------------------------

EXACT_MATCH_TOLERANCE = Decimal("0.01")     # rounding-only difference
FEE_FUZZY_TOLERANCE = Decimal("5.00")       # acceptable unexplained fee drift
BANK_AMOUNT_TOLERANCE = Decimal("1.00")     # bank line vs settlement amount
SETTLEMENT_GRACE_PERIOD_DAYS = 3            # typical T+N settlement cycle


class MatchType(str, Enum):
    EXACT = "exact"
    FUZZY = "fuzzy"
    UNMATCHED = "unmatched"
    DUPLICATE = "duplicate"
    PENDING = "pending"  # not yet due — not a discrepancy


class ReconciliationStatus(str, Enum):
    MATCHED = "matched"
    PARTIAL = "partial"
    UNMATCHED = "unmatched"
    PENDING_SETTLEMENT = "pending_settlement"
    PENDING_HUMAN_REVIEW = "pending_human_review"
    AUTO_RESOLVED = "auto_resolved"
    APPROVED = "approved"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Data shapes — mirror the DB models field-for-field so mapping in/out of
# SQLAlchemy rows in the API layer is a trivial 1:1 conversion.
# ---------------------------------------------------------------------------

@dataclass
class Transaction:
    id: int
    order_id: str
    amount: Decimal
    currency: str
    status: str  # "captured" | "failed" | "refunded"
    created_at: datetime
    source: str = "razorpay_test_mode"


@dataclass
class Settlement:
    id: int
    razorpay_settlement_id: str
    transaction_order_id: str
    amount: Decimal   # net amount actually paid out
    fees: Decimal
    utr: str
    settled_at: datetime


@dataclass
class BankStatementLine:
    id: int
    amount: Decimal
    description: str
    value_date: datetime
    utr_reference: Optional[str] = None


@dataclass
class MatchResult:
    """One row of what will become a `reconciliation_results` DB record."""
    transaction_id: Optional[int] = None
    settlement_id: Optional[int] = None
    bank_line_id: Optional[int] = None
    match_type: MatchType = MatchType.UNMATCHED
    status: ReconciliationStatus = ReconciliationStatus.UNMATCHED
    confidence: int = 0
    delta_amount: Decimal = Decimal("0.00")
    notes: str = ""


@dataclass
class ReconciliationRun:
    """Full output of one `reconcile()` call — what the API/audit layer persists."""
    results: list[MatchResult] = field(default_factory=list)
    orphan_bank_line_ids: list[int] = field(default_factory=list)
    duplicate_bank_line_ids: list[int] = field(default_factory=list)
    orphan_settlement_ids: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Tier 1 + Tier 2: transaction <-> settlement matching
# ---------------------------------------------------------------------------

def match_transaction_to_settlement(
    transaction: Transaction,
    settlement: Settlement,
    fee_tolerance: Decimal = FEE_FUZZY_TOLERANCE,
    exact_tolerance: Decimal = EXACT_MATCH_TOLERANCE,
) -> MatchResult:
    """Compare what the transaction expected to net out to vs. what actually
    settled. Returns a MatchResult classified into exact / fuzzy / unmatched.
    """
    expected_net = transaction.amount - settlement.fees
    delta = abs(expected_net - settlement.amount)

    if delta <= exact_tolerance:
        return MatchResult(
            transaction_id=transaction.id,
            settlement_id=settlement.id,
            match_type=MatchType.EXACT,
            status=ReconciliationStatus.MATCHED,
            confidence=100,
            delta_amount=delta,
            notes="Settlement amount matches transaction minus fees exactly.",
        )

    if delta <= fee_tolerance:
        # Linearly scale confidence between 60 (at the tolerance edge) and 95
        # (near-zero delta) — gives the review queue something more useful
        # than a flat number to sort/filter by.
        proximity = Decimal("1") - (delta / fee_tolerance)
        confidence = int(60 + proximity * 35)
        return MatchResult(
            transaction_id=transaction.id,
            settlement_id=settlement.id,
            match_type=MatchType.FUZZY,
            status=ReconciliationStatus.PARTIAL,
            confidence=confidence,
            delta_amount=delta,
            notes=(
                f"Settlement differs from expected net by {delta} "
                f"(within fee tolerance of {fee_tolerance})."
            ),
        )

    return MatchResult(
        transaction_id=transaction.id,
        settlement_id=settlement.id,
        match_type=MatchType.UNMATCHED,
        status=ReconciliationStatus.UNMATCHED,
        confidence=0,
        delta_amount=delta,
        notes=(
            f"Settlement differs from expected net by {delta}, exceeding fee "
            f"tolerance of {fee_tolerance}. Needs explanation."
        ),
    )


def find_settlement_for_transaction(
    transaction: Transaction,
    settlements: list[Settlement],
    now: Optional[datetime] = None,
    grace_period_days: int = SETTLEMENT_GRACE_PERIOD_DAYS,
) -> Optional[Settlement]:
    """Deterministic lookup by order_id reference — no fuzzy guessing here.
    Amount-based "which settlement is this probably for" guessing is exactly
    the kind of silent error reconciliation tools must not make.
    """
    for s in settlements:
        if s.transaction_order_id == transaction.order_id:
            return s
    return None


def classify_missing_settlement(
    transaction: Transaction,
    now: Optional[datetime] = None,
    grace_period_days: int = SETTLEMENT_GRACE_PERIOD_DAYS,
) -> MatchResult:
    """A transaction with no settlement yet is only a discrepancy once the
    normal settlement cycle has elapsed. Before that, it's just PENDING.
    """
    now = to_utc(now) if now else utc_now()
    age = now - to_utc(transaction.created_at)

    if age <= timedelta(days=grace_period_days):
        return MatchResult(
            transaction_id=transaction.id,
            match_type=MatchType.PENDING,
            status=ReconciliationStatus.PENDING_SETTLEMENT,
            confidence=100,
            notes=(
                f"Transaction is {age.days}d old; within the "
                f"{grace_period_days}d settlement cycle. Not a discrepancy yet."
            ),
        )

    return MatchResult(
        transaction_id=transaction.id,
        match_type=MatchType.UNMATCHED,
        status=ReconciliationStatus.UNMATCHED,
        confidence=0,
        notes=(
            f"Transaction is {age.days}d old with no matching settlement, "
            f"exceeding the {grace_period_days}d grace period. Needs explanation."
        ),
    )


# ---------------------------------------------------------------------------
# Tier 3: settlement <-> bank statement matching
# ---------------------------------------------------------------------------

def match_settlement_to_bank(
    settlement: Settlement,
    bank_lines: list[BankStatementLine],
    amount_tolerance: Decimal = BANK_AMOUNT_TOLERANCE,
) -> Optional[BankStatementLine]:
    """Match by UTR reference first (authoritative), falling back to
    amount-only matching only if no UTR is present on either side — and even
    then, require the amount to be within tolerance.
    """
    utr_matches = [
        b for b in bank_lines
        if b.utr_reference and b.utr_reference == settlement.utr
    ]
    for b in utr_matches:
        if abs(b.amount - settlement.amount) <= amount_tolerance:
            return b

    if not utr_matches:
        for b in bank_lines:
            if b.utr_reference:
                continue  # has a UTR but it didn't match above — not a candidate
            if abs(b.amount - settlement.amount) <= amount_tolerance:
                return b

    return None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def detect_duplicate_bank_lines(bank_lines: list[BankStatementLine]) -> list[int]:
    """Flags bank lines that appear to be duplicates of another line: same
    amount, same value_date, and same (or absent) UTR reference. The first
    occurrence in each group is treated as legitimate; the rest are flagged.
    """
    seen: dict[tuple, int] = {}
    duplicate_ids: list[int] = []

    for line in sorted(bank_lines, key=lambda b: b.id):
        key = (line.amount, line.value_date.date(), line.utr_reference)
        if key in seen:
            duplicate_ids.append(line.id)
        else:
            seen[key] = line.id

    return duplicate_ids


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def reconcile(
    transactions: list[Transaction],
    settlements: list[Settlement],
    bank_lines: list[BankStatementLine],
    now: Optional[datetime] = None,
) -> ReconciliationRun:
    """Runs the full three-tier reconciliation over one batch of data.

    This function must remain pure (no I/O, no side effects) — the API layer
    is responsible for persisting `ReconciliationRun.results` and writing the
    corresponding audit_log entries, one per result, before any status is
    considered final.
    """
    now = to_utc(now) if now else utc_now()
    results: list[MatchResult] = []

    duplicate_ids = set(detect_duplicate_bank_lines(bank_lines))
    for dup_id in duplicate_ids:
        results.append(MatchResult(
            bank_line_id=dup_id,
            match_type=MatchType.DUPLICATE,
            status=ReconciliationStatus.UNMATCHED,
            confidence=0,
            notes="Bank line appears to duplicate another line with the same "
                  "amount, date, and reference.",
        ))

    clean_bank_lines = [b for b in bank_lines if b.id not in duplicate_ids]
    matched_settlement_ids: set[int] = set()
    matched_bank_line_ids: set[int] = set()

    for txn in transactions:
        if txn.status != "captured":
            continue  # failed/refunded transactions are out of scope for Phase 1

        settlement = find_settlement_for_transaction(txn, settlements, now=now)

        if settlement is None:
            results.append(classify_missing_settlement(txn, now=now))
            continue

        txn_settlement_result = match_transaction_to_settlement(txn, settlement)
        matched_settlement_ids.add(settlement.id)

        bank_line = match_settlement_to_bank(settlement, clean_bank_lines)
        if bank_line is not None:
            matched_bank_line_ids.add(bank_line.id)
            txn_settlement_result.bank_line_id = bank_line.id
            if txn_settlement_result.match_type == MatchType.EXACT:
                txn_settlement_result.notes += " Confirmed against bank statement."
        elif txn_settlement_result.match_type == MatchType.EXACT:
            # Settlement matched the transaction cleanly, but hasn't shown up
            # in the bank statement yet — downgrade from fully matched to
            # partial rather than silently claiming full confirmation.
            txn_settlement_result.status = ReconciliationStatus.PARTIAL
            txn_settlement_result.confidence = 80
            txn_settlement_result.notes += (
                " Not yet confirmed in bank statement — may still be in transit."
            )

        results.append(txn_settlement_result)

    orphan_bank_lines = [
        b.id for b in clean_bank_lines
        if b.id not in matched_bank_line_ids
    ]

    # A settlement that references an order_id with no corresponding
    # transaction anywhere in the system is a discrepancy in its own right —
    # possibly a data sync gap, a transaction from before this system's
    # records began, or a genuine error upstream. It must be surfaced, not
    # silently dropped just because the main loop above only iterates over
    # transactions.
    known_order_ids = {t.order_id for t in transactions}
    orphan_settlements = [s for s in settlements if s.transaction_order_id not in known_order_ids]
    for orphan in orphan_settlements:
        results.append(MatchResult(
            settlement_id=orphan.id,
            match_type=MatchType.UNMATCHED,
            status=ReconciliationStatus.UNMATCHED,
            confidence=0,
            delta_amount=orphan.amount,
            notes=(
                f"Settlement references order_id '{orphan.transaction_order_id}', which has "
                f"no corresponding transaction in the system. Possible data sync gap."
            ),
        ))

    return ReconciliationRun(
        results=results,
        orphan_bank_line_ids=orphan_bank_lines,
        duplicate_bank_line_ids=sorted(duplicate_ids),
        orphan_settlement_ids=[s.id for s in orphan_settlements],
    )


def find_items_needing_review(run: ReconciliationRun) -> list[MatchResult]:
    """Convenience filter for Phase 2: exactly the items an LLM should look
    at. Anything MATCHED or already PENDING_SETTLEMENT is excluded — the
    Claude API budget should never be spent explaining things that already
    have a deterministic, confident answer.
    """
    return [
        r for r in run.results
        if r.status in (ReconciliationStatus.UNMATCHED, ReconciliationStatus.PARTIAL)
    ]
