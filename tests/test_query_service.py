import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.query_utils import extract_order_id as _extract_order_id


def test_extracts_order_id_with_underscore_format():
    assert _extract_order_id("why didn't order_00042 reconcile?") == "order_00042"


def test_extracts_order_id_with_space_format():
    assert _extract_order_id("what happened to order 42") == "order_00042"


def test_extracts_order_id_case_insensitive():
    assert _extract_order_id("Order 42 status?") == "order_00042"


def test_returns_none_when_no_order_id_present():
    assert _extract_order_id("what needs review today?") is None


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
