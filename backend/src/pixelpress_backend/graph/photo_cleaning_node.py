from __future__ import annotations

from pixelpress_backend.algorithms.feature_extraction import (
    CLIPEmbeddingGenerator,
    DuplicateDetector,
)
from pixelpress_backend.models.domain import PhotoFeatures
from pixelpress_backend.models.workflow_contracts import (
    CleanedPhotoSet,
    CleaningSummary,
    DroppedPhoto,
    KeptPhoto,
    PhotoCleaningInput,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState

QUALITY_THRESHOLD = 0.3
MIN_DIMENSION = 300
DUPLICATE_HASH_THRESHOLD = 8
DUPLICATE_EMBEDDING_THRESHOLD = 0.92


def photo_cleaning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    node_input = PhotoCleaningInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        book_size=state.request.book_size,
        photo_assets=state.request.photo_assets,
        constraints=state.request.constraints,
    )

    asset_lookup = {asset.photo_id: asset for asset in node_input.photo_assets}
    ordered_photo_ids = state.request.photo_ids if state.request.photo_ids else [asset.photo_id for asset in node_input.photo_assets]

    valid_photos: list[KeptPhoto] = []
    dropped_photos: list[DroppedPhoto] = []
    duplicate_groups: dict[str, list[str]] = {}

    photo_features_list: list[dict] = []

    for photo_id in ordered_photo_ids:
        asset = asset_lookup.get(photo_id)
        if not asset:
            photo_features_list.append({
                "photo_id": photo_id,
                "embedding": None,
                "perceptual_hash": None,
                "quality_scores": {"overall": None},
                "scene_tags": [],
                "orientation": None,
                "captured_at": None,
            })
            continue

        features = _extract_or_get_features(asset.features)
        features["photo_id"] = photo_id
        features["embedding"] = asset.features.embedding
        features["perceptual_hash"] = asset.features.perceptual_hash
        features["quality_scores"] = {
            "overall": asset.features.quality_scores.overall,
            "sharpness": asset.features.quality_scores.sharpness,
            "exposure": asset.features.quality_scores.exposure,
            "blur": asset.features.quality_scores.blur,
            "noise": asset.features.quality_scores.noise,
            "face_integrity": asset.features.quality_scores.face_integrity,
        }
        features["scene_tags"] = asset.features.scene_tags
        features["orientation"] = asset.orientation
        features["captured_at"] = asset.exif.captured_at
        photo_features_list.append(features)

    duplicate_groups = DuplicateDetector.find_duplicates(photo_features_list)

    for photo_id in ordered_photo_ids:
        asset = asset_lookup.get(photo_id)

        if photo_id in node_input.constraints.must_exclude:
            dropped_photos.append(DroppedPhoto(photo_id=photo_id, reason="must_exclude"))
            continue

        if asset:
            decision, drop_reason = _evaluate_photo(photo_id, asset, duplicate_groups, asset_lookup)
            features = asset.features
            quality_scores = features.quality_scores
            captured_at = asset.exif.captured_at
            orientation = asset.orientation
            person_ids = features.person_ids
            scene_tags = features.scene_tags
            perceptual_hash = features.perceptual_hash
            embedding_ref = str(features.embedding)[:32] if features.embedding else None
            embedding = features.embedding
            embedding_model_version = features.embedding_model_version
            width = asset.width
            height = asset.height
            face_boxes = features.face_boxes
            subject_boxes = features.subject_boxes
            dominant_color = features.dominant_color
        else:
            decision, drop_reason = "keep", None
            quality_scores = PhotoFeatures().quality_scores
            captured_at = None
            orientation = None
            person_ids = []
            scene_tags = []
            perceptual_hash = None
            embedding_ref = None
            embedding = None
            embedding_model_version = None
            width = None
            height = None
            face_boxes = []
            subject_boxes = []
            dominant_color = None

        kept = KeptPhoto(
            photo_id=photo_id,
            decision=decision,
            rank_weight=_calculate_rank_weight(decision, quality_scores.overall),
            quality_score=quality_scores.overall,
            sharpness_score=quality_scores.sharpness,
            exposure_score=quality_scores.exposure,
            blur_score=quality_scores.blur,
            noise_score=quality_scores.noise,
            face_integrity_score=quality_scores.face_integrity,
            closed_eye_prob=None,
            duplicate_score=_calculate_duplicate_score(photo_id, duplicate_groups),
            saliency_score=None,
            drop_reason=drop_reason if decision == "drop" else None,
            captured_at=captured_at,
            location_cluster=None,
            embedding_ref=embedding_ref,
            embedding=embedding,
            embedding_model_version=embedding_model_version,
            person_ids=person_ids,
            scene_tags=scene_tags,
            orientation=orientation,
            is_duplicate=any(photo_id in group for group in duplicate_groups.values()),
            perceptual_hash=perceptual_hash,
            duplicate_group_id=_find_duplicate_group_id(photo_id, duplicate_groups),
            width=width,
            height=height,
            face_boxes=face_boxes,
            subject_boxes=subject_boxes,
            dominant_color=dominant_color,
        )

        if decision == "drop":
            dropped_photos.append(DroppedPhoto(photo_id=photo_id, reason=drop_reason))
        else:
            valid_photos.append(kept)

    cleaning_summary = CleaningSummary(
        input_count=len(ordered_photo_ids),
        valid_count=len(valid_photos),
        dropped_count=len(dropped_photos),
        duplicate_groups=len(duplicate_groups),
    )

    cleaned_photo_set = CleanedPhotoSet(
        album_id=node_input.album_id,
        valid_photos=valid_photos,
        dropped_photos=dropped_photos,
        cleaning_summary=cleaning_summary,
    )

    state.cleaned_photo_set = cleaned_photo_set
    return state


