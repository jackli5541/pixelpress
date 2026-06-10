from __future__ import annotations

from datetime import datetime

from pixelpress_backend.algorithms.feature_extraction import (
    CLIPEmbeddingGenerator,
    DuplicateDetector,
    FaceNetClusterer,
    ImageQualityAnalyzer,
    PerceptualHash,
    SceneTagGenerator,
    U2NetSaliencyGenerator,
    YOLOFaceDetector,
    YOLOSubjectDetector,
)
from pixelpress_backend.models.domain import PhotoAsset, RelativeFrame
from pixelpress_backend.models.workflow_contracts import (
    CleanedPhotoSet,
    CleaningSummary,
    DroppedPhoto,
    KeptPhoto,
    PhotoCleaningInput,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def _normalize_box(box: dict, img_width: int, img_height: int) -> RelativeFrame:
    return RelativeFrame(
        x=box["x"] / img_width if img_width > 0 else 0.0,
        y=box["y"] / img_height if img_height > 0 else 0.0,
        w=box["width"] / img_width if img_width > 0 else 0.0,
        h=box["height"] / img_height if img_height > 0 else 0.0,
    )


def _extract_features(photo_id: str, asset: PhotoAsset | None = None) -> dict:
    features = {
        "photo_id": photo_id,
        "perceptual_hash": "",
        "embedding": [],
        "quality_scores": {
            "sharpness": None,
            "exposure": None,
            "blur": None,
            "noise": None,
            "face_integrity": None,
            "overall": None,
        },
        "face_boxes": [],
        "subject_boxes": [],
        "saliency_map": "",
        "scene_tags": [],
        "person_id": "",
        "orientation": asset.orientation if asset else None,
        "captured_at": asset.exif.captured_at if asset and asset.exif else None,
    }

    if asset is None or asset.image_url is None:
        return features

    try:
        from PIL import Image
        import requests
        response = requests.get(asset.image_url, timeout=10)
        img = Image.open(response.raw)
    except Exception:
        return features

    width, height = img.size

    features["perceptual_hash"] = PerceptualHash.compute(img)
    features["embedding"] = CLIPEmbeddingGenerator.generate_embedding(img)
    features["saliency_map"] = U2NetSaliencyGenerator.generate_saliency(img)
    features["scene_tags"] = SceneTagGenerator.generate_tags(img)

    features["quality_scores"]["sharpness"] = ImageQualityAnalyzer.analyze_sharpness(img)
    features["quality_scores"]["exposure"] = ImageQualityAnalyzer.analyze_exposure(img)
    features["quality_scores"]["blur"] = ImageQualityAnalyzer.analyze_blur(img)
    features["quality_scores"]["noise"] = ImageQualityAnalyzer.analyze_noise(img)

    face_boxes = YOLOFaceDetector.detect(img)
    features["face_boxes"] = [_normalize_box(b, width, height) for b in face_boxes]

    if face_boxes:
        best_face = max(face_boxes, key=lambda b: b["width"] * b["height"])
        features["quality_scores"]["face_integrity"] = ImageQualityAnalyzer.compute_face_integrity(
            (best_face["x"], best_face["y"], best_face["width"], best_face["height"]),
            width,
            height,
        )

    subject_boxes = YOLOSubjectDetector.detect(img)
    features["subject_boxes"] = [_normalize_box(b, width, height) for b in subject_boxes]

    sharpness_norm = features["quality_scores"]["sharpness"] / 1000.0 if features["quality_scores"]["sharpness"] else 0.0
    exposure_score = features["quality_scores"]["exposure"] or 0.0
    face_integrity_score = features["quality_scores"]["face_integrity"] or 0.5
    blur_norm = 1.0 - (features["quality_scores"]["blur"] / 50.0 if features["quality_scores"]["blur"] else 0.0)
    noise_norm = 1.0 - (features["quality_scores"]["noise"] / 20.0 if features["quality_scores"]["noise"] else 0.0)

    features["quality_scores"]["overall"] = float(
        0.3 * min(sharpness_norm, 1.0)
        + 0.25 * exposure_score
        + 0.2 * face_integrity_score
        + 0.15 * max(blur_norm, 0.0)
        + 0.1 * max(noise_norm, 0.0)
    )

    return features


def photo_cleaning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    node_input = PhotoCleaningInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        book_size=state.request.book_size,
        photo_assets=state.request.photo_assets,
        constraints=state.request.constraints,
    )

    asset_lookup = {asset.photo_id: asset for asset in node_input.photo_assets}
    ordered_photo_ids = state.request.photo_ids or [asset.photo_id for asset in node_input.photo_assets]

    valid_photos = []
    dropped_photos = []
    photo_features_list = []

    for photo_id in ordered_photo_ids:
        asset = asset_lookup.get(photo_id)
        features = _extract_features(photo_id, asset)
        photo_features_list.append(features)

        if features["quality_scores"]["overall"] is not None and features["quality_scores"]["overall"] < 0.2:
            dropped_photos.append(DroppedPhoto(photo_id=photo_id, reason="low_quality"))
        else:
            valid_photos.append(photo_id)

    images_for_clustering = {}
    for photo_id in valid_photos:
        asset = asset_lookup.get(photo_id)
        if asset and asset.image_url:
            try:
                from PIL import Image
                import requests
                response = requests.get(asset.image_url, timeout=10)
                images_for_clustering[photo_id] = Image.open(response.raw)
            except Exception:
                pass

    person_cluster_map = FaceNetClusterer.cluster_faces(images_for_clustering)

    duplicate_groups = DuplicateDetector.find_duplicates(photo_features_list)
    duplicate_set = set()
    for group in duplicate_groups:
        if len(group) > 1:
            duplicate_set.update(group[1:])

    features_lookup = {f["photo_id"]: f for f in photo_features_list}

    kept_photo_list = []
    final_dropped = []

    for photo_id in ordered_photo_ids:
        features = features_lookup.get(photo_id, {})
        quality_score = features.get("quality_scores", {}).get("overall")

        is_duplicate = photo_id in duplicate_set

        if photo_id not in valid_photos:
            final_dropped.append(DroppedPhoto(photo_id=photo_id, reason="low_quality"))
        elif is_duplicate:
            kept_photo_list.append(KeptPhoto(
                photo_id=photo_id,
                decision="deprioritize",
                rank_weight=0.3,
                quality_score=quality_score,
                duplicate_score=0.0,
                saliency_score=None,
                face_integrity_score=features.get("quality_scores", {}).get("face_integrity"),
                drop_reason=None,
                captured_at=features.get("captured_at"),
                location_cluster=None,
                embedding_ref=None,
                person_ids=[person_cluster_map.get(photo_id, "")] if person_cluster_map.get(photo_id) else [],
                scene_tags=features.get("scene_tags", []),
                orientation=features.get("orientation"),
                is_duplicate=True,
            ))
        else:
            rank_weight = min(1.0, (quality_score or 0.5) * 1.5)
            kept_photo_list.append(KeptPhoto(
                photo_id=photo_id,
                decision="keep",
                rank_weight=rank_weight,
                quality_score=quality_score,
                duplicate_score=1.0,
                saliency_score=None,
                face_integrity_score=features.get("quality_scores", {}).get("face_integrity"),
                drop_reason=None,
                captured_at=features.get("captured_at"),
                location_cluster=None,
                embedding_ref=None,
                person_ids=[person_cluster_map.get(photo_id, "")] if person_cluster_map.get(photo_id) else [],
                scene_tags=features.get("scene_tags", []),
                orientation=features.get("orientation"),
                is_duplicate=False,
            ))

    for dp in dropped_photos:
        if dp.photo_id not in [k.photo_id for k in kept_photo_list]:
            final_dropped.append(dp)

    cleaning_summary = CleaningSummary(
        input_count=len(ordered_photo_ids),
        valid_count=len(kept_photo_list),
        dropped_count=len(final_dropped),
        duplicate_groups=len(duplicate_groups),
    )

    cleaned_photo_set = CleanedPhotoSet(
        album_id=state.request.album_id,
        valid_photos=kept_photo_list,
        dropped_photos=final_dropped,
        cleaning_summary=cleaning_summary,
    )

    state.cleaned_photo_set = cleaned_photo_set
    return state