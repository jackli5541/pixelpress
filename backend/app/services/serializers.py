from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from app.common.enums import AlbumStatus
from app.models.album import Album
from app.models.album_theme_profile import AlbumThemeProfile
from app.models.chapter import Chapter
from app.models.export import Export
from app.models.page import Page
from app.models.photo import Photo
from app.models.task import Task
from app.models.photo_theme_assessment import PhotoThemeAssessment
from app.services.photo_selection import get_photo_review_status, is_photo_included


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def get_album_resume_step(status: str | None) -> str:
    if status == AlbumStatus.UPLOADED:
        return "cleaning"
    if status == AlbumStatus.CLEANED:
        return "chapters"
    if status == AlbumStatus.CLUSTERED:
        return "planning"
    if status in {AlbumStatus.PLANNED, AlbumStatus.RENDERED, AlbumStatus.EXPORTED}:
        return "export"
    return "upload"


def get_album_resume_route(album_id: str, status: str | None) -> str:
    step = get_album_resume_step(status)
    if step == "cleaning":
        return f"/albums/{album_id}/cleaning"
    if step == "chapters":
        return f"/albums/{album_id}/chapters"
    if step == "planning":
        return f"/albums/{album_id}/planning"
    if step == "export":
        return f"/albums/{album_id}/export"
    return f"/albums/{album_id}/upload"


def serialize_album(album: Album) -> dict[str, Any]:
    return {
        "id": album.id,
        "name": album.name,
        "project_id": album.project_id,
        "album_type": album.album_type,
        "book_size": album.book_size,
        "theme_style": album.theme_style,
        "cover_title": album.cover_title,
        "status": album.status,
        "photo_count": album.photo_count,
        "print_spec": album.print_spec_json,
        "content_revision": album.content_revision,
        "render_revision": album.render_revision,
        "has_preview_artifact": bool(album.preview_html_path),
        "has_print_artifact": bool(album.print_html_path),
        "has_render_manifest": bool(album.render_manifest_path),
        "resume_step": get_album_resume_step(album.status),
        "resume_route": get_album_resume_route(album.id, album.status),
        "updated_at": _iso(album.updated_at),
    }


def serialize_photo(photo: Photo) -> dict[str, Any]:
    features = deepcopy(photo.cleaning_features or {})
    features.pop("color_histogram", None)
    for item in features.get("faces", {}).get("items", []):
        item.pop("expression_vector", None)
    effective_recommendation = photo.cleaning_decision
    return {
        "id": photo.id,
        "album_id": photo.album_id,
        "filename": photo.filename,
        "content_type": photo.content_type,
        "size": photo.size,
        "width": photo.width,
        "height": photo.height,
        "storage_key": photo.storage_key,
        "url": photo.url,
        "uploaded_at": _iso(photo.uploaded_at),
        "taken_at": _iso(photo.taken_at),
        "taken_timezone": photo.taken_timezone,
        "gps_latitude": photo.gps_latitude,
        "gps_longitude": photo.gps_longitude,
        "device_model": photo.device_model,
        "quality_score": photo.quality_score,
        "scene_tags": photo.scene_tags,
        "cleaning_recommendation": effective_recommendation,
        "cleaning_issues": photo.cleaning_issues,
        "cleaning": {
            "suggestion": photo.cleaning_suggestion,
            "review_status": get_photo_review_status(photo),
            "confidence": photo.cleaning_confidence,
            "decision": photo.cleaning_decision,
            "decision_source": photo.cleaning_decision_source,
            "decided_at": _iso(photo.cleaning_decided_at),
            "excluded": photo.cleaning_decision == "remove",
            "analysis_version": photo.cleaning_analysis_version,
            "features": features or None,
        },
        "custom_caption": photo.custom_caption,
    }


def serialize_chapter(chapter: Chapter) -> dict[str, Any]:
    photo_ids = [
        link.photo_id
        for link in sorted(chapter.photo_links, key=lambda item: item.order_index)
        if link.__dict__.get("photo") is None or is_photo_included(link.__dict__["photo"])
    ]
    explanation = dict(chapter.clustering_explanation or {})
    included_photo_ids = set(photo_ids)
    segments = []
    for segment in sorted(chapter.segments, key=lambda item: item.order_index):
        segment_explanation = dict(segment.clustering_explanation or {})
        segment_photo_ids = [
            link.photo_id
            for link in sorted(segment.photo_links, key=lambda item: item.order_index)
            if link.photo_id in included_photo_ids
        ]
        segments.append({
            "id": segment.id,
            "name": segment.name,
            "description": segment.description,
            "order": segment.order_index + 1,
            "segment_type": segment.segment_type,
            "time_range": segment.time_range,
            "photo_ids": segment_photo_ids,
            "clustering": {
                "quality_score": segment.clustering_quality,
                "needs_review": segment.clustering_needs_review,
                "boundary_stability": segment_explanation.get("boundary_stability", []),
                "feature_coverage": segment_explanation.get("feature_coverage", {}),
                "auto_selected_k": segment_explanation.get("auto_selected_k", 1),
                "selected_k": segment_explanation.get("selected_k", 1),
                "peak_k": segment_explanation.get("peak_k", 1),
                "k_selection_stability": segment_explanation.get("k_selection_stability"),
                "selection_method": segment_explanation.get("selection_method"),
                "partition_method": segment_explanation.get("partition_method"),
                "representative_photo_ids": segment_explanation.get("representative_photo_ids", []),
            },
        })
    return {
        "id": chapter.id,
        "album_id": chapter.album_id,
        "name": chapter.name,
        "description": chapter.description,
        "order": chapter.order_index + 1,
        "photo_ids": photo_ids,
        "segments": segments,
        "clustering": {
            "source": chapter.clustering_source,
            "algorithm_version": chapter.clustering_algorithm_version,
            "quality_score": chapter.clustering_quality,
            "needs_review": chapter.clustering_needs_review,
              "strategy": explanation.get("strategy", "balanced"),
              "weights": explanation.get("weights", {}),
              "auto_selected_k": explanation.get("auto_selected_k", explanation.get("selected_k", 1)),
              "selected_k": explanation.get("selected_k", 1),
              "peak_k": explanation.get("peak_k", explanation.get("selected_k", 1)),
              "granularity": explanation.get("granularity", 0),
              "k_selection_stability": explanation.get("k_selection_stability"),
              "selection_method": explanation.get("selection_method"),
              "partition_method": explanation.get("partition_method"),
            "boundary_stability": explanation.get("boundary_stability", {}),
            "representative_photo_ids": explanation.get("representative_photo_ids", []),
            "naming_source": explanation.get("naming_source", "rule"),
            "feature_coverage": explanation.get("feature_coverage", {}),
            "embedding_model": explanation.get("embedding_model"),
            "degraded_photo_count": explanation.get("degraded_photo_count", 0),
        },
        "created_at": _iso(chapter.created_at),
    }


