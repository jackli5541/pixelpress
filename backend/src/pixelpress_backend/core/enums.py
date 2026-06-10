from enum import Enum


class SceneMode(str, Enum):
    ANNUAL = "annual"
    EVENT = "event"


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    PARTIAL = "partial"


class FeatureStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    PARTIAL = "partial"
    READY = "ready"
    FAILED = "failed"


class AlbumStatus(str, Enum):
    DRAFT = "draft"
    GENERATING = "generating"
    REVIEWABLE = "reviewable"
    LOCKED = "locked"
    ORDERED = "ordered"
    ARCHIVED = "archived"


class BookLayoutStatus(str, Enum):
    DRAFT = "draft"
    LOCKED = "locked"
    EXPORTED = "exported"
    ARCHIVED = "archived"


class TaskType(str, Enum):
    FEATURE_EXTRACT = "feature_extract"
    LAYOUT_GENERATE = "layout_generate"
    PARTIAL_REGENERATE = "partial_regenerate"
    RENDER_PREVIEW = "render_preview"
    EXPORT_PDF = "export_pdf"


class LayoutDecision(str, Enum):
    ACCEPT = "accept"
    RETRY_LAYOUT = "retry_layout"
    RETRY_PLANNING = "retry_planning"
    RETRY_CHAPTER_CLUSTERING = "retry_chapter_clustering"


class OperationType(str, Enum):
    REPLACE_PHOTO = "replace_photo"
    SWAP_PAGE_PHOTOS = "swap_page_photos"
    ADJUST_CROP = "adjust_crop"
    SET_CAPTION = "set_caption"
    SET_CHAPTER_TITLE = "set_chapter_title"
    MARK_PAGE_DISLIKED = "mark_page_disliked"
    SET_HERO_PERSON = "set_hero_person"
    MERGE_CHAPTERS = "merge_chapters"
    SPLIT_CHAPTER = "split_chapter"
    REORDER_CHAPTERS = "reorder_chapters"
    LOCK_LAYOUT = "lock_layout"
    REQUEST_EXPORT = "request_export"
    SUBMIT_ORDER = "submit_order"
