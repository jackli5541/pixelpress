from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.theme_relevance_engine import (  # noqa: E402
    QUERY_VERSION,
    SCORING_VERSION,
    relevance_signal,
)


MIN_PAIR_COUNT = 500
MIN_THEME_CATEGORIES = 8
KEEP_PRECISION_GATE = 0.90
RELEVANT_RECALL_GATE = 0.70
FALSE_EXCLUSION_GATE = 0.02
FEATURE_ORDER = (
    "raw_query_similarity",
    "expanded_query_similarity",
    "negative_similarity",
    "margin",
)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _split(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    training: list[dict[str, Any]] = []
    validation: list[dict[str, Any]] = []
    for item in records:
        album_id = str(item["album_id"])
        bucket = int(hashlib.sha256(album_id.encode("utf-8")).hexdigest()[:8], 16) % 5
        (validation if bucket == 0 else training).append(item)
    if not training or not validation:
        return records, records
    return training, validation


def _feature_vector(item: dict[str, Any]) -> list[float]:
    positive = float(item.get("positive_similarity") or 0.0)
    raw = float(item.get("raw_query_similarity", positive) or 0.0)
    expanded = float(item.get("expanded_query_similarity", positive) or 0.0)
    negative = float(item.get("negative_similarity") or 0.0)
    margin = float(item.get("margin", max(raw, expanded) - negative) or 0.0)
    return [raw, expanded, negative, margin]


def fit_logistic(records: list[dict[str, Any]]) -> dict[str, Any]:
    labeled = [(item, 1.0 if item.get("label") == "relevant" else 0.0) for item in records if item.get("label") in {"relevant", "off_theme"}]
    vectors = [_feature_vector(item) for item, _ in labeled]
    if not vectors:
        raise ValueError("theme relevance manifest has no binary labels")
    means = [sum(row[index] for row in vectors) / len(vectors) for index in range(len(FEATURE_ORDER))]
    scales = []
    for index, mean in enumerate(means):
        variance = sum((row[index] - mean) ** 2 for row in vectors) / len(vectors)
        scales.append(max(variance ** 0.5, 1e-6))
    standardized = [[(value - means[index]) / scales[index] for index, value in enumerate(row)] for row in vectors]
    weights = [0.0] * len(FEATURE_ORDER)
    positive_rate = min(1 - 1e-6, max(1e-6, sum(label for _, label in labeled) / len(labeled)))
    intercept = math.log(positive_rate / (1 - positive_rate))
    for step in range(1200):
        gradient = [0.0] * len(weights)
        intercept_gradient = 0.0
        for row, (_, label) in zip(standardized, labeled):
            logit = max(-40.0, min(40.0, intercept + sum(weight * value for weight, value in zip(weights, row))))
            error = 1.0 / (1.0 + math.exp(-logit)) - label
            intercept_gradient += error
            for index, value in enumerate(row):
                gradient[index] += error * value
        rate = 0.15 / (1.0 + step / 300.0)
        intercept -= rate * intercept_gradient / len(labeled)
        for index in range(len(weights)):
            weights[index] -= rate * (gradient[index] / len(labeled) + 0.001 * weights[index])
    return {
        "feature_order": list(FEATURE_ORDER),
        "coefficients": [round(value, 10) for value in weights],
        "intercept": round(intercept, 10),
        "feature_means": [round(value, 10) for value in means],
        "feature_scales": [round(value, 10) for value in scales],
    }


def _classifier_probability(item: dict[str, Any], classifier: dict[str, Any]) -> float:
    values = _feature_vector(item)
    normalized = [
        (value - mean) / scale
        for value, mean, scale in zip(values, classifier["feature_means"], classifier["feature_scales"])
    ]
    logit = classifier["intercept"] + sum(weight * value for weight, value in zip(classifier["coefficients"], normalized))
    return 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, logit))))


