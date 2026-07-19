"""Evaluate ordered chapter assignments against manually reviewed labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score


def _boundaries(labels: list[str]) -> set[int]:
    return {index for index, (left, right) in enumerate(zip(labels, labels[1:]), 1) if left != right}


def evaluate(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        raise ValueError("manifest must contain at least one item")
    expected = [str(item["expected_chapter"]) for item in items]
    predicted = [str(item["predicted_chapter"]) for item in items]
    expected_boundaries = _boundaries(expected)
    predicted_boundaries = _boundaries(predicted)
    matched = len(expected_boundaries & predicted_boundaries)
    precision = matched / len(predicted_boundaries) if predicted_boundaries else float(not expected_boundaries)
    recall = matched / len(expected_boundaries) if expected_boundaries else float(not predicted_boundaries)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    expected_count = len(set(expected))
    predicted_count = len(set(predicted))
    return {
        "photo_count": len(items),
        "expected_chapter_count": expected_count,
        "predicted_chapter_count": predicted_count,
        "boundary_precision": round(precision, 6),
        "boundary_recall": round(recall, 6),
        "boundary_f1": round(f1, 6),
        "adjusted_rand_index": round(float(adjusted_rand_score(expected, predicted)), 6),
        "normalized_mutual_info": round(float(normalized_mutual_info_score(expected, predicted)), 6),
        "oversegmentation_ratio": round(predicted_count / max(expected_count, 1), 6),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        raise ValueError("manifest must be a list or contain an items list")
    result = evaluate(items)
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)


if __name__ == "__main__":
    main()
