from __future__ import annotations

from dataclasses import dataclass
from math import log, sqrt

import numpy as np
from PIL import Image


SHARPNESS_SCALES = (1024, 512)
BLOCK_GRID_SIZE = 8
MIN_TEXTURE_ENTROPY = 2.0
MIN_INFORMATIVE_TILE_RATIO = 0.08
HARD_REJECT_RECOGNIZABILITY_1024 = 0.16
HARD_REJECT_RECOGNIZABILITY_512 = 0.18
HARD_REJECT_TILE_P90 = 0.18
WARNING_RECOGNIZABILITY = 0.45


@dataclass(frozen=True, slots=True)
class ScaleSharpness:
    long_edge: int
    laplacian: float
    tenengrad: float
    laplacian_score: float
    tenengrad_score: float
    recognizability: float
    edge_density: float
    entropy: float
    informative_tile_ratio: float
    tile_p10: float
    tile_p50: float
    tile_p90: float
    motion_anisotropy: float
    motion_blur_score: float


def sharpness_variance(gray: np.ndarray) -> float:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        return 0.0
    center = gray[1:-1, 1:-1]
    laplacian = gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * center
    return float(np.var(laplacian))


def score_laplacian(variance: float) -> float:
    if variance <= 30:
        return max(0.0, variance / 30 * 0.25)
    if variance <= 80:
        return 0.25 + (variance - 30) / 50 * 0.25
    return min(1.0, 0.5 + max(0.0, log(variance / 80)) / log(10) * 0.5)


