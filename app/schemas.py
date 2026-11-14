from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_serializer


class ReconciliationResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transaction_id: Optional[int]
    settlement_id: Optional[int]
    bank_line_id: Optional[int]
    match_type: str
    status: str
    confidence: int
    delta_amount: Decimal
    notes: Optional[str]
    ai_proposed_resolution: Optional[str] = None
    ai_confidence: Optional[int] = None
    reviewer_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_serializer("delta_amount")
    def serialize_delta_amount(self, value: Decimal) -> str:
        # Money is always serialized as a string, never a JSON number — a
        # JSON float can silently lose precision on the client, which is
        # never acceptable for a monetary value. Explicit, regardless of
        # whatever pydantic's own default Decimal handling happens to be.
        return str(value)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    payload_json: str
    reasoning_text: Optional[str]
    decided_by: str
    created_at: datetime


class ReconciliationSummary(BaseModel):
    total_transactions: int
    matched_count: int
    partial_count: int
    unmatched_count: int
    pending_settlement_count: int
    total_unmatched_value: Decimal
    duplicate_bank_lines: int
    orphan_settlements: int

    @field_serializer("total_unmatched_value")
    def serialize_total_unmatched_value(self, value: Decimal) -> str:
        return str(value)


class RunReconciliationResponse(BaseModel):
    summary: ReconciliationSummary
    results_created: int
