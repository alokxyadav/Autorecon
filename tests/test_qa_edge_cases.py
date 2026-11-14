"""
QA pass — edge cases specifically hunted for as a tester, separate from the
original per-module test files so it's clear which tests were written
alongside the code vs. added under adversarial review afterward.
"""

import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.matching_engine import (
    Transaction, Settlement, BankStatementLine,
    MatchType, ReconciliationStatus,
    match_transaction_to_settlement, match_settlement_to_bank,
    detect_duplicate_bank_lines, reconcile,
)
from app.services.policy_gate import evaluate_policy, PolicyGateInput, PolicyDecision
from app.services.ai_reasoning_service import parse_reasoning_response, ReasoningError
from app.security import verify_api_key, RateLimiter

NOW = datetime(2026, 8, 27, 12, 0, 0)


def _txn(id, order_id, amount, created_at=None, status="captured"):
    return Transaction(
        id=id, order_id=order_id, amount=Decimal(amount),
        currency="INR", status=status, created_at=created_at or NOW,
    )


def _settlement(id, order_id, amount, fees, utr, settled_at=None):
    return Settlement(
        id=id, razorpay_settlement_id=f"stl_{id}", transaction_order_id=order_id,
        amount=Decimal(amount), fees=Decimal(fees), utr=utr, settled_at=settled_at or NOW,
    )


# ---------------------------------------------------------------------------
# Matching engine — adversarial / boundary cases
# ---------------------------------------------------------------------------

def test_zero_amount_transaction_does_not_crash_matcher():
    txn = _txn(1, "order_1", "0.00")
    stl = _settlement(1, "order_1", "0.00", "0.00", "UTR001")
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type == MatchType.EXACT


def test_negative_settlement_amount_is_treated_as_a_large_discrepancy_not_a_crash():
    # A negative settlement (e.g. a chargeback clawback) should never crash
    # the matcher, even though it's an unusual case worth flagging.
    txn = _txn(1, "order_1", "1000.00")
    stl = _settlement(1, "order_1", "-980.00", "20.00", "UTR001")
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type == MatchType.UNMATCHED
    assert result.delta_amount > Decimal("1000")


def test_fees_larger_than_transaction_amount_does_not_crash():
    # Pathological but possible with a data entry error upstream.
    txn = _txn(1, "order_1", "10.00")
    stl = _settlement(1, "order_1", "5.00", "50.00", "UTR001")  # fees > amount
    result = match_transaction_to_settlement(txn, stl)
    assert result.match_type in (MatchType.UNMATCHED, MatchType.FUZZY)


def test_two_transactions_with_identical_amounts_do_not_cross_match():
    # Two unrelated ₹500 transactions on the same day must never be matched
    # to each other's settlements just because the amount coincides.
    txn_a = _txn(1, "order_a", "500.00")
    txn_b = _txn(2, "order_b", "500.00")
    stl_a = _settlement(1, "order_a", "490.00", "10.00", "UTR_A")
    stl_b = _settlement(2, "order_b", "490.00", "10.00", "UTR_B")

    result_a = match_transaction_to_settlement(txn_a, stl_a)
    result_b = match_transaction_to_settlement(txn_b, stl_b)
    assert result_a.settlement_id == 1
    assert result_b.settlement_id == 2


def test_bank_line_with_utr_present_never_falls_back_to_amount_only_matching():
    # If a bank line DOES have a UTR, it must not be matched by amount alone
    # even if no UTR-based match is found for it elsewhere — the fallback
    # path is only for lines with NO utr_reference at all.
    stl = _settlement(1, "order_1", "980.00", "20.00", "UTR001")
    bank_lines = [BankStatementLine(id=1, amount=Decimal("980.00"), description="x",
                                     value_date=NOW, utr_reference="SOME_OTHER_UTR")]
    match = match_settlement_to_bank(stl, bank_lines)
    assert match is None


def test_duplicate_detection_is_insensitive_to_input_order():
    lines_forward = [
        BankStatementLine(id=1, amount=Decimal("500"), description="", value_date=NOW, utr_reference="U1"),
        BankStatementLine(id=2, amount=Decimal("500"), description="", value_date=NOW, utr_reference="U1"),
    ]
    lines_reversed = list(reversed(lines_forward))
    # Regardless of input order, exactly one of the pair should be flagged —
    # specifically the one with the higher id, since detect_duplicate_bank_lines
    # sorts by id internally before comparing.
    assert detect_duplicate_bank_lines(lines_forward) == [2]
    assert detect_duplicate_bank_lines(lines_reversed) == [2]


def test_empty_input_lists_do_not_crash_reconcile():
    run = reconcile([], [], [], now=NOW)
    assert run.results == []
    assert run.orphan_bank_line_ids == []
    assert run.duplicate_bank_line_ids == []


