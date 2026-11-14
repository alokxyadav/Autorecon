import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.forecast_service import (
    SettledRecord, PendingRecord,
    compute_settlement_lag_stats, detect_settlement_anomalies,
    forecast_cash_position,
)

NOW = datetime(2026, 8, 27, 0, 0, 0)


def test_settlement_lag_stats_computed_correctly():
    records = [
        SettledRecord(Decimal("100"), NOW - timedelta(days=10), NOW - timedelta(days=7)),  # 3 day lag
        SettledRecord(Decimal("200"), NOW - timedelta(days=10), NOW - timedelta(days=7)),  # 3 day lag
        SettledRecord(Decimal("300"), NOW - timedelta(days=10), NOW - timedelta(days=5)),  # 5 day lag
    ]
    stats = compute_settlement_lag_stats(records)
    assert stats.sample_size == 3
    assert abs(stats.average_days - (3 + 3 + 5) / 3) < 0.01


def test_settlement_lag_stats_empty_input():
    stats = compute_settlement_lag_stats([])
    assert stats.sample_size == 0
    assert stats.average_days == 0.0


def test_detects_anomalous_late_settlement():
    # 10 normal 3-day settlements, then one wildly late 20-day settlement.
    records = [
        SettledRecord(Decimal("100"), NOW - timedelta(days=15), NOW - timedelta(days=12))
        for _ in range(10)
    ]
    records.append(
        SettledRecord(Decimal("500"), NOW - timedelta(days=30), NOW - timedelta(days=10))  # 20 day lag
    )
    stats = compute_settlement_lag_stats(records)
    anomalies = detect_settlement_anomalies(records, stats)
    assert len(anomalies) >= 1
    assert "500" in anomalies[0]


def test_no_anomalies_with_insufficient_history():
    records = [SettledRecord(Decimal("100"), NOW - timedelta(days=5), NOW - timedelta(days=2))]
    stats = compute_settlement_lag_stats(records)
    anomalies = detect_settlement_anomalies(records, stats)
    assert anomalies == []


def test_forecast_places_pending_amount_in_correct_future_bucket():
    settled = [
        SettledRecord(Decimal("100"), NOW - timedelta(days=10), NOW - timedelta(days=7))
        for _ in range(5)
    ]  # consistent 3-day lag, zero spread
    pending = [PendingRecord(Decimal("1000.00"), NOW)]  # created today

    result = forecast_cash_position(settled, pending, horizon_days=7, now=NOW)
    assert result.lag_stats.sample_size == 5

    assert result.daily_forecast[-1].expected_amount == Decimal("1000.00")


def test_forecast_uses_default_lag_when_no_history_available():
    pending = [PendingRecord(Decimal("500.00"), NOW)]
    result = forecast_cash_position([], pending, horizon_days=7, now=NOW)
    assert result.lag_stats.sample_size == 0
    assert result.daily_forecast[-1].expected_amount == Decimal("500.00")  # still forecasts, just with a default assumption


def test_forecast_excludes_amounts_landing_outside_horizon():
    settled = [
        SettledRecord(Decimal("100"), NOW - timedelta(days=10), NOW - timedelta(days=7))
        for _ in range(5)
    ]  # 3-day lag
    # This pending transaction was created 20 days ago — expected settlement
    # date is 17 days in the past, well outside a 7-day forward horizon.
    pending = [PendingRecord(Decimal("999.00"), NOW - timedelta(days=20))]

    result = forecast_cash_position(settled, pending, horizon_days=7, now=NOW)
    total_expected = sum(d.expected_amount for d in result.daily_forecast)
    assert total_expected == Decimal("0.00")


def test_forecast_confidence_band_is_ordered():
    settled = [
        SettledRecord(Decimal("100"), NOW - timedelta(days=10), NOW - timedelta(days=7)),
        SettledRecord(Decimal("100"), NOW - timedelta(days=10), NOW - timedelta(days=5)),
    ]
    pending = [PendingRecord(Decimal("500.00"), NOW)]

    result = forecast_cash_position(settled, pending, horizon_days=7, now=NOW)

    assert all(
        day.low_estimate <= day.expected_amount <= day.high_estimate
        for day in result.daily_forecast
    )


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
