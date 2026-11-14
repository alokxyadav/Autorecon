import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ai_reasoning_service import (
    get_ai_explanation, parse_reasoning_response, build_reasoning_prompt,
    ReasoningError,
)

SAMPLE_CONTEXT = {
    "order_id": "order_00042",
    "transaction_amount": "500.00",
    "transaction_created_at": "2026-08-20T10:00:00",
    "settlement_amount": "483.00",
    "settlement_fees": "10.00",
    "settlement_utr": "UTR000042",
    "settlement_settled_at": "2026-08-22T09:00:00",
    "bank_line_amount": None,
    "bank_line_description": None,
    "bank_line_value_date": None,
    "delta_amount": "7.00",
    "match_type": "unmatched",
    "notes": "Settlement differs from expected net by 7.00.",
}

VALID_RESPONSE = (
    '{"hypothesis": "The settlement fee appears higher than the standard '
    'rate, likely an additional processing surcharge.", '
    '"proposed_resolution": "Verify the fee schedule for this payment '
    'method with Razorpay and adjust the expected fee rate if confirmed.", '
    '"confidence": 72}'
)


def _no_sleep(seconds):
    pass  # test double — verifies backoff logic without real delays


def _fake_complete_fn(response_text):
    def fn(system_prompt, user_prompt):
        return response_text
    return fn


def test_parses_clean_valid_response():
    result = parse_reasoning_response(VALID_RESPONSE)
    assert result.is_valid
    assert result.confidence == 72
    assert "surcharge" in result.hypothesis


def test_parses_response_wrapped_in_markdown_fences():
    fenced = "```json\n" + VALID_RESPONSE + "\n```"
    result = parse_reasoning_response(fenced)
    assert result.is_valid
    assert result.confidence == 72


def test_rejects_response_missing_required_keys():
    bad = '{"hypothesis": "something", "confidence": 80}'
    try:
        parse_reasoning_response(bad)
        assert False, "expected ReasoningError"
    except ReasoningError:
        pass


def test_rejects_non_json_response():
    try:
        parse_reasoning_response("I think this is probably a fee issue.")
        assert False, "expected ReasoningError"
    except ReasoningError:
        pass


def test_rejects_confidence_out_of_range():
    bad = '{"hypothesis": "x", "proposed_resolution": "y", "confidence": 150}'
    try:
        parse_reasoning_response(bad)
        assert False, "expected ReasoningError"
    except ReasoningError:
        pass


def test_get_ai_explanation_succeeds_on_first_try_with_good_response():
    explanation = get_ai_explanation(SAMPLE_CONTEXT, _fake_complete_fn(VALID_RESPONSE))
    assert explanation.is_valid
    assert explanation.confidence == 72


def test_get_ai_explanation_retries_then_succeeds():
    calls = {"count": 0}

    def flaky_fn(system_prompt, user_prompt):
        calls["count"] += 1
        if calls["count"] == 1:
            return "not json at all"
        return VALID_RESPONSE

    explanation = get_ai_explanation(SAMPLE_CONTEXT, flaky_fn, max_retries=2, sleep_fn=_no_sleep)
    assert explanation.is_valid
    assert calls["count"] == 2


def test_get_ai_explanation_falls_back_safely_after_exhausting_retries():
    def always_broken_fn(system_prompt, user_prompt):
        return "garbage, not json"

    explanation = get_ai_explanation(SAMPLE_CONTEXT, always_broken_fn, max_retries=2, sleep_fn=_no_sleep)
    assert explanation.is_valid is False
    assert explanation.confidence == 0
    assert explanation.raw_error is not None


def test_get_ai_explanation_falls_back_when_api_call_raises():
    def raising_fn(system_prompt, user_prompt):
        raise ConnectionError("simulated network failure")

    explanation = get_ai_explanation(SAMPLE_CONTEXT, raising_fn, max_retries=1, sleep_fn=_no_sleep)
    assert explanation.is_valid is False
    assert "simulated network failure" in explanation.raw_error


def test_build_reasoning_prompt_handles_missing_settlement_and_bank_line():
    context = dict(SAMPLE_CONTEXT)
    context["settlement_amount"] = None
    prompt = build_reasoning_prompt(context)
    assert "Settlement: none found" in prompt
    assert "Bank statement line: none found" in prompt


def test_get_ai_explanation_never_raises_even_on_unexpected_exception():
    def weird_fn(system_prompt, user_prompt):
        raise RuntimeError("something totally unexpected")

    # Must not propagate — the caller (API endpoint) should never crash
    # because the AI layer misbehaved.
    explanation = get_ai_explanation(SAMPLE_CONTEXT, weird_fn, max_retries=0)
    assert explanation.is_valid is False


def test_backoff_delays_grow_exponentially_between_retries():
    delays_recorded = []

    def recording_sleep(seconds):
        delays_recorded.append(seconds)

    def always_broken_fn(system_prompt, user_prompt):
        return "not json"

    get_ai_explanation(
        SAMPLE_CONTEXT, always_broken_fn, max_retries=3,
        sleep_fn=recording_sleep, base_delay_seconds=1.0,
    )
    # 3 retries means 3 failures before the final (4th) attempt also fails —
    # backoff should be called before each retry, but NOT after the final
    # attempt (no point sleeping after we've already given up).
    assert delays_recorded == [1.0, 2.0, 4.0]


def test_no_backoff_sleep_called_when_first_attempt_succeeds():
    delays_recorded = []

    def recording_sleep(seconds):
        delays_recorded.append(seconds)

    get_ai_explanation(
        SAMPLE_CONTEXT, _fake_complete_fn(VALID_RESPONSE),
        sleep_fn=recording_sleep,
    )
    assert delays_recorded == []


def test_no_backoff_sleep_after_the_final_failed_attempt():
    delays_recorded = []

    def recording_sleep(seconds):
        delays_recorded.append(seconds)

    def always_broken_fn(system_prompt, user_prompt):
        return "not json"

    get_ai_explanation(
        SAMPLE_CONTEXT, always_broken_fn, max_retries=1,
        sleep_fn=recording_sleep, base_delay_seconds=0.5,
    )
    # max_retries=1 means 2 total attempts — exactly one sleep in between,
    # none after the second (final) attempt fails.
    assert delays_recorded == [0.5]


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
