import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.security import verify_api_key, RateLimiter


# ---------------------------------------------------------------------------
# API key verification
# ---------------------------------------------------------------------------

def test_auth_disabled_when_no_expected_key_set():
    assert verify_api_key(provided=None, expected=None) is True
    assert verify_api_key(provided="anything", expected="") is True


def test_rejects_missing_key_when_auth_enabled():
    assert verify_api_key(provided=None, expected="secret123") is False


def test_rejects_wrong_key():
    assert verify_api_key(provided="wrong", expected="secret123") is False


def test_accepts_correct_key():
    assert verify_api_key(provided="secret123", expected="secret123") is True


def test_rejects_key_that_is_a_prefix_of_the_real_one():
    # Guards against a naive `expected.startswith(provided)` implementation bug.
    assert verify_api_key(provided="secret", expected="secret123") is False


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

def test_allows_requests_under_the_limit():
    limiter = RateLimiter(max_requests=3, window_seconds=60)
    now = 1000.0
    assert limiter.allow("client_a", now=now) is True
    assert limiter.allow("client_a", now=now) is True
    assert limiter.allow("client_a", now=now) is True


def test_blocks_requests_over_the_limit_within_the_same_window():
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    now = 1000.0
    assert limiter.allow("client_a", now=now) is True
    assert limiter.allow("client_a", now=now) is True
    assert limiter.allow("client_a", now=now) is False  # 3rd request, over limit


def test_resets_after_window_elapses():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    assert limiter.allow("client_a", now=1000.0) is True
    assert limiter.allow("client_a", now=1005.0) is False  # still within window
    assert limiter.allow("client_a", now=1061.0) is True   # window has elapsed


def test_different_keys_are_tracked_independently():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    now = 1000.0
    assert limiter.allow("client_a", now=now) is True
    assert limiter.allow("client_b", now=now) is True  # separate client, separate budget
    assert limiter.allow("client_a", now=now) is False  # client_a is now over limit


def test_reset_clears_all_tracked_state():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    limiter.allow("client_a", now=1000.0)
    limiter.reset()
    assert limiter.allow("client_a", now=1000.0) is True  # budget restored


def test_stale_entries_are_cleaned_up_to_bound_memory():
    # Simulate many distinct short-lived clients (e.g. rotating IPs) over a
    # long period — without cleanup, _windows grows forever.
    limiter = RateLimiter(max_requests=5, window_seconds=1.0)
    limiter._cleanup_interval = 10  # lower threshold so the test doesn't need 100+ calls

    base_time = 1000.0
    for i in range(20):
        # Each call is both a new distinct client AND far enough apart in
        # time that earlier windows have definitely expired.
        limiter.allow(f"client_{i}", now=base_time + i * 2.0)

    # After cleanup has run at least once, old expired windows should have
    # been evicted — the dict should NOT contain all 20 clients forever.
    assert len(limiter._windows) < 20


def test_thread_safety_under_concurrent_access_from_same_key():
    import threading as th

    limiter = RateLimiter(max_requests=100, window_seconds=60)
    successes = []
    lock = th.Lock()

    def worker():
        result = limiter.allow("shared_client", now=1000.0)
        with lock:
            successes.append(result)

    threads = [th.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Exactly 100 requests against a limit of 100 — every single one should
    # succeed with no race condition either double-counting or under-counting.
    assert sum(successes) == 100
    assert len(successes) == 100


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
