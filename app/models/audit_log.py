from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base


class AuditLogRecord(Base):
    """Append-only. No router in this codebase exposes an update or delete
    for this table — that is a deliberate design decision, not an oversight.
    If you find yourself wanting to edit an audit_log row, write a new row
    that supersedes it instead; never mutate history.
    """
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    # event_type values used across phases:
    #   "match_attempt"   — written by the Phase 1 matching engine
    #   "ai_proposal"     — written by the Phase 2 Claude reasoning layer
    #   "human_decision"  — written when a reviewer approves/rejects
    #   "system_error"    — written on API/Claude failures (fail-safe logging)
    payload_json = Column(Text, nullable=False)   # JSON-encoded snapshot of the event
    reasoning_text = Column(Text, nullable=True)  # human-readable explanation, if any
    decided_by = Column(String, nullable=False, default="system")  # "system" | "claude" | reviewer name
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