def test_reconcile_ignores_refunded_and_failed_transactions_entirely():
    transactions = [
        _txn(1, "order_1", "500.00", status="refunded"),
        _txn(2, "order_2", "500.00", status="failed"),
    ]
    run = reconcile(transactions, [], [], now=NOW)
    assert run.results == []  # neither should produce a reconciliation result at all


# ---------------------------------------------------------------------------
# Policy gate — adversarial cases
# ---------------------------------------------------------------------------

def test_policy_gate_zero_confidence_never_auto_resolves_regardless_of_amount():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=0, delta_amount=Decimal("0.01"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.PENDING_HUMAN_REVIEW


def test_policy_gate_zero_amount_with_high_confidence_auto_resolves():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=100, delta_amount=Decimal("0.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.AUTO_RESOLVED


# ---------------------------------------------------------------------------
# AI reasoning — malformed input hunting
# ---------------------------------------------------------------------------

def test_reasoning_parser_rejects_confidence_as_string_not_int():
    # A model might return "95" (string) instead of 95 (int) — must be rejected,
    # not silently coerced, since silent coercion could hide a formatting bug.
    bad = '{"hypothesis": "x", "proposed_resolution": "y", "confidence": "95"}'
    try:
        parse_reasoning_response(bad)
        assert False, "expected ReasoningError for string confidence"
    except ReasoningError:
        pass


def test_reasoning_parser_rejects_empty_json_object():
    try:
        parse_reasoning_response("{}")
        assert False, "expected ReasoningError"
    except ReasoningError:
        pass


def test_reasoning_parser_rejects_json_array_instead_of_object():
    try:
        parse_reasoning_response('[{"hypothesis": "x"}]')
        assert False, "expected ReasoningError"
    except ReasoningError:
        pass


def test_reasoning_parser_handles_extra_unexpected_keys_gracefully():
    # Extra keys beyond the required three should not break parsing — only
    # missing required keys should.
    extra = ('{"hypothesis": "x", "proposed_resolution": "y", "confidence": 80, '
             '"unexpected_extra_field": "should be ignored"}')
    result = parse_reasoning_response(extra)
    assert result.is_valid


# ---------------------------------------------------------------------------
# Security — adversarial cases
# ---------------------------------------------------------------------------

def test_api_key_check_rejects_empty_string_provided_when_key_required():
    assert verify_api_key(provided="", expected="realkey") is False


def test_rate_limiter_handles_burst_exactly_at_boundary():
    limiter = RateLimiter(max_requests=5, window_seconds=1)
    now = 1000.0
    results = [limiter.allow("client", now=now) for _ in range(6)]
    assert results == [True, True, True, True, True, False]


def test_reasoning_parser_rejects_boolean_confidence_despite_bool_being_an_int_subclass():
    # Python quirk: isinstance(True, int) is True. A naive isinstance check
    # would let `"confidence": true` sneak through as confidence=1.
    bad = '{"hypothesis": "x", "proposed_resolution": "y", "confidence": true}'
    try:
        parse_reasoning_response(bad)
        assert False, "expected ReasoningError for boolean confidence"
    except ReasoningError:
        pass


def test_orphan_settlement_with_no_matching_transaction_is_flagged_not_dropped():
    # Regression test for a real bug found during QA: a settlement whose
    # order_id has no corresponding transaction anywhere was previously
    # silently dropped, producing zero results instead of a discrepancy.
    now = NOW
    settlements = [_settlement(1, "order_ghost", "100.00", "5.00", "UTR001", settled_at=now)]
    run = reconcile([], settlements, [], now=now)
    assert len(run.results) == 1
    assert run.results[0].settlement_id == 1
    assert run.results[0].status == ReconciliationStatus.UNMATCHED
    assert run.orphan_settlement_ids == [1]


def test_reconcile_survives_mixed_naive_and_timezone_aware_datetimes():
    # Regression test for a CRITICAL bug: SQLite returns naive datetimes,
    # Postgres (the actual production deploy target) returns timezone-aware
    # ones for DateTime(timezone=True) columns. Before the time_utils.py
    # fix, this exact scenario crashed with "can't subtract offset-naive
    # and offset-aware datetimes" the moment this app hit a real database.
    from datetime import timezone as tz
    aware_now = datetime(2026, 8, 27, 12, 0, 0, tzinfo=tz.utc)
    naive_created_at = datetime(2026, 8, 20, 10, 0, 0)  # simulates a SQLite-read value

    txn = Transaction(
        id=1, order_id="order_1", amount=Decimal("1000.00"),
        currency="INR", status="captured", created_at=naive_created_at,
    )
    # Should not raise, and should correctly classify as UNMATCHED since
    # it's well past the settlement grace period with no settlement.
    run = reconcile([txn], [], [], now=aware_now)
    assert len(run.results) == 1
    assert run.results[0].status == ReconciliationStatus.UNMATCHED


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
