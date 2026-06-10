from __future__ import annotations

from datetime import datetime
from typing import Any

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


class FeatureService:
    @staticmethod
    def extract_single(photo_id: str, image_url: str | None = None) -> PhotoFeatures:
        features = PhotoFeatures(
            photo_id=photo_id,
            embedding=None,
            embedding_model_version=CLIPEmbeddingGenerator.MODEL_VERSION,
            face_boxes=[],
            face_ids=[],
            subject_boxes=[],
            saliency_map=None,
            saliency_model_version="u2net",
            quality_scores=PhotoQualityScores(),
            perceptual_hash=None,
            duplicate_group_id=None,
            scene_tags=[],
            person_ids=[],
            dominant_color=None,
            feature_extracted_at=datetime.utcnow().isoformat(),
            feature_status="ready",
        )

        if not image_url:
            features.feature_status = "partial"
            return features

        try:
            from PIL import Image
            import requests
            response = requests.get(image_url, timeout=10)
            img = Image.open(response.raw)
        except Exception:
            features.feature_status = "failed"
            return features

        width, height = img.size

        features.perceptual_hash = PerceptualHash.compute(img)
        features.embedding = CLIPEmbeddingGenerator.generate_embedding(img)
        features.saliency_map = U2NetSaliencyGenerator.generate_saliency(img)
        features.scene_tags = SceneTagGenerator.generate_tags(img)

        features.quality_scores.sharpness = ImageQualityAnalyzer.analyze_sharpness(img)
        features.quality_scores.exposure = ImageQualityAnalyzer.analyze_exposure(img)
        features.quality_scores.blur = ImageQualityAnalyzer.analyze_blur(img)
        features.quality_scores.noise = ImageQualityAnalyzer.analyze_noise(img)

        face_boxes = YOLOFaceDetector.detect(img)
        for box in face_boxes:
            features.face_boxes.append(RelativeFrame(
                x=box["x"] / width if width > 0 else 0.0,
                y=box["y"] / height if height > 0 else 0.0,
                w=box["width"] / width if width > 0 else 0.0,
                h=box["height"] / height if height > 0 else 0.0,
            ))

        if face_boxes:
            best_face = max(face_boxes, key=lambda b: b["width"] * b["height"])
            features.quality_scores.face_integrity = ImageQualityAnalyzer.compute_face_integrity(
                (best_face["x"], best_face["y"], best_face["width"], best_face["height"]),
                width,
                height,
            )

        subject_boxes = YOLOSubjectDetector.detect(img)
        for box in subject_boxes:
            features.subject_boxes.append(RelativeFrame(
                x=box["x"] / width if width > 0 else 0.0,
                y=box["y"] / height if height > 0 else 0.0,
                w=box["width"] / width if width > 0 else 0.0,
                h=box["height"] / height if height > 0 else 0.0,
            ))

        sharpness_norm = features.quality_scores.sharpness / 1000.0 if features.quality_scores.sharpness else 0.0
        exposure_score = features.quality_scores.exposure or 0.0
        face_integrity_score = features.quality_scores.face_integrity or 0.5
        blur_norm = 1.0 - (features.quality_scores.blur / 50.0 if features.quality_scores.blur else 0.0)
        noise_norm = 1.0 - (features.quality_scores.noise / 20.0 if features.quality_scores.noise else 0.0)

        features.quality_scores.overall = float(
            0.3 * min(sharpness_norm, 1.0)
            + 0.25 * exposure_score
            + 0.2 * face_integrity_score
            + 0.15 * max(blur_norm, 0.0)
            + 0.1 * max(noise_norm, 0.0)
        )

        r, g, b = img.convert("RGB").getpixel((width // 2, height // 2)) if width > 0 and height > 0 else (0, 0, 0)
        features.dominant_color = f"#{r:02x}{g:02x}{b:02x}"

        return features

    @staticmethod
    def batch_extract(photo_items: list[dict[str, Any]]) -> list[PhotoFeatures]:
        results = []
        images_for_clustering = {}

        for item in photo_items:
            features = FeatureService.extract_single(item["photo_id"], item.get("image_url"))
            results.append(features)
            if item.get("image_url"):
                try:
                    from PIL import Image
                    import requests
                    response = requests.get(item["image_url"], timeout=10)
                    images_for_clustering[item["photo_id"]] = Image.open(response.raw)
                except Exception:
                    pass

        person_cluster_map = FaceNetClusterer.cluster_faces(images_for_clustering)
        for features in results:
            if features.photo_id in person_cluster_map:
                features.person_ids.append(person_cluster_map[features.photo_id])

        features_list = [{
            "photo_id": f.photo_id,
            "perceptual_hash": f.perceptual_hash or "",
            "embedding": f.embedding or [],
        } for f in results]
        duplicate_groups = DuplicateDetector.find_duplicates(features_list)

        group_id_counter = 0
        for group in duplicate_groups:
            group_id = f"dup_group_{group_id_counter}"
            group_id_counter += 1
            for photo_id in group:
                for features in results:
                    if features.photo_id == photo_id:
                        features.duplicate_group_id = group_id
                        break

        return results

    @staticmethod
    def compute_embedding_similarity(emb1: list[float], emb2: list[float]) -> float:
        return CLIPEmbeddingGenerator.cosine_similarity(emb1, emb2)

    @staticmethod
    def compute_hash_distance(hash1: str, hash2: str) -> int:
        return PerceptualHash.hamming_distance(hash1, hash2)