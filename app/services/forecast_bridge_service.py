from datetime import datetime

from sqlalchemy.orm import Session

from app.models.reconciliation_result import ReconciliationResultRecord
from app.models.transaction import TransactionRecord
from app.models.settlement import SettlementRecord
from app.services.forecast_service import SettledRecord, PendingRecord, forecast_cash_position
from app.services.matching_engine import ReconciliationStatus
from app.services.time_utils import utc_now, to_utc

# Only these statuses count as "verified" for forecasting purposes — never
# forecast off a raw transaction that hasn't been reconciled at all.
VERIFIED_STATUSES = {
    ReconciliationStatus.MATCHED.value,
    ReconciliationStatus.PARTIAL.value,
    ReconciliationStatus.AUTO_RESOLVED.value,
    ReconciliationStatus.APPROVED.value,
}


def build_forecast(db: Session, horizon_days: int = 7, now: datetime | None = None) -> dict:
    now = to_utc(now) if now else utc_now()

    verified_results = db.query(ReconciliationResultRecord).filter(
        ReconciliationResultRecord.status.in_(VERIFIED_STATUSES),
        ReconciliationResultRecord.settlement_id.isnot(None),
    ).all()

    settled_records = []
    for r in verified_results:
        txn = db.get(TransactionRecord, r.transaction_id) if r.transaction_id else None
        settlement = db.get(SettlementRecord, r.settlement_id) if r.settlement_id else None
        if txn and settlement:
            settled_records.append(SettledRecord(
                amount=settlement.amount,
                transaction_created_at=txn.created_at,
                settled_at=settlement.settled_at,
            ))

    pending_results = db.query(ReconciliationResultRecord).filter(
        ReconciliationResultRecord.status == ReconciliationStatus.PENDING_SETTLEMENT.value,
    ).all()

    pending_records = []
    for r in pending_results:
        txn = db.get(TransactionRecord, r.transaction_id) if r.transaction_id else None
        if txn:
            pending_records.append(PendingRecord(
                amount=txn.amount,
                transaction_created_at=txn.created_at,
            ))

    result = forecast_cash_position(settled_records, pending_records, horizon_days=horizon_days, now=now)

    return {
        "lag_stats": {
            "average_days": round(result.lag_stats.average_days, 2),
            "stdev_days": round(result.lag_stats.stdev_days, 2),
            "sample_size": result.lag_stats.sample_size,
        },
        "daily_forecast": [
            {
                "date": d.date,
                "expected_amount": str(d.expected_amount),
                "low_estimate": str(d.low_estimate),
                "high_estimate": str(d.high_estimate),
            }
            for d in result.daily_forecast
        ],
        "anomalies": result.anomalies,
    }