def serialize_theme_profile(profile: AlbumThemeProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "analysis_revision": profile.analysis_revision,
        "confirmed_revision": profile.confirmed_revision,
        "profile_version": profile.profile_version,
        "source": profile.source,
        "status": profile.status,
        "title": profile.title,
        "constraints": dict(profile.constraints_json or {}),
        "candidates": list(profile.candidates_json or []),
        "chapter_strategy": profile.chapter_strategy,
        "fallback_used": profile.fallback_used,
        "custom_input": profile.custom_input,
        "provider": profile.provider,
        "model": profile.model,
        "confirmed_at": _iso(profile.confirmed_at),
    }


def serialize_theme_assessment(assessment: PhotoThemeAssessment) -> dict[str, Any]:
    effective_decision = assessment.user_decision or assessment.suggested_decision
    return {
        "photo": serialize_photo(assessment.photo),
        "relevance_score": assessment.relevance_score,
        "relevance_label": assessment.relevance_label,
        "suggested_decision": assessment.suggested_decision,
        "user_decision": assessment.user_decision,
        "effective_decision": effective_decision,
        "reasons": list(assessment.reasons_json or []),
        "relevance_evidence": dict(assessment.evidence_json or {}),
        "scoring_version": assessment.scoring_version,
        "feature_version": assessment.feature_version,
    }


def serialize_page(page: Page) -> dict[str, Any]:
    photo_ids = [
        link.photo_id
        for link in sorted(page.photo_links, key=lambda item: item.order_index)
        if link.__dict__.get("photo") is None or is_photo_included(link.__dict__["photo"])
    ]
    preview_snippet = (page.html or "")[:800]
    return {
        "id": page.id,
        "album_id": page.album_id,
        "chapter_id": page.chapter_id,
        "page_number": page.page_number,
        "template": page.template,
        "photo_ids": photo_ids,
        "photo_count": len(photo_ids),
        "preview_snippet": preview_snippet,
        "preview_available": bool(page.html),
        "status": page.status,
        "meta": page.meta_json,
        "created_at": _iso(page.created_at),
    }


def serialize_task(task: Task) -> dict[str, Any]:
    debug_payload = task.debug_payload or {}
    request_info = debug_payload.get("request") if isinstance(debug_payload, dict) else None
    request_id = request_info.get("request_id") if isinstance(request_info, dict) else None
    return {
        "id": task.id,
        "album_id": task.album_id,
        "task_type": task.task_type,
        "task_status": task.task_status,
        "job_id": task.job_id,
        "idempotency_key": task.idempotency_key,
        "task_params": task.task_params,
        "resource_type": task.resource_type,
        "resource_id": task.resource_id,
        "requested_revision": task.requested_revision,
        "result_revision": task.result_revision,
        "progress_pct": task.progress_pct,
        "progress_step": task.progress_step,
        "attempt_count": task.attempt_count,
        "max_attempts": task.max_attempts,
        "worker_name": task.worker_name,
        "retryable": task.retryable,
        "error_code": task.error_code,
        "provider": task.provider,
        "model": task.model,
        "error_message": task.error_message,
        "fallback_reason": task.fallback_reason,
        "cancel_requested": task.cancel_requested,
        "pipeline_name": task.pipeline_name,
        "pipeline_version": task.pipeline_version,
        "result_payload": task.result_payload,
        "metrics_payload": task.metrics_payload,
        "debug_payload": task.debug_payload,
        "request_id": request_id,
        "created_at": _iso(task.created_at),
        "started_at": _iso(task.started_at),
        "heartbeat_at": _iso(task.heartbeat_at),
        "updated_at": _iso(task.updated_at),
        "finished_at": _iso(task.finished_at),
    }


def serialize_export(export: Export) -> dict[str, Any]:
    return {
        "id": export.id,
        "album_id": export.album_id,
        "status": export.status,
        "format": export.format,
        "file_path": export.file_path,
        "file_size": export.file_size,
        "created_at": _iso(export.created_at),
        "task_id": export.task_id,
    }
