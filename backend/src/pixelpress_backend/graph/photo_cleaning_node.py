from __future__ import annotations

from PIL import Image
import io

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
from pixelpress_backend.models.domain import PhotoFeatures, PhotoQualityScores, RelativeFrame
from pixelpress_backend.models.workflow_contracts import (
    CleanedPhotoSet,
    DroppedPhoto,
    KeptPhoto,
    PhotoCleaningInput,
)
from pixelpress_backend.models.workflow_state import LayoutWorkflowState


def photo_cleaning_node(state: LayoutWorkflowState) -> LayoutWorkflowState:
    node_input = PhotoCleaningInput(
        album_id=state.request.album_id,
        scene_mode=state.request.scene_mode,
        book_size=state.request.book_size,
        photo_assets=state.request.photo_assets,
        constraints=state.request.constraints,
    )

    asset_lookup = {asset.photo_id: asset for asset in (node_input.photo_assets or [])}
    ordered_photo_ids = state.request.photo_ids if state.request.photo_ids else [asset.photo_id for asset in (node_input.photo_assets or [])]

    valid_photos = []
    dropped_photos = []
    photo_features_list = []

    for photo_id in ordered_photo_ids:
        asset = asset_lookup.get(photo_id)
        features = PhotoFeatures()

        img = Image.new("RGB", (100, 100), color="white")

        features.perceptual_hash = PerceptualHash.compute(img)

        quality_result = ImageQualityAnalyzer.analyze(img)
        features.quality_scores = PhotoQualityScores(**quality_result)

        features.embedding = CLIPEmbeddingGenerator.generate_embedding(img)
        features.embedding_model_version = "clip-vit-b-32"

        face_boxes = YOLOFaceDetector.detect(img)
        width = asset.width if asset else 100
        height = asset.height if asset else 100
        features.face_boxes = [
            RelativeFrame(x=b["x"] / width, y=b["y"] / height,
                          w=b["w"] / width, h=b["h"] / height)
            for b in face_boxes
        ]

        subject_boxes = YOLOSubjectDetector.detect(img)
        features.subject_boxes = [
            RelativeFrame(x=b["x"] / width, y=b["y"] / height,
                          w=b["w"] / width, h=b["h"] / height)
            for b in subject_boxes
        ]

        features.saliency_map = U2NetSaliencyGenerator.generate(img)
        features.saliency_model_version = "u2net-fallback"

        features.scene_tags = SceneTagGenerator.generate(img)

        features.person_ids = FaceNetClusterer.cluster(face_boxes)

        photo_features_list.append({
            "photo_id": photo_id,
            "perceptual_hash": features.perceptual_hash,
            "embedding": features.embedding,
            "duplicate_group_id": None,
        })

        if asset:
            asset.features = features

    duplicate_groups = DuplicateDetector.find_duplicates(photo_features_list)

    for photo_id in ordered_photo_ids:
        asset = asset_lookup.get(photo_id)
        features = asset.features if asset else PhotoFeatures()
        quality_score = features.quality_scores.overall or 0.0

        decision = "keep"
        drop_reason = None
        is_duplicate = False

        if features.perceptual_hash:
            for group_id, photos in duplicate_groups.items():
                if photo_id in photos:
                    is_duplicate = True
                    if len(photos) > 1 and photos.index(photo_id) > 0:
                        decision = "deprioritize"

        if quality_score < 0.1:
            decision = "drop"
            drop_reason = "low_quality"

        if decision == "drop":
            dropped_photos.append(DroppedPhoto(photo_id=photo_id, reason=drop_reason or "filtered"))
        else:
            valid_photos.append(KeptPhoto(
                photo_id=photo_id,
                decision=decision,
                rank_weight=1.0 if decision == "keep" else 0.5,
                quality_score=quality_score,
                duplicate_score=0.0 if is_duplicate else None,
                saliency_score=None,
                face_integrity_score=None,
                drop_reason=drop_reason,
                captured_at=asset.exif.captured_at if asset and asset.exif else None,
                location_cluster=None,
                embedding_ref=str(features.embedding[:10]) if features.embedding else None,
                person_ids=features.person_ids,
                scene_tags=features.scene_tags,
                orientation=asset.orientation if asset else None,
                is_duplicate=is_duplicate,
            ))

    cleaned_photo_set = CleanedPhotoSet(
        album_id=node_input.album_id,
        valid_photos=valid_photos,
        dropped_photos=dropped_photos,
        cleaning_summary={
            "input_count": len(ordered_photo_ids),
            "valid_count": len(valid_photos),
            "dropped_count": len(dropped_photos),
            "duplicate_groups": len(duplicate_groups),
        },
    )

    state.cleaned_photo_set = cleaned_photo_set
    return state