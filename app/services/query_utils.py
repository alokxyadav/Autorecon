"""
Pure text-parsing helpers for the query service. Deliberately dependency-free
(no SQLAlchemy imports) so this logic can be unit tested without a database
or any external package being installed.
"""

import re

ORDER_ID_PATTERN = re.compile(r"order[_\s]?(\d+)", re.IGNORECASE)


def extract_order_id(question: str) -> str | None:
    match = ORDER_ID_PATTERN.search(question)
    if match:
        return f"order_{match.group(1).zfill(5)}"
    return None
