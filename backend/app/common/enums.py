from enum import StrEnum


class AlbumStatus(StrEnum):
    DRAFT = "draft"
    UPLOADED = "uploaded"
    CLEANED = "cleaned"
    CLUSTERED = "clustered"
    PLANNED = "planned"
    RENDERED = "rendered"
    EXPORTED = "exported"
    FAILED = "failed"


class TaskStatus(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
