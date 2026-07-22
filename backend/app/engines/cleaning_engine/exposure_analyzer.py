from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image


def _block_statistics(luminance: np.ndarray, grid_size: int = 8) -> tuple[float, float]:
    height, width = luminance.shape
    informative = 0
    clipped = 0
    total = 0
    for row in range(grid_size):
        top = row * height // grid_size
        bottom = (row + 1) * height // grid_size
        for column in range(grid_size):
            left = column * width // grid_size
            right = (column + 1) * width // grid_size
            block = luminance[top:bottom, left:right]
            if block.size == 0:
                continue
            total += 1
            dynamic_range = float(np.percentile(block, 95) - np.percentile(block, 5))
            standard_deviation = float(np.std(block))
            if dynamic_range >= 0.12 or standard_deviation >= 0.035:
                informative += 1
            if float(np.mean(block <= 0.01)) >= 0.75 or float(np.mean(block >= 0.99)) >= 0.75:
                clipped += 1
    return informative / max(1, total), clipped / max(1, total)


class ExposureFeatureExtractor:
    version = "exposure-v3"

    def extract(self, image: Image.Image, *, applicable: bool) -> dict[str, Any]:
        if not applicable:
            return {
                "version": self.version,
                "score": None,
                "severity": "not_applicable",
                "applicable": False,
            }

        sample = image.copy()
        sample.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        luminance = np.asarray(sample.convert("L"), dtype=np.float64) / 255.0
        p01, p05, p50, p95, p99 = (
            float(value) for value in np.percentile(luminance, [1, 5, 50, 95, 99])
        )
        mean = float(np.mean(luminance))
        shadow_clip = float(np.mean(luminance <= 0.01))
        highlight_clip = float(np.mean(luminance >= 0.99))
        dynamic_range = p95 - p05
        informative_ratio, clipped_block_ratio = _block_statistics(luminance)

        shadow_loss = shadow_clip >= 0.45 and p95 <= 0.35 and clipped_block_ratio >= 0.35
        highlight_loss = highlight_clip >= 0.45 and p05 >= 0.65 and clipped_block_ratio >= 0.35
        shadow_warning = shadow_clip >= 0.20 and p95 <= 0.50 and clipped_block_ratio >= 0.20
        highlight_warning = highlight_clip >= 0.20 and p05 >= 0.50 and clipped_block_ratio >= 0.20
        severity = "severe" if shadow_loss or highlight_loss else "warning" if shadow_warning or highlight_warning else "ok"

        clipping_penalty = min(0.8, max(shadow_clip, highlight_clip) * 1.2)
        information_factor = 0.65 + 0.35 * min(1.0, informative_ratio / 0.45)
        range_factor = 0.65 + 0.35 * min(1.0, dynamic_range / 0.55)
        score = max(0.0, min(1.0, (1.0 - clipping_penalty) * information_factor * range_factor))

        return {
            "version": self.version,
            "applicable": True,
            "mean": round(mean, 4),
            "p01": round(p01, 4),
            "p05": round(p05, 4),
            "p50": round(p50, 4),
            "p95": round(p95, 4),
            "p99": round(p99, 4),
            "shadow_clip": round(shadow_clip, 4),
            "highlight_clip": round(highlight_clip, 4),
            "dynamic_range": round(dynamic_range, 4),
            "informative_block_ratio": round(informative_ratio, 4),
            "clipped_block_ratio": round(clipped_block_ratio, 4),
            "score": round(score, 4),
            "severity": severity,
        }
