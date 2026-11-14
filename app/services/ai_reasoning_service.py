"""
AI Reasoning Layer.

This module never decides anything about money — it only produces a
*hypothesis*, a *proposed resolution*, and a *confidence score* for
discrepancies the deterministic matching engine couldn't resolve. The
policy_gate module (see policy_gate.py) is the only thing that acts on this
output.

DESIGN NOTE ON TESTABILITY:
`get_ai_explanation()` takes a `complete_fn: Callable[[str, str], str]`
argument rather than importing the `anthropic` SDK directly. This means:
  - Unit tests can pass a fake function and verify parsing/retry/fallback
    behavior with zero network calls and no dependency on the anthropic
    package being installed.
  - Only `make_claude_complete_fn()` at the bottom of this file actually
    imports `anthropic` — and it does so lazily, inside the function body —
    so importing this module never fails just because the SDK isn't present.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional


SYSTEM_PROMPT = """You are a financial reconciliation assistant helping a human finance team understand payment discrepancies.

You will be given details of a transaction, its settlement (if any), and the closest candidate bank statement line (if any), along with a computed amount delta.

Your job:
1. Form the single most likely hypothesis for why this didn't cleanly match (e.g. fee rounding, a duplicate webhook, a delayed or missing settlement, a partial refund, a currency conversion difference, or genuinely missing money).
2. Propose one concrete, specific resolution a finance team member could take.
3. Give a confidence score from 0-100 for your OWN hypothesis — be conservative. Only use 90+ if the evidence is genuinely unambiguous.

