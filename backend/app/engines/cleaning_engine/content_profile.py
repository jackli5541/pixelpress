from __future__ import annotations

import re
from typing import Any

import numpy as np
from PIL import Image


SCREENSHOT_NAME_PATTERN = re.compile(
    r"(?:screenshot|screen[ _-]?shot|snipaste|snipping[ _-]?tool|"
    r"\u5c4f\u5e55\u622a\u56fe|\u5c4f\u5e55\u5feb\u7167|\u622a\u56fe|\u622a\u5c4f|\u30b9\u30af\u30ea\u30fc\u30f3\u30b7\u30e7\u30c3\u30c8)",
    re.IGNORECASE,
)


def _profile_statistics(image: Image.Image) -> tuple[float, float, float]:
    sample = image.copy()
    sample.thumbnail((768, 768), Image.Resampling.BILINEAR)
    rgb = np.asarray(sample.convert("RGB"), dtype=np.int16)
    if rgb.size == 0 or min(rgb.shape[:2]) < 2:
        return 0.0, 0.0, 0.0

    horizontal_delta = np.max(np.abs(np.diff(rgb, axis=1)), axis=2)
    vertical_delta = np.max(np.abs(np.diff(rgb, axis=0)), axis=2)
    flat_ratio = float(
        (np.mean(horizontal_delta <= 3) + np.mean(vertical_delta <= 3)) / 2
    )

    gray = np.asarray(sample.convert("L"), dtype=np.float64)
    gradient_y, gradient_x = np.gradient(gray)
    magnitude = np.hypot(gradient_x, gradient_y)
    edge_mask = magnitude >= max(8.0, float(np.percentile(magnitude, 80)))
    if np.any(edge_mask):
        angles = np.mod(np.arctan2(np.abs(gradient_y), np.abs(gradient_x)), np.pi / 2)
        distance_to_axis = np.minimum(angles, np.pi / 2 - angles)
        axis_edge_ratio = float(np.mean(distance_to_axis[edge_mask] <= np.deg2rad(12)))
    else:
        axis_edge_ratio = 0.0

    quantized = (rgb // 16).reshape(-1, 3)
    unique_ratio = float(len(np.unique(quantized, axis=0)) / max(1, len(quantized)))
    return flat_ratio, axis_edge_ratio, unique_ratio


class ContentProfileExtractor:
    version = "content-profile-v1"

    def extract(self, image: Image.Image, photo_meta: dict[str, Any]) -> dict[str, Any]:
        filename = str(photo_meta.get("filename") or "")
        content_type = str(photo_meta.get("content_type") or "").lower()
        has_camera_metadata = bool(photo_meta.get("device_model") or photo_meta.get("taken_at"))
        filename_match = bool(SCREENSHOT_NAME_PATTERN.search(filename))
        flat_ratio, axis_edge_ratio, unique_ratio = _profile_statistics(image)

        signals: list[str] = []
        if filename_match:
            signals.append("screenshot_filename")
        if content_type == "image/png":
            signals.append("png_container")
        if has_camera_metadata:
            signals.append("camera_metadata")
        if flat_ratio >= 0.55:
            signals.append("flat_regions")
        if axis_edge_ratio >= 0.62:
            signals.append("axis_aligned_edges")
        if unique_ratio <= 0.08:
            signals.append("limited_color_variation")

        ui_like = flat_ratio >= 0.55 and axis_edge_ratio >= 0.62
        if filename_match:
            capture_kind = "screenshot_or_graphic"
            confidence = 0.98
        elif content_type == "image/png" and not has_camera_metadata and ui_like:
            capture_kind = "screenshot_or_graphic"
            confidence = 0.86
        elif has_camera_metadata:
            capture_kind = "camera_photo"
            confidence = 0.92
        else:
            capture_kind = "unknown"
            confidence = 0.5

        if capture_kind == "camera_photo":
            visual_domain = "photographic"
        elif capture_kind == "screenshot_or_graphic" and flat_ratio >= 0.68 and unique_ratio <= 0.08:
            visual_domain = "illustration"
        elif capture_kind == "screenshot_or_graphic":
            visual_domain = "mixed"
        elif flat_ratio >= 0.72 and unique_ratio <= 0.06:
            visual_domain = "illustration"
            confidence = max(confidence, 0.72)
        else:
            visual_domain = "unknown"

        return {
            "version": self.version,
            "capture_kind": capture_kind,
            "visual_domain": visual_domain,
            "confidence": round(confidence, 4),
            "signals": signals,
            "statistics": {
                "flat_region_ratio": round(flat_ratio, 4),
                "axis_edge_ratio": round(axis_edge_ratio, 4),
                "quantized_unique_ratio": round(unique_ratio, 4),
            },
        }
