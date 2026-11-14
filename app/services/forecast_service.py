"""
Cash-Flow Forecast Module.

DESIGN PRINCIPLE: this module only ever forecasts from RECONCILED data
(status MATCHED, PARTIAL, or AUTO_RESOLVED/APPROVED) — never from raw,
unverified transactions. Forecasting off unverified numbers would let a
single unresolved discrepancy silently distort a cash position projection
that a finance team might actually act on.

Kept dependency-free like matching_engine.py so it's fully unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from statistics import mean, pstdev
from typing import Optional

from app.services.time_utils import utc_now, to_utc


@dataclass
class SettledRecord:
    """Minimal shape the forecast needs — the API layer maps DB rows to this."""
    amount: Decimal
    transaction_created_at: datetime
    settled_at: datetime


@dataclass
class PendingRecord:
    """A transaction still awaiting settlement."""
    amount: Decimal
    transaction_created_at: datetime


@dataclass
class ForecastDay:
    date: str  # ISO date, e.g. "2026-09-01"
    expected_amount: Decimal
    low_estimate: Decimal
    high_estimate: Decimal


@dataclass
class SettlementLagStats:
    average_days: float
    stdev_days: float
    sample_size: int


@dataclass
class ForecastResult:
    lag_stats: SettlementLagStats
    daily_forecast: list[ForecastDay] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)


def compute_settlement_lag_stats(settled_records: list[SettledRecord]) -> SettlementLagStats:
    """Historical average (and spread) of days between a transaction being
    created and its settlement landing — the basis for projecting when
    currently-pending money will actually arrive.
    """
    if not settled_records:
        return SettlementLagStats(average_days=0.0, stdev_days=0.0, sample_size=0)

    lags = [
        (to_utc(r.settled_at) - to_utc(r.transaction_created_at)).total_seconds() / 86400.0
        for r in settled_records
    ]
    avg = mean(lags)
    spread = pstdev(lags) if len(lags) > 1 else 0.0
    return SettlementLagStats(average_days=avg, stdev_days=spread, sample_size=len(lags))


def detect_settlement_anomalies(
    settled_records: list[SettledRecord],
    lag_stats: SettlementLagStats,
    anomaly_threshold_stdevs: float = 2.0,
) -> list[str]:
    """Flags recent settlements that took meaningfully longer than the
    historical average — an early warning signal, not a hard discrepancy.
    """
    if lag_stats.sample_size < 3 or lag_stats.stdev_days == 0:
        return []  # not enough history to call anything anomalous yet

    anomalies = []
    threshold = lag_stats.average_days + (anomaly_threshold_stdevs * lag_stats.stdev_days)

    for r in settled_records:
        lag_days = (to_utc(r.settled_at) - to_utc(r.transaction_created_at)).total_seconds() / 86400.0
        if lag_days > threshold:
            anomalies.append(
                f"Settlement for a {r.amount} transaction took {lag_days:.1f} days "
                f"— well above the {lag_stats.average_days:.1f}-day historical average."
            )

    return anomalies


def forecast_cash_position(
    settled_records: list[SettledRecord],
    pending_records: list[PendingRecord],
    horizon_days: int = 7,
    now: Optional[datetime] = None,
) -> ForecastResult:
    """Projects cumulative verified cash availability for each of the next
    `horizon_days`. The low / expected / high figures respectively assume
    the latest, average, and earliest plausible settlement date, so every
    row is a real confidence band: low <= expected <= high.
    """
    now = to_utc(now) if now else utc_now()
    lag_stats = compute_settlement_lag_stats(settled_records)
    anomalies = detect_settlement_anomalies(settled_records, lag_stats)

    avg_lag = lag_stats.average_days if lag_stats.sample_size > 0 else 3.0  # sane default: T+3
    spread = lag_stats.stdev_days if lag_stats.sample_size > 1 else 1.0
    projected_records: list[tuple[datetime, datetime, datetime, Decimal]] = []

    for record in pending_records:
        created_at = to_utc(record.transaction_created_at)
        expected_settle_date = created_at + timedelta(days=avg_lag)
        earliest_settle_date = created_at + timedelta(days=max(0.0, avg_lag - spread))
        latest_settle_date = created_at + timedelta(days=avg_lag + spread)

        # An overdue item is a discrepancy to investigate, not a new forecast
        # entry. This keeps the horizon forward-looking and matches the API's
        # existing behaviour.
        expected_days_out = (expected_settle_date.date() - now.date()).days
        if 0 <= expected_days_out < horizon_days:
            projected_records.append(
                (earliest_settle_date, expected_settle_date, latest_settle_date, record.amount)
            )

    daily_forecast = []
    for days_out in range(horizon_days):
        forecast_date = now.date() + timedelta(days=days_out)
        low = sum(
            (amount for _, _, latest, amount in projected_records if latest.date() <= forecast_date),
            Decimal("0.00"),
        )
        expected = sum(
            (amount for _, expected_date, _, amount in projected_records if expected_date.date() <= forecast_date),
            Decimal("0.00"),
        )
        high = sum(
            (amount for earliest, _, _, amount in projected_records if earliest.date() <= forecast_date),
            Decimal("0.00"),
        )
        daily_forecast.append(
            ForecastDay(
                date=forecast_date.isoformat(),
                expected_amount=expected,
                low_estimate=low,
                high_estimate=high,
            )
        )

    return ForecastResult(lag_stats=lag_stats, daily_forecast=daily_forecast, anomalies=anomalies)