def _labeled_points(records: list[dict[str, Any]], classifier: dict[str, Any] | None = None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for item in records:
        label = str(item.get("label") or "")
        if label not in {"relevant", "off_theme"}:
            continue
        signal = _classifier_probability(item, classifier) if classifier else relevance_signal(
            float(item["positive_similarity"]),
            float(item["negative_similarity"]) if item.get("negative_similarity") is not None else None,
        )
        points.append((signal, 1.0 if label == "relevant" else 0.0))
    return sorted(points)


def fit_isotonic(records: list[dict[str, Any]], classifier: dict[str, Any] | None = None) -> tuple[list[float], list[float]]:
    grouped: dict[float, list[float]] = defaultdict(list)
    for signal, label in _labeled_points(records, classifier):
        grouped[signal].append(label)
    blocks = [
        {"left": signal, "right": signal, "weight": len(labels), "sum": sum(labels)}
        for signal, labels in sorted(grouped.items())
    ]
    index = 0
    while index < len(blocks) - 1:
        left_mean = blocks[index]["sum"] / blocks[index]["weight"]
        right_mean = blocks[index + 1]["sum"] / blocks[index + 1]["weight"]
        if left_mean <= right_mean:
            index += 1
            continue
        blocks[index] = {
            "left": blocks[index]["left"],
            "right": blocks[index + 1]["right"],
            "weight": blocks[index]["weight"] + blocks[index + 1]["weight"],
            "sum": blocks[index]["sum"] + blocks[index + 1]["sum"],
        }
        blocks.pop(index + 1)
        index = max(0, index - 1)
    signals: list[float] = []
    probabilities: list[float] = []
    for block in blocks:
        probability = block["sum"] / block["weight"]
        for signal in (block["left"], block["right"]):
            if signals and signal == signals[-1]:
                probabilities[-1] = probability
            else:
                signals.append(round(float(signal), 8))
                probabilities.append(round(float(probability), 8))
    if len(signals) == 1:
        signals = [signals[0] - 1e-6, signals[0] + 1e-6]
        probabilities = [probabilities[0], probabilities[0]]
    return signals, probabilities


def _interpolate(signal: float, xs: list[float], ys: list[float]) -> float:
    if signal <= xs[0]:
        return ys[0]
    if signal >= xs[-1]:
        return ys[-1]
    for index in range(1, len(xs)):
        if signal <= xs[index]:
            ratio = (signal - xs[index - 1]) / (xs[index] - xs[index - 1])
            return ys[index - 1] + ratio * (ys[index] - ys[index - 1])
    return ys[-1]


def _scored(records: list[dict[str, Any]], xs: list[float], ys: list[float], classifier: dict[str, Any] | None = None) -> list[tuple[float, str]]:
    result: list[tuple[float, str]] = []
    for item in records:
        signal = _classifier_probability(item, classifier) if classifier else relevance_signal(
            float(item["positive_similarity"]),
            float(item["negative_similarity"]) if item.get("negative_similarity") is not None else None,
        )
        result.append((_interpolate(signal, xs, ys), str(item["label"])))
    return result


def choose_thresholds(records: list[dict[str, Any]], xs: list[float], ys: list[float], classifier: dict[str, Any] | None = None) -> tuple[float, float]:
    scored = _scored(records, xs, ys, classifier)
    candidates = sorted({0.0, 1.0, *[score for score, _ in scored]})
    keep = 1.0
    best_recall = -1.0
    relevant_total = sum(label == "relevant" for _, label in scored)
    for threshold in candidates:
        predicted = [label for score, label in scored if score >= threshold]
        precision = _ratio(sum(label == "relevant" for label in predicted), len(predicted))
        recall = _ratio(sum(label == "relevant" for label in predicted), relevant_total)
        if precision >= KEEP_PRECISION_GATE and recall > best_recall:
            keep, best_recall = threshold, recall

    exclude = 0.0
    best_off_theme_recall = -1.0
    off_theme_total = sum(label == "off_theme" for _, label in scored)
    for threshold in candidates:
        predicted = [label for score, label in scored if score <= threshold]
        false_exclusion = _ratio(sum(label == "relevant" for label in predicted), relevant_total)
        off_theme_recall = _ratio(sum(label == "off_theme" for label in predicted), off_theme_total)
        if false_exclusion <= FALSE_EXCLUSION_GATE and off_theme_recall > best_off_theme_recall:
            exclude, best_off_theme_recall = threshold, off_theme_recall
    return round(exclude, 8), round(keep, 8)


def metrics(records: list[dict[str, Any]], xs: list[float], ys: list[float], exclude: float, keep: float, classifier: dict[str, Any] | None = None) -> dict[str, float]:
    scored = _scored(records, xs, ys, classifier)
    kept = [label for score, label in scored if score >= keep]
    excluded = [label for score, label in scored if score <= exclude]
    relevant_total = sum(label == "relevant" for _, label in scored)
    return {
        "candidate_precision": _ratio(sum(label == "relevant" for label in kept), len(kept)),
        "relevant_recall": _ratio(sum(label == "relevant" for label in kept), relevant_total),
        "false_exclusion_rate": _ratio(sum(label == "relevant" for label in excluded), relevant_total),
        "review_rate": _ratio(sum(exclude < score < keep for score, _ in scored), len(scored)),
    }


def evaluate(records: list[dict[str, Any]], *, dataset_version: str) -> dict[str, Any]:
    if not records:
        raise ValueError("theme relevance manifest is empty")
    training, validation = _split(records)
    classifier = fit_logistic(training)
    xs, ys = fit_isotonic(training, classifier)
    exclude, keep = choose_thresholds(training, xs, ys, classifier)
    validation_metrics = metrics(validation, xs, ys, exclude, keep, classifier)
    categories = {str(item.get("theme_category") or "") for item in records if item.get("theme_category")}
    metadata = {
        (
            str(item.get("provider") or ""),
            str(item.get("model") or ""),
            int(item.get("dimension") or 0),
            str(item.get("query_version") or ""),
            str(item.get("scoring_version") or ""),
        )
        for item in records
    }
    metadata_valid = len(metadata) == 1 and all(metadata) and all(next(iter(metadata)))
    labels_valid = all(item.get("label") in {"relevant", "uncertain", "off_theme"} for item in records)
    annotations_valid = all(len(set(item.get("annotators") or [])) >= 2 for item in records)
    requirements_met = (
        len(records) >= MIN_PAIR_COUNT
        and len(categories) >= MIN_THEME_CATEGORIES
        and metadata_valid
        and labels_valid
        and annotations_valid
        and exclude < keep
    )
    quality_met = (
        validation_metrics["candidate_precision"] >= KEEP_PRECISION_GATE
        and validation_metrics["relevant_recall"] >= RELEVANT_RECALL_GATE
        and validation_metrics["false_exclusion_rate"] <= FALSE_EXCLUSION_GATE
    )
    first = records[0] if records else {}
    return {
        "version": f"{dataset_version}-calibration-v1",
        "dataset_version": dataset_version,
        "provider": str(first.get("provider") or ""),
        "model": str(first.get("model") or ""),
        "dimension": int(first.get("dimension") or 0),
        "query_version": str(first.get("query_version") or QUERY_VERSION),
        "scoring_version": str(first.get("scoring_version") or SCORING_VERSION),
        "enabled": requirements_met and quality_met,
        "classifier": classifier,
        "mapping": {"signal": xs, "probability": ys},
        "decision_thresholds": {
            "exclude_max_probability": exclude,
            "keep_min_probability": keep,
        },
        "metrics": validation_metrics,
        "requirements": {
            "pair_count": len(records),
            "minimum_pair_count": MIN_PAIR_COUNT,
            "theme_category_count": len(categories),
            "minimum_theme_category_count": MIN_THEME_CATEGORIES,
            "single_embedding_configuration": metadata_valid,
            "labels_valid": labels_valid,
            "dual_annotation_valid": annotations_valid,
            "requirements_met": requirements_met,
        },
        "gates": {
            "candidate_precision": KEEP_PRECISION_GATE,
            "relevant_recall": RELEVANT_RECALL_GATE,
            "false_exclusion_rate": FALSE_EXCLUSION_GATE,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate and evaluate cross-modal theme relevance")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate(records, dataset_version=args.dataset_version)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["enabled"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
