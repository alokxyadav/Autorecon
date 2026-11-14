import sys
import os
import csv
import io

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.export_service import (
    reconciliation_results_to_csv, audit_log_to_csv,
    RECONCILIATION_CSV_COLUMNS, AUDIT_LOG_CSV_COLUMNS,
)


def test_reconciliation_csv_has_correct_header():
    csv_text = reconciliation_results_to_csv([])
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == RECONCILIATION_CSV_COLUMNS


def test_reconciliation_csv_round_trips_a_full_row():
    row = {
        "id": 1, "transaction_id": 5, "settlement_id": 5, "bank_line_id": None,
        "match_type": "fuzzy", "status": "pending_human_review", "confidence": 60,
        "delta_amount": "7.00", "notes": "Fee drift beyond tolerance.",
        "ai_proposed_resolution": "Verify fee schedule.", "ai_confidence": 72,
        "reviewer_name": None, "created_at": "2026-08-27T10:00:00",
        "updated_at": "2026-08-27T10:00:00",
    }
    csv_text = reconciliation_results_to_csv([row])
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "1"
    assert parsed[0]["match_type"] == "fuzzy"
    assert parsed[0]["delta_amount"] == "7.00"


def test_reconciliation_csv_handles_missing_fields_without_crashing():
    # A result with no AI proposal yet (transaction_id=None fields etc.)
    # must export cleanly, not raise or produce a malformed row.
    sparse_row = {"id": 2, "match_type": "unmatched", "status": "unmatched"}
    csv_text = reconciliation_results_to_csv([sparse_row])
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert parsed[0]["id"] == "2"
    assert parsed[0]["ai_proposed_resolution"] == ""  # missing field -> empty, not "None"


def test_reconciliation_csv_correctly_escapes_embedded_commas_and_quotes():
    # This is the exact class of bug a naive string-join CSV implementation
    # gets wrong — a note field containing a comma or quote must not corrupt
    # the column structure when the file is reopened.
    row = {
        "id": 3, "match_type": "unmatched", "status": "unmatched",
        "notes": 'Settlement delta of ₹7.00, exceeds tolerance; customer said "not my problem".',
    }
    csv_text = reconciliation_results_to_csv([row])
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert parsed[0]["notes"] == 'Settlement delta of ₹7.00, exceeds tolerance; customer said "not my problem".'


def test_reconciliation_csv_handles_none_delta_amount_as_empty_string_not_the_word_none():
    row = {"id": 4, "match_type": "unmatched", "status": "unmatched", "delta_amount": None}
    csv_text = reconciliation_results_to_csv([row])
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert parsed[0]["delta_amount"] == ""


def test_reconciliation_csv_with_many_rows_preserves_order():
    rows = [{"id": i, "match_type": "exact", "status": "matched"} for i in range(1, 6)]
    csv_text = reconciliation_results_to_csv(rows)
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert [r["id"] for r in parsed] == ["1", "2", "3", "4", "5"]


def test_audit_log_csv_has_correct_header():
    csv_text = audit_log_to_csv([])
    reader = csv.reader(io.StringIO(csv_text))
    header = next(reader)
    assert header == AUDIT_LOG_CSV_COLUMNS


def test_audit_log_csv_round_trips_a_row():
    row = {
        "id": 1, "event_type": "ai_proposal", "decided_by": "claude",
        "reasoning_text": "Likely a fee rounding discrepancy.",
        "created_at": "2026-08-27T10:00:00",
    }
    csv_text = audit_log_to_csv([row])
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert parsed[0]["event_type"] == "ai_proposal"
    assert parsed[0]["reasoning_text"] == "Likely a fee rounding discrepancy."


def test_audit_log_csv_handles_newlines_in_reasoning_text():
    # Multi-line reasoning text is realistic (a longer explanation) and must
    # not break row boundaries when the CSV is reopened.
    row = {
        "id": 2, "event_type": "human_decision", "decided_by": "Priya",
        "reasoning_text": "Approved after review.\nChecked against bank statement manually.",
        "created_at": "2026-08-27T11:00:00",
    }
    csv_text = audit_log_to_csv([row])
    reader = csv.DictReader(io.StringIO(csv_text))
    parsed = list(reader)
    assert len(parsed) == 1  # the embedded newline must not create a phantom second row
    assert "Checked against bank statement manually." in parsed[0]["reasoning_text"]


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
