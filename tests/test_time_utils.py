import sys
import os
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.time_utils import to_utc, utc_now


def test_utc_now_is_always_timezone_aware():
    assert utc_now().tzinfo is not None


def test_to_utc_adds_timezone_to_naive_datetime():
    naive = datetime(2026, 8, 27, 12, 0, 0)
    result = to_utc(naive)
    assert result.tzinfo is not None
    assert result.tzinfo == timezone.utc


def test_to_utc_converts_non_utc_aware_datetime_to_utc():
    ist = timezone(timedelta(hours=5, minutes=30))
    aware_ist = datetime(2026, 8, 27, 17, 30, 0, tzinfo=ist)
    result = to_utc(aware_ist)
    assert result.tzinfo == timezone.utc
    assert result.hour == 12  # 17:30 IST == 12:00 UTC


def test_naive_and_aware_datetimes_can_be_subtracted_after_normalization():
    # This is the exact regression this module exists to prevent: without
    # to_utc(), this subtraction raises TypeError.
    naive = datetime(2026, 8, 27, 10, 0, 0)
    aware = datetime(2026, 8, 27, 12, 0, 0, tzinfo=timezone.utc)
    diff = to_utc(aware) - to_utc(naive)
    assert diff.total_seconds() == 7200  # 2 hours


def test_to_utc_is_idempotent():
    dt = utc_now()
    assert to_utc(to_utc(dt)) == to_utc(dt)


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
