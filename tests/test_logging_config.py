import sys
import os
import io
import json
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.logging_config import JSONLogFormatter, request_id_var


def _make_logger_with_capture():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONLogFormatter())
    logger = logging.getLogger(f"test_logger_{id(stream)}")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def test_log_output_is_valid_json():
    logger, stream = _make_logger_with_capture()
    logger.info("hello world")
    output = stream.getvalue().strip()
    parsed = json.loads(output)  # raises if not valid JSON
    assert parsed["message"] == "hello world"


def test_log_includes_required_fields():
    logger, stream = _make_logger_with_capture()
    logger.warning("something happened")
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["level"] == "WARNING"
    assert "timestamp" in parsed
    assert "logger" in parsed
    assert "request_id" in parsed


def test_request_id_defaults_to_dash_when_unset():
    logger, stream = _make_logger_with_capture()
    logger.info("no request context")
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["request_id"] == "-"


def test_request_id_is_included_when_set_via_contextvar():
    logger, stream = _make_logger_with_capture()
    token = request_id_var.set("req-abc-123")
    try:
        logger.info("inside a request")
    finally:
        request_id_var.reset(token)
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["request_id"] == "req-abc-123"


def test_exception_info_is_included_when_logged():
    logger, stream = _make_logger_with_capture()
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("something failed")
    parsed = json.loads(stream.getvalue().strip())
    assert "exception" in parsed
    assert "ValueError: boom" in parsed["exception"]


def test_timestamp_is_iso_format_and_utc():
    logger, stream = _make_logger_with_capture()
    logger.info("check timestamp")
    parsed = json.loads(stream.getvalue().strip())
    # Should parse cleanly as an ISO timestamp and carry UTC offset info.
    from datetime import datetime
    dt = datetime.fromisoformat(parsed["timestamp"])
    assert dt.tzinfo is not None


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
