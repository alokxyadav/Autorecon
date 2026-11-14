"""
Policy Gate — the single most important file in this project.

This is what stands between an LLM's opinion and an actual change to a
financial record. Claude may propose a resolution and a confidence score;
this module is the ONLY thing that decides whether that proposal is applied
automatically or sent to a human. It has no knowledge of Claude, no network
calls, and no side effects — pure input -> decision, so it can be tested
exhaustively and reasoned about without any mocking.
"""

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum


def _env_decimal(name: str, default: str) -> Decimal:
    raw = os.getenv(name, default)
    try:
        return Decimal(raw)
    except InvalidOperation:
        # A malformed env var must never crash every reconciliation/analyze
        # call — fall back to the safe default and let the rest of the
        # system keep working. (This mirrors _env_int's existing try/except
        # below — this function previously lacked one, a real bug found
        # during a dedicated QA pass.)
        return Decimal(default)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


DEFAULT_AUTO_APPROVE_CONFIDENCE_THRESHOLD = 90
DEFAULT_AUTO_APPROVE_MAX_AMOUNT = Decimal("500.00")


class PolicyDecision(str, Enum):
    AUTO_RESOLVED = "auto_resolved"
    PENDING_HUMAN_REVIEW = "pending_human_review"


@dataclass
class PolicyGateInput:
    ai_confidence: int          # 0-100, from the AI reasoning layer
    delta_amount: Decimal       # absolute rupee value at stake
    has_valid_proposal: bool    # False if AI reasoning failed/parsing failed


@dataclass
class PolicyGateResult:
    decision: PolicyDecision
    reason: str


def load_thresholds_from_env() -> tuple[int, Decimal]:
    """Reads thresholds from environment variables (see .env.example),
    falling back to safe defaults. Called once by the router/service layer;
    `evaluate_policy` itself stays pure and takes thresholds as arguments so
    tests never need to touch environment variables.
    """
    confidence = _env_int("AUTO_APPROVE_CONFIDENCE_THRESHOLD", DEFAULT_AUTO_APPROVE_CONFIDENCE_THRESHOLD)
    max_amount = _env_decimal("AUTO_APPROVE_MAX_AMOUNT", str(DEFAULT_AUTO_APPROVE_MAX_AMOUNT))
    return confidence, max_amount


def evaluate_policy(
    gate_input: PolicyGateInput,
    confidence_threshold: int = DEFAULT_AUTO_APPROVE_CONFIDENCE_THRESHOLD,
    max_amount: Decimal = DEFAULT_AUTO_APPROVE_MAX_AMOUNT,
) -> PolicyGateResult:
    """The only function that may decide AUTO_RESOLVED. Every branch that
    returns PENDING_HUMAN_REVIEW is intentional and safe-by-default — when
    in doubt, this function always routes to a human.
    """
    if not gate_input.has_valid_proposal:
        return PolicyGateResult(
            decision=PolicyDecision.PENDING_HUMAN_REVIEW,
            reason="AI reasoning did not produce a valid proposal — routing to human by default.",
        )

    if gate_input.ai_confidence < confidence_threshold:
        return PolicyGateResult(
            decision=PolicyDecision.PENDING_HUMAN_REVIEW,
            reason=(
                f"AI confidence {gate_input.ai_confidence} is below the "
                f"auto-approve threshold of {confidence_threshold}."
            ),
        )

    if abs(gate_input.delta_amount) > max_amount:
        return PolicyGateResult(
            decision=PolicyDecision.PENDING_HUMAN_REVIEW,
            reason=(
                f"Amount at stake ({gate_input.delta_amount}) exceeds the "
                f"auto-approve ceiling of {max_amount}, regardless of confidence."
            ),
        )

    return PolicyGateResult(
        decision=PolicyDecision.AUTO_RESOLVED,
        reason=(
            f"AI confidence {gate_input.ai_confidence} >= {confidence_threshold} "
            f"and amount {gate_input.delta_amount} <= {max_amount}."
        ),
    )