def _extract_or_get_features(features: PhotoFeatures) -> dict:
    return {
        "embedding": features.embedding,
        "perceptual_hash": features.perceptual_hash,
        "quality_scores": {
            "overall": features.quality_scores.overall,
            "sharpness": features.quality_scores.sharpness,
            "exposure": features.quality_scores.exposure,
            "blur": features.quality_scores.blur,
            "noise": features.quality_scores.noise,
            "face_integrity": features.quality_scores.face_integrity,
        },
        "scene_tags": features.scene_tags,
    }


def _evaluate_photo(photo_id: str, asset: object, duplicate_groups: dict[str, list[str]], asset_lookup: dict[str, object]) -> tuple[str, str | None]:
    width = getattr(asset, "width", None)
    height = getattr(asset, "height", None)
    features = getattr(asset, "features", None)

    if width is None or height is None or width < MIN_DIMENSION or height < MIN_DIMENSION:
        return "drop", "too_small"

    if features and features.quality_scores and features.quality_scores.overall is not None:
        if features.quality_scores.overall < QUALITY_THRESHOLD:
            return "drop", "low_quality"

    if features and features.feature_status == "failed":
        return "drop", "feature_extraction_failed"

    duplicate_group = _find_duplicate_group_id(photo_id, duplicate_groups)
    if duplicate_group:
        group_photos = duplicate_groups[duplicate_group]
        if photo_id != group_photos[0]:
            if features and features.quality_scores and features.quality_scores.overall is not None:
                first_photo_id = group_photos[0]
                first_asset = asset_lookup.get(first_photo_id)
                if first_asset:
                    first_features = getattr(first_asset, "features", None)
                    if first_features and first_features.quality_scores and first_features.quality_scores.overall is not None:
                        if features.quality_scores.overall < first_features.quality_scores.overall:
                            return "deprioritize", "duplicate_low_quality"
            return "deprioritize", "duplicate"

    return "keep", None


def _calculate_rank_weight(decision: str, quality_score: float | None) -> float:
    base_weight = 1.0
    if decision == "deprioritize":
        base_weight = 0.3
    if quality_score is not None:
        base_weight *= quality_score
    return round(max(0.1, base_weight), 2)


def _calculate_duplicate_score(photo_id: str, duplicate_groups: dict[str, list[str]]) -> float:
    for group_id, photos in duplicate_groups.items():
        if photo_id in photos:
            return 1.0 / len(photos)
    return 0.0


def _find_duplicate_group_id(photo_id: str, duplicate_groups: dict[str, list[str]]) -> str | None:
    for group_id, photos in duplicate_groups.items():
        if photo_id in photos:
            return group_id
    return None