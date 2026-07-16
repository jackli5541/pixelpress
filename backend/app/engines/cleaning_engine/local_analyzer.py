from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from math import cos, log, pi, sqrt
from typing import Any

import numpy as np
from PIL import Image, ImageOps


ANALYSIS_MAX_EDGE = 1024
PHASH_SOURCE_SIZE = 32
PHASH_HASH_SIZE = 8
CLEAR_DISCARD_MIN_SEVERE_ISSUES = 2
CLEAR_DISCARD_SCORE_THRESHOLD = 3.0
REVIEW_SCORE_THRESHOLD = 5.0


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


def _score_sharpness(variance: float) -> float:
    if variance <= 30:
        return max(0.0, variance / 30 * 0.25)
    if variance <= 80:
        return 0.25 + (variance - 30) / 50 * 0.25
    return min(1.0, 0.5 + max(0.0, log(variance / 80)) / log(10) * 0.5)


def _score_exposure(mean: float, shadow_clip: float, highlight_clip: float, dynamic_range: float) -> float:
    if mean < 0.5:
        mean_score = min(1.0, mean / 0.35)
    else:
        mean_score = min(1.0, (1.0 - mean) / 0.35)
    clipping_penalty = min(0.75, max(shadow_clip, highlight_clip) * 1.5)
    range_factor = min(1.0, max(0.0, dynamic_range / 0.55))
    return max(0.0, min(1.0, mean_score * (1.0 - clipping_penalty) * (0.65 + 0.35 * range_factor)))


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


def _sharpness_variance(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    center = gray[1:-1, 1:-1]
    laplacian = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * center
    return float(np.var(laplacian))


def _color_histogram(rgb: np.ndarray) -> list[float]:
    values: list[float] = []
    for channel in range(3):
        hist, _ = np.histogram(rgb[:, :, channel], bins=16, range=(0, 256))
        normalized = hist.astype(np.float64) / max(1, hist.sum())
        values.extend(round(float(item), 6) for item in normalized)
    return values


def _quality_suggestion(quality_score: float, severe_count: int) -> tuple[str, float, bool]:
    clear_discard = severe_count >= CLEAR_DISCARD_MIN_SEVERE_ISSUES and quality_score < CLEAR_DISCARD_SCORE_THRESHOLD
    if clear_discard:
        return "remove", 0.9, True
    if severe_count >= 1 or quality_score < REVIEW_SCORE_THRESHOLD:
        return "review", 0.75, False
    return "keep", 0.9, False


class LocalPhotoAnalyzer:
    def __init__(self, version: str) -> None:
        self.version = version

    def analyze(self, content: bytes, photo_meta: dict[str, Any]) -> dict[str, Any]:
        with Image.open(BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")

        width, height = image.size
        analysis_image = image.copy()
        analysis_image.thumbnail((ANALYSIS_MAX_EDGE, ANALYSIS_MAX_EDGE), Image.Resampling.LANCZOS)
        rgb = np.asarray(analysis_image, dtype=np.uint8)
        gray = np.asarray(analysis_image.convert("L"), dtype=np.float64)
        luminance = gray / 255.0

        sharpness_raw = _sharpness_variance(gray)
        sharpness_score = _score_sharpness(sharpness_raw)
        luminance_mean = float(np.mean(luminance))
        p05, p95 = (float(value) for value in np.percentile(luminance, [5, 95]))
        shadow_clip = float(np.mean(luminance <= 0.02))
        highlight_clip = float(np.mean(luminance >= 0.98))
        dynamic_range = p95 - p05
        exposure_score = _score_exposure(luminance_mean, shadow_clip, highlight_clip, dynamic_range)
        min_side = min(width, height)
        resolution_score = min(1.0, min_side / 1600)

        sharpness_severity = _severity(sharpness_raw, 80, 30)
        exposure_severity = "ok"
        if luminance_mean < 0.08 or luminance_mean > 0.92 or max(shadow_clip, highlight_clip) > 0.50:
            exposure_severity = "severe"
        elif luminance_mean < 0.15 or luminance_mean > 0.85 or max(shadow_clip, highlight_clip) > 0.25:
            exposure_severity = "warning"
        resolution_severity = _severity(float(min_side), 800, 320)

        issues: list[str] = []
        if sharpness_severity != "ok":
            issues.append(f"sharpness_{sharpness_severity}")
        if exposure_severity != "ok":
            issues.append(f"exposure_{exposure_severity}")
        if resolution_severity != "ok":
            issues.append(f"resolution_{resolution_severity}")

        quality_score = round((sharpness_score * 0.5 + exposure_score * 0.3 + resolution_score * 0.2) * 10, 2)
        severe_count = sum(value == "severe" for value in (sharpness_severity, exposure_severity, resolution_severity))
        suggestion, confidence, clear_discard = _quality_suggestion(quality_score, severe_count)

        return {
            "photo_id": photo_meta.get("id"),
            "content_sha256": sha256(content).hexdigest(),
            "perceptual_hash": _perceptual_hash(analysis_image),
            "analysis_version": self.version,
            "quality_score": quality_score,
            "suggestion": suggestion,
            "confidence": confidence,
            "clear_discard": clear_discard,
            "issues": issues,
            "features": {
                "sharpness": {"variance": round(sharpness_raw, 3), "score": round(sharpness_score, 4), "severity": sharpness_severity},
                "exposure": {
                    "mean": round(luminance_mean, 4),
                    "p05": round(p05, 4),
                    "p95": round(p95, 4),
                    "shadow_clip": round(shadow_clip, 4),
                    "highlight_clip": round(highlight_clip, 4),
                    "dynamic_range": round(dynamic_range, 4),
                    "score": round(exposure_score, 4),
                    "severity": exposure_severity,
                },
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
            },
        }
