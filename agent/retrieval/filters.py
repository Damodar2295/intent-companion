"""Shared pre-ranking metadata predicates; reserved keys are internal only."""

from datetime import datetime


def matches(kind, metadata, filters):
    for key, value in filters.items():
        if key == "_fresh_at":
            try:
                expiry = datetime.fromisoformat(str(metadata["expires_at"]))
                now = datetime.fromisoformat(value)
                if expiry.tzinfo is None or expiry <= now or metadata.get("active") is False:
                    return False
            except (KeyError, TypeError, ValueError):
                return False
        elif key == "_valid_on":
            # ISO date comparison, inclusive for date-only catalog validity.
            day = value
            if metadata.get("valid_from") and str(metadata["valid_from"])[:10] > day:
                return False
            if metadata.get("valid_to") and str(metadata["valid_to"])[:10] < day:
                return False
        elif key == "_types":
            if kind not in value:
                return False
        elif key == "_products":
            if not set(value).intersection(metadata.get("product_ids", [])):
                return False
        elif (kind if key == "document_type" else metadata.get(key)) != value:
            return False
    return True
