from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from app.database import Base


class ReconciliationResultRecord(Base):
    __tablename__ = "reconciliation_results"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True, index=True)
    settlement_id = Column(Integer, ForeignKey("settlements.id"), nullable=True, index=True)
    bank_line_id = Column(Integer, ForeignKey("bank_statement_lines.id"), nullable=True, index=True)

    match_type = Column(String, nullable=False)   # exact|fuzzy|unmatched|duplicate|pending
    status = Column(String, nullable=False, index=True)
    confidence = Column(Integer, nullable=False, default=0)
    delta_amount = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)

    # Populated in Phase 2 by the AI reasoning layer — nullable here so
    # Phase 1 can insert rows before Claude ever looks at them.
    ai_proposed_resolution = Column(Text, nullable=True)
    ai_confidence = Column(Integer, nullable=True)
    reviewer_name = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
