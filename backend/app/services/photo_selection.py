from __future__ import annotations


def get_photo_review_status(photo) -> str:  # noqa: ANN001
    """Return the effective review state while preserving the analyzer suggestion."""
    decision = getattr(photo, "cleaning_decision", None)
    if decision == "remove":
        return "removed"
    if decision == "keep":
        return "kept"

    suggestion = getattr(photo, "cleaning_suggestion", None)
    if suggestion in {"review", "remove"}:
        return "pending_review"
    if suggestion == "keep":
        return "included"
    return "unanalyzed"


def requires_photo_review(photo) -> bool:  # noqa: ANN001
    return get_photo_review_status(photo) == "pending_review"


def is_photo_included(photo) -> bool:  # noqa: ANN001
    return getattr(photo, "cleaning_decision", None) != "remove"
