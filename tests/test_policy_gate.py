import sys
import os
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.policy_gate import (
    PolicyGateInput, PolicyDecision, evaluate_policy,
)


def test_auto_resolves_when_confidence_high_and_amount_small():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=95, delta_amount=Decimal("50.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.AUTO_RESOLVED


def test_routes_to_human_when_confidence_below_threshold():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=89, delta_amount=Decimal("50.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.PENDING_HUMAN_REVIEW


def test_routes_to_human_when_amount_exceeds_ceiling_even_at_max_confidence():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=100, delta_amount=Decimal("50000.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.PENDING_HUMAN_REVIEW
    assert "exceeds" in result.reason


def test_routes_to_human_when_ai_proposal_is_invalid_regardless_of_confidence():
    # Simulates a parsing failure upstream — confidence might even be garbage-high,
    # but has_valid_proposal=False must always win.
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=100, delta_amount=Decimal("1.00"), has_valid_proposal=False),
    )
    assert result.decision == PolicyDecision.PENDING_HUMAN_REVIEW


def test_boundary_confidence_exactly_at_threshold_auto_resolves():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=90, delta_amount=Decimal("100.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.AUTO_RESOLVED


def test_boundary_amount_exactly_at_ceiling_auto_resolves():
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=95, delta_amount=Decimal("500.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.AUTO_RESOLVED


def test_negative_delta_amount_is_evaluated_by_absolute_value():
    # A "refund overpaid" discrepancy might be represented as negative — the
    # policy gate must judge by magnitude, not sign.
    result = evaluate_policy(
        PolicyGateInput(ai_confidence=95, delta_amount=Decimal("-50000.00"), has_valid_proposal=True),
        confidence_threshold=90, max_amount=Decimal("500.00"),
    )
    assert result.decision == PolicyDecision.PENDING_HUMAN_REVIEW


def test_load_thresholds_falls_back_safely_on_malformed_env_vars():
    # Regression test for a real bug: a malformed AUTO_APPROVE_MAX_AMOUNT
    # env var (e.g. a typo) previously crashed with decimal.InvalidOperation
    # on every single reconciliation/analyze call, instead of falling back
    # to the safe default like AUTO_APPROVE_CONFIDENCE_THRESHOLD already did.
    import os
    from app.services.policy_gate import load_thresholds_from_env, DEFAULT_AUTO_APPROVE_MAX_AMOUNT

    os.environ["AUTO_APPROVE_MAX_AMOUNT"] = "not-a-number"
    try:
        confidence, max_amount = load_thresholds_from_env()
        assert max_amount == DEFAULT_AUTO_APPROVE_MAX_AMOUNT
    finally:
        del os.environ["AUTO_APPROVE_MAX_AMOUNT"]


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
    print(f"\n{passed} passed, {failed} failed out of {len(test_fns)} tests")
    sys.exit(1 if failed else 0)