def _gradient_components(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if gray.shape[0] < 3 or gray.shape[1] < 3:
        empty = np.zeros_like(gray, dtype=np.float64)
        return empty, empty
    padded = np.pad(gray.astype(np.float64), 1, mode="edge")
    gx = (
        -padded[:-2, :-2]
        + padded[:-2, 2:]
        - 2 * padded[1:-1, :-2]
        + 2 * padded[1:-1, 2:]
        - padded[2:, :-2]
        + padded[2:, 2:]
    )
    gy = (
        -padded[:-2, :-2]
        - 2 * padded[:-2, 1:-1]
        - padded[:-2, 2:]
        + padded[2:, :-2]
        + 2 * padded[2:, 1:-1]
        + padded[2:, 2:]
    )
    return gx, gy


def _tenengrad(gx: np.ndarray, gy: np.ndarray) -> float:
    return float(np.mean(gx * gx + gy * gy)) if gx.size else 0.0


def _score_tenengrad(value: float) -> float:
    return min(1.0, sqrt(max(0.0, value) / 24000.0))


def _entropy(gray: np.ndarray) -> float:
    if not gray.size:
        return 0.0
    histogram, _ = np.histogram(gray, bins=64, range=(0, 256))
    probabilities = histogram.astype(np.float64) / max(1, int(histogram.sum()))
    nonzero = probabilities[probabilities > 0]
    return float(-np.sum(nonzero * np.log2(nonzero)))


def _recognizability(laplacian_score: float, tenengrad_score: float) -> float:
    return max(0.0, min(1.0, laplacian_score * 0.6 + tenengrad_score * 0.4))


def _tile_metrics(gray: np.ndarray) -> tuple[float, float, float, float]:
    height, width = gray.shape
    values: list[float] = []
    informative = 0
    total = 0
    for row in range(BLOCK_GRID_SIZE):
        top = row * height // BLOCK_GRID_SIZE
        bottom = (row + 1) * height // BLOCK_GRID_SIZE
        for column in range(BLOCK_GRID_SIZE):
            left = column * width // BLOCK_GRID_SIZE
            right = (column + 1) * width // BLOCK_GRID_SIZE
            tile = gray[top:bottom, left:right]
            if min(tile.shape, default=0) < 3:
                continue
            total += 1
            gx, gy = _gradient_components(tile)
            magnitude = np.hypot(gx, gy)
            edge_density = float(np.mean(magnitude >= 80.0))
            entropy = _entropy(tile)
            if entropy < MIN_TEXTURE_ENTROPY and edge_density < 0.01:
                continue
            informative += 1
            laplacian_score = score_laplacian(sharpness_variance(tile))
            tenengrad_score = _score_tenengrad(_tenengrad(gx, gy))
            values.append(_recognizability(laplacian_score, tenengrad_score))
    ratio = informative / max(1, total)
    if not values:
        return ratio, 0.0, 0.0, 0.0
    p10, p50, p90 = np.percentile(np.asarray(values, dtype=np.float64), [10, 50, 90])
    return ratio, float(p10), float(p50), float(p90)


def _motion_anisotropy(gx: np.ndarray, gy: np.ndarray) -> float:
    magnitude = np.hypot(gx, gy)
    mask = magnitude >= 40.0
    if int(mask.sum()) < 64:
        return 0.0
    orientations = (np.arctan2(gy[mask], gx[mask]) + np.pi) % np.pi
    histogram, _ = np.histogram(orientations, bins=18, range=(0, np.pi), weights=magnitude[mask])
    total = float(histogram.sum())
    if total <= 0:
        return 0.0
    distribution = histogram.astype(np.float64) / total
    uniform = 1.0 / len(distribution)
    return max(0.0, min(1.0, float(np.max(distribution) - uniform) / (1.0 - uniform)))


def _resize_gray(image: Image.Image, long_edge: int) -> np.ndarray:
    resized = image.convert("L")
    if max(resized.size) > long_edge:
        scale = long_edge / max(resized.size)
        target = (max(1, round(resized.width * scale)), max(1, round(resized.height * scale)))
        resized = resized.resize(target, Image.Resampling.LANCZOS)
    return np.asarray(resized, dtype=np.float64)


def _analyze_scale(image: Image.Image, long_edge: int) -> ScaleSharpness:
    gray = _resize_gray(image, long_edge)
    gx, gy = _gradient_components(gray)
    magnitude = np.hypot(gx, gy)
    laplacian = sharpness_variance(gray)
    tenengrad = _tenengrad(gx, gy)
    laplacian_score = score_laplacian(laplacian)
    tenengrad_score = _score_tenengrad(tenengrad)
    recognizability = _recognizability(laplacian_score, tenengrad_score)
    edge_density = float(np.mean(magnitude >= 80.0)) if magnitude.size else 0.0
    entropy = _entropy(gray)
    informative_ratio, tile_p10, tile_p50, tile_p90 = _tile_metrics(gray)
    anisotropy = _motion_anisotropy(gx, gy)
    motion_blur_score = anisotropy * (1.0 - recognizability)
    return ScaleSharpness(
        long_edge=max(gray.shape, default=0),
        laplacian=laplacian,
        tenengrad=tenengrad,
        laplacian_score=laplacian_score,
        tenengrad_score=tenengrad_score,
        recognizability=recognizability,
        edge_density=edge_density,
        entropy=entropy,
        informative_tile_ratio=informative_ratio,
        tile_p10=tile_p10,
        tile_p50=tile_p50,
        tile_p90=tile_p90,
        motion_anisotropy=anisotropy,
        motion_blur_score=motion_blur_score,
    )


def analyze_sharpness(image: Image.Image) -> dict[str, object]:
    scales = {scale: _analyze_scale(image, scale) for scale in SHARPNESS_SCALES}
    primary = scales[1024]
    secondary = scales[512]
    texture_sufficient = (
        max(primary.entropy, secondary.entropy) >= MIN_TEXTURE_ENTROPY
        and max(primary.informative_tile_ratio, secondary.informative_tile_ratio) >= MIN_INFORMATIVE_TILE_RATIO
    )
    motion_evidence = max(primary.motion_blur_score, secondary.motion_blur_score) >= 0.30
    defocus_evidence = max(primary.tenengrad_score, secondary.tenengrad_score) < 0.15
    hard_reject = bool(
        texture_sufficient
        and primary.tile_p90 < HARD_REJECT_TILE_P90
        and primary.recognizability < HARD_REJECT_RECOGNIZABILITY_1024
        and secondary.recognizability < HARD_REJECT_RECOGNIZABILITY_512
        and (motion_evidence or defocus_evidence)
    )
    if hard_reject:
        severity = "severe"
    elif not texture_sufficient:
        severity = "undetermined"
    elif min(primary.recognizability, secondary.recognizability) < WARNING_RECOGNIZABILITY:
        severity = "warning"
    else:
        severity = "ok"

    def serialize(item: ScaleSharpness) -> dict[str, float | int]:
        return {
            "long_edge": item.long_edge,
            "laplacian": round(item.laplacian, 3),
            "tenengrad": round(item.tenengrad, 3),
            "laplacian_score": round(item.laplacian_score, 4),
            "tenengrad_score": round(item.tenengrad_score, 4),
            "recognizability": round(item.recognizability, 4),
            "edge_density": round(item.edge_density, 4),
            "entropy": round(item.entropy, 4),
            "informative_tile_ratio": round(item.informative_tile_ratio, 4),
            "tile_p10": round(item.tile_p10, 4),
            "tile_p50": round(item.tile_p50, 4),
            "tile_p90": round(item.tile_p90, 4),
            "motion_anisotropy": round(item.motion_anisotropy, 4),
            "motion_blur_score": round(item.motion_blur_score, 4),
        }

    return {
        "score": round((primary.recognizability + secondary.recognizability) / 2, 4),
        "severity": severity,
        "hard_reject": hard_reject,
        "hard_reject_reason": "unrecoverable_blur" if hard_reject else None,
        "texture_sufficient": texture_sufficient,
        "motion_blur_suspected": motion_evidence,
        "scales": {str(scale): serialize(item) for scale, item in scales.items()},
    }


class TechnicalFeatureExtractor:
    version = "technical-v3"

    def extract_sharpness(self, image: Image.Image) -> dict[str, object]:
        return analyze_sharpness(image)
