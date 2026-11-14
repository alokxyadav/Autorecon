from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.forecast_bridge_service import build_forecast

router = APIRouter(prefix="", tags=["forecast"])


@router.get("/forecast")
def get_forecast(
    horizon_days: int = Query(default=7, ge=1, le=30),
    db: Session = Depends(get_db),
):
    """Cash-flow forecast built ONLY from reconciled (verified) data — see
    forecast_bridge_service.VERIFIED_STATUSES. Never includes raw unverified
    transactions, so a discrepancy elsewhere in the pipeline can't silently
    distort a number this endpoint returns.
    """
    return build_forecast(db, horizon_days=horizon_days)
