from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from math import cos, pi, sqrt
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app.engines.cleaning_engine.content_profile import ContentProfileExtractor
from app.engines.cleaning_engine.exposure_analyzer import ExposureFeatureExtractor
from app.engines.cleaning_engine.technical_analyzer import TechnicalFeatureExtractor


ANALYSIS_MAX_EDGE = 1024
PHASH_SOURCE_SIZE = 32
PHASH_HASH_SIZE = 8
@lru_cache(maxsize=1)
def _dct_matrix() -> np.ndarray:
    matrix = np.empty((PHASH_SOURCE_SIZE, PHASH_SOURCE_SIZE), dtype=np.float64)
    scale0 = sqrt(1 / PHASH_SOURCE_SIZE)
    scale = sqrt(2 / PHASH_SOURCE_SIZE)
    for frequency in range(PHASH_SOURCE_SIZE):
        factor = scale0 if frequency == 0 else scale
        for position in range(PHASH_SOURCE_SIZE):
            matrix[frequency, position] = factor * cos(pi * (2 * position + 1) * frequency / (2 * PHASH_SOURCE_SIZE))
    return matrix


def _severity(value: float, warning: float, severe: float, *, lower_is_worse: bool = True) -> str:
    if lower_is_worse:
        if value < severe:
            return "severe"
        if value < warning:
            return "warning"
    else:
        if value > severe:
            return "severe"
        if value > warning:
            return "warning"
    return "ok"


def _orientation(width: int, height: int) -> str:
    ratio = width / max(height, 1)
    if ratio > 1.1:
        return "landscape"
    if ratio < 1 / 1.1:
        return "portrait"
    return "square"


def _perceptual_hash(image: Image.Image) -> str:
    resized = image.convert("L").resize((PHASH_SOURCE_SIZE, PHASH_SOURCE_SIZE), Image.Resampling.LANCZOS)
    pixels = np.asarray(resized, dtype=np.float64)
    matrix = _dct_matrix()
    transformed = matrix @ pixels @ matrix.T
    low_frequency = transformed[:PHASH_HASH_SIZE, :PHASH_HASH_SIZE].copy()
    median = float(np.median(low_frequency.flatten()[1:]))
    bits = low_frequency.flatten() > median
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return f"{value:016x}"


def _color_histogram(rgb: np.ndarray) -> list[float]:
    values: list[float] = []
    for channel in range(3):
        hist, _ = np.histogram(rgb[:, :, channel], bins=16, range=(0, 256))
        normalized = hist.astype(np.float64) / max(1, hist.sum())
        values.extend(round(float(item), 6) for item in normalized)
    return values


def _quality_suggestion(*, hard_reject: bool, high_value_face_risk: bool) -> tuple[str, float, bool]:
    if hard_reject:
        return "remove", 0.99, True
    if high_value_face_risk:
        return "review", 0.85, False
    return "keep", 0.9, False


