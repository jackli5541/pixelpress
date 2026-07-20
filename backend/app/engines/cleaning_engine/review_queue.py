from __future__ import annotations

from typing import Any

FACE_REVIEW_REASONS = {
    "face_analysis_failed",
    "face_edge_crop_suspected",
    "face_blur_suspected",
    "closed_eyes_suspected",
    "face_occlusion_suspected",
    "body_crop_suspected",
    "expression_attention",
}


def _is_pending(photo: Any) -> bool:
    return photo.cleaning_decision is None and photo.cleaning_suggestion in {"review", "remove"}


def _priority(reason_codes: set[str], *, duplicate: bool) -> int:
    if "analysis_failed" in reason_codes:
        return 100
    if FACE_REVIEW_REASONS.intersection(reason_codes):
        return 80
    if duplicate:
        return 70
    if "sharpness_severe" in reason_codes:
        return 65
    return 50


class ReviewQueueBuilder:
    policy_version = "cleaning-policy-v3"

    def build(self, photos: list[Any], groups: list[Any]) -> list[dict[str, Any]]:
        photos_by_id = {photo.id: photo for photo in photos}
        consumed: set[str] = set()
        queue: list[dict[str, Any]] = []
        for group in groups:
            pending_ids = [
                member.photo_id
                for member in group.members
                if member.photo_id in photos_by_id
                and _is_pending(photos_by_id[member.photo_id])
            ]
            if not pending_ids:
                continue
            all_photo_ids = [member.photo_id for member in sorted(group.members, key=lambda item: (item.rank, item.id))]
            reasons = {f"duplicate_{group.group_type}"}
            for photo_id in all_photo_ids:
                reasons.update(photos_by_id[photo_id].cleaning_issues or [])
            suggested_action = "accept_preferred" if float(group.confidence or 0) >= 0.8 else "keep_all"
            queue.append({
                "id": f"group:{group.id}",
                "kind": "duplicate_group",
                "photo_ids": all_photo_ids,
                "group_id": group.id,
                "preferred_photo_id": group.preferred_photo_id,
                "reason_codes": sorted(reasons),
                "priority": _priority(reasons, duplicate=True),
                "suggested_action": suggested_action,
                "explanation": {
                    "group_type": group.group_type,
                    "confidence": group.confidence,
                    "pending_count": len(pending_ids),
                },
                "policy_version": self.policy_version,
            })
            consumed.update(all_photo_ids)

        for photo in photos:
            if photo.id in consumed or not _is_pending(photo):
                continue
            reasons = set(photo.cleaning_issues or [])
            suggested_action = "remove" if photo.cleaning_suggestion == "remove" else "keep"
            queue.append({
                "id": f"photo:{photo.id}",
                "kind": "single_photo",
                "photo_ids": [photo.id],
                "group_id": None,
                "preferred_photo_id": None,
                "reason_codes": sorted(reasons),
                "priority": _priority(reasons, duplicate=False),
                "suggested_action": suggested_action,
                "explanation": {
                    "quality_score": photo.quality_score,
                    "confidence": photo.cleaning_confidence,
                },
                "policy_version": self.policy_version,
            })

        return sorted(queue, key=lambda item: (-item["priority"], item["kind"], item["id"]))


def build_review_queue(photos: list[Any], groups: list[Any]) -> list[dict[str, Any]]:
    return ReviewQueueBuilder().build(photos, groups)
