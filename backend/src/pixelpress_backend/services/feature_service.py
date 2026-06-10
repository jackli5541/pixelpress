from __future__ import annotations

import io
import logging
from typing import Any

from PIL import Image

from pixelpress_backend.algorithms.feature_extraction import (
    DuplicateDetector,
    FeatureExtractor,
)
from pixelpress_backend.models.domain import PhotoFeatures, PhotoQualityScores

logger = logging.getLogger(__name__)


class FeatureService:
    @staticmethod
    def extract_features_from_bytes(photo_id: str, image_bytes: bytes) -> PhotoFeatures:
        try:
            img = Image.open(io.BytesIO(image_bytes))
            raw_features = FeatureExtractor.extract_features(photo_id, img)
            return FeatureService._convert_to_domain(raw_features)
        except Exception as e:
            logger.error(f"Failed to extract features for {photo_id}: {e}")
            return PhotoFeatures(
                feature_status="failed",
                embedding_model_version="clip-vit-b-32",
            )

    @staticmethod
    def extract_features_from_path(photo_id: str, file_path: str) -> PhotoFeatures:
        try:
            img = Image.open(file_path)
            raw_features = FeatureExtractor.extract_features(photo_id, img)
            return FeatureService._convert_to_domain(raw_features)
        except Exception as e:
            logger.error(f"Failed to extract features from {file_path}: {e}")
            return PhotoFeatures(
                feature_status="failed",
                embedding_model_version="clip-vit-b-32",
            )

    @staticmethod
    def batch_extract_features(photo_items: list[dict[str, Any]]) -> list[PhotoFeatures]:
        results = []
        for item in photo_items:
            photo_id = item.get("photo_id", "")
            if "image_bytes" in item:
                features = FeatureService.extract_features_from_bytes(photo_id, item["image_bytes"])
            elif "file_path" in item:
                features = FeatureService.extract_features_from_path(photo_id, item["file_path"])
            else:
                features = PhotoFeatures(
                    feature_status="pending",
                    embedding_model_version="pixelpress-clip-v1",
                )
            results.append(features)
        return results

    @staticmethod
    def find_duplicate_groups(photo_features: list[dict[str, Any]]) -> dict[str, list[str]]:
        return DuplicateDetector.find_duplicates(photo_features)

    @staticmethod
    def _convert_to_domain(raw: dict[str, Any]) -> PhotoFeatures:
        quality = raw.get("quality_scores", {})
        return PhotoFeatures(
            embedding=raw.get("embedding"),
            embedding_model_version=raw.get("embedding_model_version"),
            face_boxes=[
                {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"]}
                for box in raw.get("face_boxes", [])
            ],
            face_ids=raw.get("face_ids", []),
            subject_boxes=[
                {"x": box["x"], "y": box["y"], "w": box["w"], "h": box["h"], "label": box.get("label")}
                for box in raw.get("subject_boxes", [])
            ],
            saliency_map=raw.get("saliency_map"),
            saliency_model_version=raw.get("saliency_model_version"),
            quality_scores=PhotoQualityScores(
                sharpness=quality.get("sharpness"),
                exposure=quality.get("exposure"),
                blur=quality.get("blur"),
                noise=quality.get("noise"),
                face_integrity=quality.get("face_integrity"),
                overall=quality.get("overall"),
            ),
            perceptual_hash=raw.get("perceptual_hash"),
            duplicate_group_id=raw.get("duplicate_group_id"),
            scene_tags=raw.get("scene_tags", []),
            person_ids=raw.get("person_ids", []),
            dominant_color=raw.get("dominant_color"),
            feature_extracted_at=raw.get("feature_extracted_at"),
            feature_status=raw.get("feature_status"),
        )