class LocalPhotoAnalyzer:
    def __init__(self, version: str, *, face_analyzer: Any | None = None) -> None:
        self.version = version
        self.face_analyzer = face_analyzer
        self.content_profile_extractor = ContentProfileExtractor()
        self.exposure_extractor = ExposureFeatureExtractor()
        self.technical_extractor = TechnicalFeatureExtractor()

    def analyze(self, content: bytes, photo_meta: dict[str, Any]) -> dict[str, Any]:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")

        width, height = image.size
        analysis_image = image.copy()
        analysis_image.thumbnail((ANALYSIS_MAX_EDGE, ANALYSIS_MAX_EDGE), Image.Resampling.LANCZOS)
        rgb = np.asarray(analysis_image, dtype=np.uint8)

        content_profile = self.content_profile_extractor.extract(image, photo_meta)
        sharpness = self.technical_extractor.extract_sharpness(image)
        sharpness_score = float(sharpness["score"])
        exposure = self.exposure_extractor.extract(
            image,
            applicable=(
                content_profile["capture_kind"] != "screenshot_or_graphic"
                and content_profile["visual_domain"] != "illustration"
            ),
        )
        min_side = min(width, height)
        resolution_score = min(1.0, min_side / 1600)

        sharpness_severity = str(sharpness["severity"])
        face_features = (
            self.face_analyzer.analyze(image, content_profile=content_profile)
            if self.face_analyzer is not None
            else None
        )
        face_analysis_failed = bool(
            face_features
            and not face_features.get("available")
            and not face_features.get("disabled")
        )
        hard_reject = bool(sharpness.get("hard_reject"))
        if hard_reject and face_analysis_failed:
            hard_reject = False
            sharpness_severity = "warning"
            sharpness["hard_reject"] = False
            sharpness["hard_reject_reason"] = None
            sharpness["severity"] = "warning"
        elif hard_reject and face_features and face_features.get("detected_count"):
            primary_face = max(face_features.get("items") or [], key=lambda item: int(item.get("min_side_px") or 0), default=None)
            primary_clarity = primary_face.get("clarity") if primary_face else None
            if not primary_clarity or not primary_clarity.get("hard_reject"):
                hard_reject = False
                sharpness_severity = "warning"
                sharpness["hard_reject"] = False
                sharpness["hard_reject_reason"] = None
                sharpness["severity"] = "warning"
        exposure_severity = str(exposure["severity"])
        resolution_severity = _severity(float(min_side), 800, 320)

        issues: list[str] = []
        if sharpness_severity != "ok":
            issues.append(f"sharpness_{sharpness_severity}")
        if exposure_severity in {"warning", "severe"}:
            issues.append(f"exposure_{exposure_severity}")
        if resolution_severity != "ok":
            issues.append(f"resolution_{resolution_severity}")
        if face_analysis_failed:
            issues.append("face_analysis_failed")
        if face_features and face_features.get("available"):
            aggregate = face_features.get("aggregate") or {}
            if aggregate.get("high_value_edge_crop_count"):
                issues.append("face_edge_crop_suspected")
            if aggregate.get("high_value_closed_eye_count"):
                issues.append("closed_eyes_suspected")
            if aggregate.get("high_value_occlusion_count"):
                issues.append("face_occlusion_suspected")
            if aggregate.get("high_value_blur_count"):
                issues.append("face_blur_suspected")
            if face_features.get("pose", {}).get("body_crop_suspected_count"):
                issues.append("body_crop_suspected")

        sharpness_quality_score = 0.75 if sharpness_severity == "undetermined" else sharpness_score
        exposure_score = exposure.get("score")
        if exposure_score is None:
            quality_score = round((sharpness_quality_score * 0.65 + resolution_score * 0.35) * 10, 2)
            quality_profile = "graphic"
        else:
            quality_score = round((sharpness_quality_score * 0.5 + float(exposure_score) * 0.3 + resolution_score * 0.2) * 10, 2)
            quality_profile = "photographic"
        face_review_issues = {
            "face_edge_crop_suspected",
            "closed_eyes_suspected",
            "face_occlusion_suspected",
            "face_blur_suspected",
            "body_crop_suspected",
        }
        suggestion, confidence, clear_discard = _quality_suggestion(
            hard_reject=hard_reject,
            high_value_face_risk=bool(face_review_issues.intersection(issues)),
        )

        return {
            "photo_id": photo_meta.get("id"),
            "content_sha256": sha256(content).hexdigest(),
            "perceptual_hash": _perceptual_hash(analysis_image),
            "analysis_version": self.version,
            "quality_score": quality_score,
            "suggestion": suggestion,
            "confidence": confidence,
            "clear_discard": clear_discard,
            "hard_reject": hard_reject,
            "hard_reject_reason": "unrecoverable_blur" if hard_reject else None,
            "issues": issues,
            "features": {
                "versions": {
                    "content_profile": self.content_profile_extractor.version,
                    "technical": "technical-v3",
                    "exposure": self.exposure_extractor.version,
                    "policy": "cleaning-policy-v3",
                },
                "content_profile": content_profile,
                "quality_profile": quality_profile,
                "sharpness": {
                    **sharpness,
                    "variance": sharpness.get("scales", {}).get("1024", {}).get("laplacian"),
                },
                "exposure": exposure,
                "resolution": {
                    "width": width,
                    "height": height,
                    "megapixels": round(width * height / 1_000_000, 3),
                    "min_side": min_side,
                    "score": round(resolution_score, 4),
                    "severity": resolution_severity,
                },
                "composition": {"orientation": _orientation(width, height), "aspect_ratio": round(width / max(height, 1), 5)},
                "color_histogram": _color_histogram(rgb),
                **({"faces": face_features} if face_features is not None else {}),
            },
        }
