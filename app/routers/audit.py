from typing import Optional

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.audit_log import AuditLogRecord
from app.schemas import AuditLogOut
from app.services.export_service import audit_log_to_csv

router = APIRouter(prefix="", tags=["audit"])


@router.get("/audit-log", response_model=list[AuditLogOut])
def list_audit_log(
    response: Response,
    event_type: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Read-only, always. There is no update or delete endpoint for this
    table anywhere in the codebase — that is intentional, not a gap.
    """
    q = db.query(AuditLogRecord)
    if event_type:
        q = q.filter(AuditLogRecord.event_type == event_type)

    response.headers["X-Total-Count"] = str(q.count())

    q = q.order_by(AuditLogRecord.created_at.desc())
    return q.offset(offset).limit(limit).all()


@router.get("/audit-log/export")
def export_audit_log_csv(
    event_type: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Exports the full audit trail as CSV — a real compliance requirement:
    a finance team needs to be able to hand an auditor a complete,
    unfiltered (or filtered-by-type) record of every decision made, not
    just view it a page at a time in a browser.
    """
    q = db.query(AuditLogRecord)
    if event_type:
        q = q.filter(AuditLogRecord.event_type == event_type)
    rows = q.order_by(AuditLogRecord.created_at.asc()).all()

    entries = (
        {
            "id": r.id, "event_type": r.event_type, "decided_by": r.decided_by,
            "reasoning_text": r.reasoning_text, "created_at": r.created_at,
        }
        for r in rows
    )
    csv_text = audit_log_to_csv(entries)
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_log.csv"},
    )
