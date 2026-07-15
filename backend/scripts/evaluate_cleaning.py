from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.engines.cleaning_engine.service import run_cleaning  # noqa: E402

GATES = {
    "duplicate_precision": 0.98,
    "duplicate_recall": 0.90,
    "removal_precision": 0.98,
    "max_false_removal_rate": 0.005,
    "preferred_accuracy": 0.85,
}


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 1.0


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 1.0, 1.0
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt((proportion * (1 - proportion) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def _pairs(groups: list[set[str]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for group in groups:
        ordered = sorted(group)
        for left in range(len(ordered)):
            for right in range(left + 1, len(ordered)):
                pairs.add((ordered[left], ordered[right]))
    return pairs


def evaluate(records: list[dict[str, Any]], base_dir: Path) -> dict[str, Any]:
    albums: dict[str, list[dict[str, Any]]] = defaultdict(list)
    labels = {str(item["id"]): item for item in records}
    for item in records:
        path = (base_dir / item["path"]).resolve()
        albums[str(item["album_id"])].append({
            "id": str(item["id"]),
            "content": path.read_bytes(),
            "width": item.get("width"),
            "height": item.get("height"),
            "taken_at": datetime.fromisoformat(item["taken_at"]) if item.get("taken_at") else None,
            "device_model": item.get("device_model"),
            "uploaded_at": None,
        })

    predicted_groups: list[set[str]] = []
    preferred_predictions: dict[frozenset[str], str] = {}
    suggestions: dict[str, str] = {}
    auto_excluded: set[str] = set()
    for album_id, photos in albums.items():
        result = run_cleaning(album_id, photos, version="evaluation", auto_exclude_exact=True)
        for item in result["per_photo"]:
            suggestions[item["photo_id"]] = item["suggestion"]
            if item.get("auto_excluded"):
                auto_excluded.add(item["photo_id"])
        for group in result["groups"]:
            member_ids = {member["photo_id"] for member in group["members"]}
            predicted_groups.append(member_ids)
            preferred_predictions[frozenset(member_ids)] = group["preferred_photo_id"]

    truth_cluster_members: dict[str, set[str]] = defaultdict(set)
    for item in records:
        if item.get("duplicate_cluster_id"):
            truth_cluster_members[str(item["duplicate_cluster_id"])].add(str(item["id"]))
    truth_groups = [members for members in truth_cluster_members.values() if len(members) >= 2]
    predicted_pairs = _pairs(predicted_groups)
    truth_pairs = _pairs(truth_groups)
    true_pairs = predicted_pairs & truth_pairs

    remove_predictions = {photo_id for photo_id, suggestion in suggestions.items() if suggestion == "remove"}
    should_remove = {photo_id for photo_id, item in labels.items() if item.get("should_remove") is True}
    must_keep = {photo_id for photo_id, item in labels.items() if item.get("quality_label") == "must_keep"}
    baseline_excluded = {photo_id for photo_id, item in labels.items() if item.get("baseline_excluded") is True}

    preferred_total = 0
    preferred_correct = 0
    for truth_group in truth_groups:
        acceptable = {photo_id for photo_id in truth_group if labels[photo_id].get("acceptable_preferred") is True}
        if not acceptable:
            continue
        preferred_total += 1
        matching = [(members, choice) for members, choice in preferred_predictions.items() if set(members) == truth_group]
        if matching and matching[0][1] in acceptable:
            preferred_correct += 1

    metric_counts = {
        "duplicate_precision": (len(true_pairs), len(predicted_pairs)),
        "duplicate_recall": (len(true_pairs), len(truth_pairs)),
        "removal_precision": (len(remove_predictions & should_remove), len(remove_predictions)),
        "false_removal_rate": (len(auto_excluded & must_keep), len(must_keep)),
        "preferred_accuracy": (preferred_correct, preferred_total),
        "high_quality_retention": (len(must_keep - auto_excluded), len(must_keep)),
        "baseline_high_quality_retention": (len(must_keep - baseline_excluded), len(must_keep)),
    }
    metrics = {name: _safe_ratio(*counts) for name, counts in metric_counts.items()}
    confidence_intervals = {name: _wilson_interval(*counts) for name, counts in metric_counts.items()}
    passed = (
        metrics["duplicate_precision"] >= GATES["duplicate_precision"]
        and metrics["duplicate_recall"] >= GATES["duplicate_recall"]
        and metrics["removal_precision"] >= GATES["removal_precision"]
        and metrics["false_removal_rate"] <= GATES["max_false_removal_rate"]
        and confidence_intervals["false_removal_rate"][1] <= GATES["max_false_removal_rate"]
        and metrics["preferred_accuracy"] >= GATES["preferred_accuracy"]
        and metrics["high_quality_retention"] >= metrics["baseline_high_quality_retention"]
    )
    return {
        "passed": passed,
        "metrics": metrics,
        "confidence_intervals_95": confidence_intervals,
        "counts": metric_counts,
        "gates": GATES,
        "sample_count": len(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the Stage B photo cleaning pipeline")
    parser.add_argument("manifest", type=Path, help="JSONL labels manifest")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    report = evaluate(records, args.manifest.parent)
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
