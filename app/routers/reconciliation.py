from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.reconciliation_result import ReconciliationResultRecord
from app.schemas import ReconciliationResultOut, RunReconciliationResponse
from app.services.reconciliation_service import run_reconciliation
from app.services.data_generator import generate_demo_dataset
from app.services.ai_analysis_service import analyze_unresolved_items, record_human_decision
from app.services.ai_reasoning_service import make_claude_complete_fn
from app.services.query_service import answer_query
from app.services.export_service import reconciliation_results_to_csv

router = APIRouter(prefix="", tags=["reconciliation"])


class ReviewDecisionRequest(BaseModel):
    # min_length=1 rejects an empty payload, but "   " (whitespace-only)
    # would still pass a naive length check — the validator below catches
    # that too, since a name of pure whitespace is exactly as useless as
    # an empty string in the audit trail.
    reviewer_name: str = Field(..., min_length=1, max_length=100)

    @field_validator("reviewer_name")
    @classmethod
    def reviewer_name_must_not_be_blank_after_stripping(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("reviewer_name cannot be blank or whitespace-only")
        return stripped


class QueryRequest(BaseModel):
    # max_length bounds how much text gets sent to the Claude API per
    # request — both a cost control and a defense against pathologically
    # large payloads being used to run up API usage.
    question: str = Field(..., min_length=1, max_length=500)


class QueryResponse(BaseModel):
    answer: str
    grounded_in: list[int]


def _get_claude_complete_fn():
    """Constructs the real Claude completion function on demand, inside the
    request handler rather than at import time — so the app can still start
    up and serve non-AI endpoints even if ANTHROPIC_API_KEY isn't set yet,
    and fails with a clear error only when an AI endpoint is actually hit.
    """
    try:
        return make_claude_complete_fn()
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "AI reasoning is unavailable — check that the 'anthropic' package "
                f"is installed and ANTHROPIC_API_KEY is set. ({e})"
            ),
        )


@router.post("/reconcile/run", response_model=RunReconciliationResponse)
def trigger_reconciliation(db: Session = Depends(get_db)):
    """Runs the deterministic matching engine over all current data and
    persists results + audit log entries. Safe to call repeatedly — each
    run fully replaces the previous reconciliation_results snapshot.
    """
    summary, results_created = run_reconciliation(db)
    return RunReconciliationResponse(summary=summary, results_created=results_created)


@router.post("/demo/seed")
def seed_demo_data(
    num_transactions: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """Convenience endpoint for local/demo use: wipes and repopulates source
    tables with a fresh synthetic dataset containing known, deliberately
    injected discrepancies. Not intended for production use.

    Bounded to 5000 to prevent a client requesting an unbounded amount of
    data generation — without this, an unauthenticated or careless caller
    could request a number large enough to exhaust memory or hang the
    request for an extended period (a real, if unglamorous, DoS vector on
    an endpoint that was otherwise wide open).
    """
    summary = generate_demo_dataset(db, num_transactions=num_transactions)
    return {"seeded": True, "details": summary}


@router.get("/reconciliation/results", response_model=list[ReconciliationResultOut])
def list_results(
    response: Response,
    status: Optional[str] = Query(default=None, description="Filter by status, e.g. 'unmatched'"),
    match_type: Optional[str] = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    q = db.query(ReconciliationResultRecord)
    if status:
        q = q.filter(ReconciliationResultRecord.status == status)
    if match_type:
        q = q.filter(ReconciliationResultRecord.match_type == match_type)

    # Total count of matching rows BEFORE pagination is applied — without
    # this, a frontend has no way to render "page 1 of N" or know whether
    # more results exist beyond the current page. Exposed as a response
    # header rather than changing the response body shape, so this doesn't
    # break any existing caller expecting a plain array back.
    total_count = q.count()
    response.headers["X-Total-Count"] = str(total_count)

    q = q.order_by(ReconciliationResultRecord.delta_amount.desc())
    return q.offset(offset).limit(limit).all()


def _result_row_to_dict(row: ReconciliationResultRecord) -> dict:
    return {
        "id": row.id, "transaction_id": row.transaction_id,
        "settlement_id": row.settlement_id, "bank_line_id": row.bank_line_id,
        "match_type": row.match_type, "status": row.status,
        "confidence": row.confidence, "delta_amount": row.delta_amount,
        "notes": row.notes, "ai_proposed_resolution": row.ai_proposed_resolution,
        "ai_confidence": row.ai_confidence, "reviewer_name": row.reviewer_name,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


@router.get("/reconciliation/results/export")
def export_results_csv(
    status: Optional[str] = Query(default=None),
    match_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Exports reconciliation results as a downloadable CSV file — a real
    requirement for any finance team using this in practice, since they need
    to hand numbers to auditors, paste them into an existing spreadsheet, or
    attach them to a month-end close email, not just view them in a browser
    tab. Applies the same status/match_type filters as the list endpoint,
    but with no page limit — this is meant to export everything matching
    the filter, not one page of it.
    """
    q = db.query(ReconciliationResultRecord)
    if status:
        q = q.filter(ReconciliationResultRecord.status == status)
    if match_type:
        q = q.filter(ReconciliationResultRecord.match_type == match_type)
    rows = q.order_by(ReconciliationResultRecord.id.asc()).all()

    csv_text = reconciliation_results_to_csv(_result_row_to_dict(r) for r in rows)
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=reconciliation_results.csv"},
    )


@router.get("/reconciliation/results/{result_id}", response_model=ReconciliationResultOut)
def get_result(result_id: int, db: Session = Depends(get_db)):
    result = db.query(ReconciliationResultRecord).filter(
        ReconciliationResultRecord.id == result_id
    ).first()
    if result is None:
        raise HTTPException(status_code=404, detail="Reconciliation result not found")
    return result


@router.post("/reconciliation/analyze")
def analyze_items(reanalyze: bool = False, db: Session = Depends(get_db)):
    """Runs the Claude reasoning layer + policy gate over every currently
    UNMATCHED/PARTIAL reconciliation result. By default, skips items that
    already have an AI proposal (pass reanalyze=true to force a re-run,
    e.g. after changing policy thresholds).
    """
    complete_fn = _get_claude_complete_fn()
    return analyze_unresolved_items(db, complete_fn, reanalyze=reanalyze)


@router.post("/reconciliation/{result_id}/approve", response_model=ReconciliationResultOut)
def approve_result(result_id: int, body: ReviewDecisionRequest, db: Session = Depends(get_db)):
    result = record_human_decision(db, result_id, approve=True, reviewer_name=body.reviewer_name)
    if result is None:
        raise HTTPException(status_code=404, detail="Reconciliation result not found")
    return result


@router.post("/reconciliation/{result_id}/reject", response_model=ReconciliationResultOut)
def reject_result(result_id: int, body: ReviewDecisionRequest, db: Session = Depends(get_db)):
    result = record_human_decision(db, result_id, approve=False, reviewer_name=body.reviewer_name)
    if result is None:
        raise HTTPException(status_code=404, detail="Reconciliation result not found")
    return result


@router.post("/query", response_model=QueryResponse)
def query_reconciliation(body: QueryRequest, db: Session = Depends(get_db)):
    """Natural-language question about the reconciliation state, answered
    strictly from retrieved audit_log entries — never from the model's own
    general knowledge. See query_service.answer_query for the grounding logic.
    """
    complete_fn = _get_claude_complete_fn()
    result = answer_query(db, body.question, complete_fn)
    return QueryResponse(**result)