Respond with ONLY a JSON object, no markdown code fences, no prose before or after, exactly matching this shape:
{"hypothesis": "<one or two sentences>", "proposed_resolution": "<one or two sentences, concrete and actionable>", "confidence": <integer 0-100>}
"""


class ReasoningError(Exception):
    """Raised when the model's response can't be parsed into a valid proposal."""


@dataclass
class AIExplanation:
    hypothesis: Optional[str]
    proposed_resolution: Optional[str]
    confidence: int
    is_valid: bool
    raw_error: Optional[str] = None


def build_reasoning_prompt(item_context: dict) -> str:
    """`item_context` is a plain dict assembled by the caller (see
    ai_analysis_service.py) — kept as a dict rather than a DB row so this
    function has no dependency on SQLAlchemy and is trivially testable.
    """
    lines = [
        f"Transaction: order_id={item_context.get('order_id')}, "
        f"amount={item_context.get('transaction_amount')}, "
        f"created_at={item_context.get('transaction_created_at')}",
    ]
    if item_context.get("settlement_amount") is not None:
        lines.append(
            f"Settlement: amount={item_context.get('settlement_amount')}, "
            f"fees={item_context.get('settlement_fees')}, "
            f"utr={item_context.get('settlement_utr')}, "
            f"settled_at={item_context.get('settlement_settled_at')}"
        )
    else:
        lines.append("Settlement: none found for this transaction.")

    if item_context.get("bank_line_amount") is not None:
        lines.append(
            f"Closest bank statement line: amount={item_context.get('bank_line_amount')}, "
            f"description={item_context.get('bank_line_description')}, "
            f"value_date={item_context.get('bank_line_value_date')}"
        )
    else:
        lines.append("Bank statement line: none found.")

    lines.append(f"Computed delta: {item_context.get('delta_amount')}")
    lines.append(f"Match type from deterministic engine: {item_context.get('match_type')}")
    lines.append(f"System notes: {item_context.get('notes')}")

    return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_reasoning_response(raw_text: str) -> AIExplanation:
    cleaned = _strip_code_fences(raw_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ReasoningError(f"Response was not valid JSON: {e}") from e

    if not isinstance(data, dict):
        raise ReasoningError("Response JSON was not an object.")

    required_keys = {"hypothesis", "proposed_resolution", "confidence"}
    missing = required_keys - data.keys()
    if missing:
        raise ReasoningError(f"Response missing required keys: {missing}")

    confidence = data["confidence"]
    # isinstance(True, int) is True in Python — explicitly exclude bool so a
    # malformed `"confidence": true` from the model can't sneak through as 1.
    if isinstance(confidence, bool) or not isinstance(confidence, int) or not (0 <= confidence <= 100):
        raise ReasoningError(f"Confidence must be an integer 0-100, got: {confidence!r}")

    if not isinstance(data["hypothesis"], str) or not isinstance(data["proposed_resolution"], str):
        raise ReasoningError("hypothesis and proposed_resolution must be strings.")

    return AIExplanation(
        hypothesis=data["hypothesis"],
        proposed_resolution=data["proposed_resolution"],
        confidence=confidence,
        is_valid=True,
    )


def get_ai_explanation(
    item_context: dict,
    complete_fn: Callable[[str, str], str],
    max_retries: int = 2,
    sleep_fn: Callable[[float], None] = time.sleep,
    base_delay_seconds: float = 0.5,
) -> AIExplanation:
    """Calls `complete_fn(system_prompt, user_prompt) -> raw_text`, retries
    with exponential backoff on failure, and falls back to a safe "needs
    manual review" result if every attempt fails — this function must never
    raise. A failure here should always degrade to "a human looks at it",
    never crash the request or silently invent a confident-looking answer.

    `sleep_fn` is injectable so tests can verify backoff timing without
    actually waiting — see tests/test_ai_reasoning_service.py.
    """
    user_prompt = build_reasoning_prompt(item_context)
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            raw = complete_fn(SYSTEM_PROMPT, user_prompt)
        except Exception as e:  # network error, rate limit, timeout, etc.
            last_error = f"API call failed on attempt {attempt + 1}: {e}"
            if attempt < max_retries:
                sleep_fn(base_delay_seconds * (2 ** attempt))
            continue

        try:
            return parse_reasoning_response(raw)
        except ReasoningError as e:
            last_error = f"Parse failure on attempt {attempt + 1}: {e}"
            if attempt < max_retries:
                sleep_fn(base_delay_seconds * (2 ** attempt))
            continue

    return AIExplanation(
        hypothesis=None,
        proposed_resolution=None,
        confidence=0,
        is_valid=False,
        raw_error=last_error or "Unknown failure",
    )


# ---------------------------------------------------------------------------
# Production wiring — only this function touches the real Claude API.
# Deliberately NOT called anywhere in this module's own tests.
# ---------------------------------------------------------------------------

def make_claude_complete_fn(model: str = "claude-sonnet-5") -> Callable[[str, str], str]:
    """Lazily imports `anthropic` so this module can be imported (and its
    pure logic tested) in environments where the SDK isn't installed.
    Reads ANTHROPIC_API_KEY from the environment, same as the SDK default.

    NOTE: model names change over time — verify "claude-sonnet-5" is still
    current at https://docs.claude.com before deploying, or pass a different
    `model` string when calling this function.
    """
    import anthropic  # local import — see module docstring for why

    # timeout: prevents a hung request from blocking a worker indefinitely.
    # max_retries=0: the anthropic SDK has its own built-in retry logic by
    # default (2 retries with backoff) which would silently stack with the
    # retry/backoff loop in get_ai_explanation() above, potentially turning
    # one failed call into a very long multi-minute wait before this
    # function's own fallback ever kicks in. Disabling the SDK's internal
    # retries makes get_ai_explanation() the single source of truth for
    # retry behavior.
    client = anthropic.Anthropic(timeout=30.0, max_retries=0)

    def complete_fn(system_prompt: str, user_prompt: str) -> str:
        response = client.messages.create(
            model=model,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Claude's response content is a list of blocks; we only ever expect
        # a single text block given this prompt design.
        return "".join(block.text for block in response.content if block.type == "text")

    return complete_fn
