"""
Tests for the deterministic matching engine.

These tests use zero external dependencies beyond the standard library plus
the matching_engine module itself, so they run identically whether pytest is
installed or not (see the `if __name__ == "__main__"` runner at the bottom).
Once you `pip install -r requirements.txt`, run these normally with `pytest`.
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.matching_engine import (
    Transaction,
    Settlement,
    BankStatementLine,
    MatchType,
    ReconciliationStatus,
    match_transaction_to_settlement,
    find_settlement_for_transaction,
    classify_missing_settlement,
    match_settlement_to_bank,
    detect_duplicate_bank_lines,
    reconcile,
    find_items_needing_review,
)

NOW = datetime(2026, 8, 27, 12, 0, 0)


def _txn(id, order_id, amount, created_at=None, status="captured"):
    return Transaction(
        id=id, order_id=order_id, amount=Decimal(amount),
        currency="INR", status=status,
        created_at=created_at or NOW - timedelta(days=1),
    )


def _settlement(id, order_id, amount, fees, utr, settled_at=None):
    return Settlement(
        id=id, razorpay_settlement_id=f"stl_{id}", transaction_order_id=order_id,
        amount=Decimal(amount), fees=Decimal(fees), utr=utr,
        settled_at=settled_at or NOW,
    )


def _bank_line(id, amount, utr_reference=None, value_date=None, description="NEFT CR"):
    return BankStatementLine(
        id=id, amount=Decimal(amount), description=description,
        value_date=value_date or NOW, utr_reference=utr_reference,
    )


# ---------------------------------------------------------------------------
# Tier 1: exact matches
# ---------------------------------------------------------------------------

def test_exact_match_when_amounts_reconcile_perfectly():
    txn = _txn(1, "order_1", "1000.00")
    stl = _settlement(1, "order_1", "980.00", "20.00", "UTR001")
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type == MatchType.EXACT
    assert result.status == ReconciliationStatus.MATCHED
    assert result.confidence == 100
    assert result.delta_amount == Decimal("0.00")


def test_exact_match_tolerates_sub_paisa_rounding():
    txn = _txn(1, "order_1", "1000.005")
    stl = _settlement(1, "order_1", "980.00", "20.00", "UTR001")
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type == MatchType.EXACT


# ---------------------------------------------------------------------------
# Tier 2: fuzzy matches (fee drift within tolerance)
# ---------------------------------------------------------------------------

def test_fuzzy_match_within_fee_tolerance():
    txn = _txn(1, "order_1", "1000.00")
    # Expected net = 980.00, actual settled = 977.00 -> delta 3.00, within 5.00 tolerance
    stl = _settlement(1, "order_1", "977.00", "20.00", "UTR001")
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type == MatchType.FUZZY
    assert result.status == ReconciliationStatus.PARTIAL
    assert 60 <= result.confidence <= 95


def test_fuzzy_match_confidence_decreases_as_delta_grows():
    txn = _txn(1, "order_1", "1000.00")
    stl_small_delta = _settlement(1, "order_1", "979.00", "20.00", "UTR001")   # delta 1.00
    stl_big_delta = _settlement(2, "order_1", "975.50", "20.00", "UTR002")     # delta 4.50
    small = match_transaction_to_settlement(txn, stl_small_delta)
    big = match_transaction_to_settlement(txn, stl_big_delta)
    assert small.confidence > big.confidence


# ---------------------------------------------------------------------------
# Tier 3: genuine unmatched (exceeds tolerance)
# ---------------------------------------------------------------------------

def test_unmatched_when_delta_exceeds_fee_tolerance():
    txn = _txn(1, "order_1", "1000.00")
    stl = _settlement(1, "order_1", "900.00", "20.00", "UTR001")  # delta 80
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type == MatchType.UNMATCHED
    assert result.status == ReconciliationStatus.UNMATCHED
    assert result.confidence == 0


# ---------------------------------------------------------------------------
# Missing settlement classification (pending vs. genuinely missing)
# ---------------------------------------------------------------------------

def test_recent_transaction_without_settlement_is_pending_not_a_discrepancy():
    txn = _txn(1, "order_1", "1000.00", created_at=NOW - timedelta(days=1))
    result = classify_missing_settlement(txn, now=NOW)
    assert result.status == ReconciliationStatus.PENDING_SETTLEMENT
    assert result.match_type == MatchType.PENDING


def test_old_transaction_without_settlement_is_flagged_unmatched():
    txn = _txn(1, "order_1", "1000.00", created_at=NOW - timedelta(days=10))
    result = classify_missing_settlement(txn, now=NOW)
    assert result.status == ReconciliationStatus.UNMATCHED
    assert result.match_type == MatchType.UNMATCHED


def test_find_settlement_for_transaction_does_not_guess_by_amount():
    txn = _txn(1, "order_1", "1000.00")
    # Same amount, but a *different* order_id — must NOT be treated as a match.
    unrelated_settlement = _settlement(1, "order_999", "980.00", "20.00", "UTR001")
    found = find_settlement_for_transaction(txn, [unrelated_settlement])
    assert found is None


# ---------------------------------------------------------------------------
# Settlement <-> bank matching
# ---------------------------------------------------------------------------

def test_settlement_matches_bank_line_by_utr():
    stl = _settlement(1, "order_1", "980.00", "20.00", "UTR001")
    bank_lines = [_bank_line(1, "980.00", utr_reference="UTR001")]
    match = match_settlement_to_bank(stl, bank_lines)
    assert match is not None
    assert match.id == 1


def test_settlement_does_not_match_bank_line_with_wrong_utr_even_if_amount_matches():
    stl = _settlement(1, "order_1", "980.00", "20.00", "UTR001")
    bank_lines = [_bank_line(1, "980.00", utr_reference="UTR999")]
    match = match_settlement_to_bank(stl, bank_lines)
    assert match is None


def test_settlement_falls_back_to_amount_match_when_no_utr_present_anywhere():
    stl = _settlement(1, "order_1", "980.00", "20.00", "UTR001")
    bank_lines = [_bank_line(1, "980.00", utr_reference=None)]
    match = match_settlement_to_bank(stl, bank_lines)
    assert match is not None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def test_detects_duplicate_bank_lines():
    lines = [
        _bank_line(1, "500.00", utr_reference="UTR100", value_date=NOW),
        _bank_line(2, "500.00", utr_reference="UTR100", value_date=NOW),  # duplicate of #1
        _bank_line(3, "700.00", utr_reference="UTR200", value_date=NOW),
    ]
    duplicates = detect_duplicate_bank_lines(lines)
    assert duplicates == [2]


def test_does_not_flag_similar_but_distinct_lines_as_duplicates():
    lines = [
        _bank_line(1, "500.00", utr_reference="UTR100", value_date=NOW),
        _bank_line(2, "500.00", utr_reference="UTR200", value_date=NOW),  # different UTR
    ]
    duplicates = detect_duplicate_bank_lines(lines)
    assert duplicates == []


# ---------------------------------------------------------------------------
# Full orchestration
# ---------------------------------------------------------------------------

def test_reconcile_end_to_end_mixed_scenario():
    transactions = [
        _txn(1, "order_1", "1000.00"),                                    # clean match
        _txn(2, "order_2", "500.00"),                                     # fuzzy (fee drift)
        _txn(3, "order_3", "2000.00"),                                    # genuinely unmatched
        _txn(4, "order_4", "300.00", created_at=NOW - timedelta(hours=2)),  # pending, too new
        _txn(5, "order_5", "150.00", status="failed"),                    # excluded — not captured
    ]
    settlements = [
        _settlement(1, "order_1", "980.00", "20.00", "UTR001"),
        _settlement(2, "order_2", "483.00", "10.00", "UTR002"),  # expected 490, delta 7 -> unmatched actually
        _settlement(3, "order_3", "1200.00", "50.00", "UTR003"), # delta way over tolerance
        # order_4: no settlement yet (still within grace period)
        # order_5: failed transaction, correctly has no settlement
    ]
    bank_lines = [
        _bank_line(1, "980.00", utr_reference="UTR001"),
        _bank_line(2, "483.00", utr_reference="UTR002"),
        # UTR003 never lands in the bank statement
        _bank_line(3, "980.00", utr_reference="UTR001"),  # duplicate of bank line #1
    ]

    run = reconcile(transactions, settlements, bank_lines, now=NOW)

    by_txn = {r.transaction_id: r for r in run.results if r.transaction_id}

    assert by_txn[1].status == ReconciliationStatus.MATCHED
    assert by_txn[1].match_type == MatchType.EXACT

    # order_2: expected net 490.00, settled 483.00 -> delta 7.00, exceeds 5.00 tolerance -> unmatched
    assert by_txn[2].status == ReconciliationStatus.UNMATCHED

    assert by_txn[3].status == ReconciliationStatus.UNMATCHED
    assert by_txn[4].status == ReconciliationStatus.PENDING_SETTLEMENT
    assert 5 not in by_txn  # failed transaction excluded entirely

    assert run.duplicate_bank_line_ids == [3]

    # find_items_needing_review surfaces every UNMATCHED/PARTIAL result,
    # including the duplicate bank line (transaction_id=None) — duplicates
    # deserve an LLM look too, they just aren't tied to a transaction.
    review_items = find_items_needing_review(run)
    review_txn_ids = {r.transaction_id for r in review_items if r.transaction_id}
    assert review_txn_ids == {2, 3}  # genuine transaction-level discrepancies
    assert any(r.bank_line_id == 3 for r in review_items)  # duplicate also surfaced
    assert len(review_items) == 3  # order_2, order_3, and the duplicate bank line


def test_find_items_needing_review_excludes_matched_and_pending():
    transactions = [_txn(1, "order_1", "1000.00")]
    settlements = [_settlement(1, "order_1", "980.00", "20.00", "UTR001")]
    bank_lines = [_bank_line(1, "980.00", utr_reference="UTR001")]
    run = reconcile(transactions, settlements, bank_lines, now=NOW)
    assert find_items_needing_review(run) == []


# ---------------------------------------------------------------------------
# Minimal runner so this file proves itself correct even without pytest
# installed (pytest is still the intended long-term runner — see README).
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_fns = [(name, obj) for name, obj in list(globals().items())
                if name.startswith("test_") and callable(obj)]
    passed, failed = 0, 0
    for name, fn in test_fns:
        try:
            fn()
            print(f"PASS  {name}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed out of {len(test_fns)} tests")
    sys.exit(1 if failed else 0)
