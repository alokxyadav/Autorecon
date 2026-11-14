"""
Natural-language query over the audit trail.

Deliberately simple retrieval (no vector DB, no embeddings) — for the scale
of a buildathon demo, a regex-based order_id/result_id extraction plus a
text search over recent audit_log entries is transparent, debuggable, and
good enough. If this needs to scale to thousands of entries, swap the
retrieval step for a proper search index; `answer_query()`'s contract
(retrieve -> ground -> answer or say "not found") stays the same either way.
"""

import re
from typing import Callable

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLogRecord
from app.models.transaction import TransactionRecord
from app.services.query_utils import extract_order_id

RESULT_ID_PATTERN = re.compile(r"reconciliation(?:\s+result)?\s*#?(\d+)", re.IGNORECASE)

QUERY_SYSTEM_PROMPT = """You are answering a finance team member's question about their reconciliation system, using ONLY the audit log excerpts provided below.

Rules:
- If the excerpts answer the question, answer clearly and concisely, in plain language a non-technical finance person would understand.
- If the excerpts do NOT contain enough information to answer, say so explicitly. Do not guess or fill gaps with assumptions.
- Never invent order IDs, amounts, or outcomes that aren't in the excerpts.
"""


def _retrieve_relevant_entries(db: Session, question: str, limit: int = 10) -> list[AuditLogRecord]:
    order_id = extract_order_id(question)

    if order_id:
        txn = db.query(TransactionRecord).filter(TransactionRecord.order_id == order_id).first()
        if txn is None:
            return []
        # Audit entries reference transaction_id inside payload_json as plain
        # text, so a LIKE search on the serialized id is sufficient here.
        entries = db.query(AuditLogRecord).filter(
            AuditLogRecord.payload_json.like(f'%"transaction_id": {txn.id}%')
        ).order_by(AuditLogRecord.created_at.asc()).all()
        return entries

    # No specific order mentioned — fall back to the most recent entries,
    # which at least grounds general questions like "what needs review?"
    return db.query(AuditLogRecord).order_by(
        AuditLogRecord.created_at.desc()
    ).limit(limit).all()


def answer_query(db: Session, question: str, complete_fn: Callable[[str, str], str]) -> dict:
    entries = _retrieve_relevant_entries(db, question)

    if not entries:
        return {
            "answer": "I couldn't find any audit trail entries related to that question.",
            "grounded_in": [],
        }

    context_lines = [
        f"[{e.created_at.isoformat()}] {e.event_type} by {e.decided_by}: "
        f"{e.reasoning_text or e.payload_json}"
        for e in entries
    ]
    context_block = "\n".join(context_lines)
    user_prompt = f"Audit log excerpts:\n{context_block}\n\nQuestion: {question}"

    try:
        answer_text = complete_fn(QUERY_SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        return {
            "answer": (
                "I couldn't reach the reasoning service to answer this right now "
                f"({e}). Here are the relevant audit log entries directly:"
            ),
            "grounded_in": [e.id for e in entries],
        }

    return {
        "answer": answer_text.strip(),
        "grounded_in": [e.id for e in entries],
    }
