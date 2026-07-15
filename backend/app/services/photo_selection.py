from __future__ import annotations


def is_photo_included(photo) -> bool:  # noqa: ANN001
    return getattr(photo, "cleaning_decision", None) != "remove"
