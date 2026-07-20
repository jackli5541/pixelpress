from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.ai.factory import get_multimodal_embedding_provider
from app.ai.types import ProviderConnectionConfig, TextEmbeddingRequest


QUERY_VERSION = "cross-modal-query-v2-anchored"
SCORING_VERSION = "cross-modal-relevance-v3-embedding-only"


@dataclass(frozen=True, slots=True)
class ThemeQuery:
    positive_vector: list[float]
    provider: str
    model: str
    dimension: int
    expansion_vectors: tuple[list[float], ...] = ()
    negative_vectors: tuple[list[float], ...] = ()
    query_version: str = QUERY_VERSION


@dataclass(frozen=True, slots=True)
class RelevanceCalibration:
    version: str
    provider: str
    model: str
    dimension: int
    query_version: str
    scoring_version: str
    enabled: bool
    signal_knots: tuple[float, ...]
    probability_knots: tuple[float, ...]
    exclude_max_probability: float
    keep_min_probability: float
    load_status: str = "loaded"
    feature_order: tuple[str, ...] = ()
    coefficients: tuple[float, ...] = ()
    intercept: float = 0.0
    feature_means: tuple[float, ...] = ()
    feature_scales: tuple[float, ...] = ()

    @classmethod
    def from_dict(
        cls,
        payload: dict[str, Any],
        *,
        load_status: str = "loaded",
    ) -> "RelevanceCalibration":
        mapping = payload.get("mapping") or {}
        thresholds = payload.get("decision_thresholds") or {}
        classifier = payload.get("classifier") or {}
        feature_order = tuple(str(value) for value in classifier.get("feature_order", []))
        coefficients = tuple(float(value) for value in classifier.get("coefficients", []))
        feature_means = tuple(float(value) for value in classifier.get("feature_means", []))
        feature_scales = tuple(float(value) for value in classifier.get("feature_scales", []))
        classifier_valid = not feature_order or (
            len(feature_order) == len(coefficients) == len(feature_means) == len(feature_scales)
            and all(value > 0 for value in feature_scales)
        )
        signal_knots = tuple(float(value) for value in mapping.get("signal", []))
        probability_knots = tuple(float(value) for value in mapping.get("probability", []))
        if len(signal_knots) != len(probability_knots) or len(signal_knots) < 2:
            signal_knots, probability_knots = (), ()
        if signal_knots and any(left >= right for left, right in zip(signal_knots, signal_knots[1:])):
            signal_knots, probability_knots = (), ()
        if probability_knots and (
            any(value < 0 or value > 1 for value in probability_knots)
            or any(left > right for left, right in zip(probability_knots, probability_knots[1:]))
        ):
            signal_knots, probability_knots = (), ()
        exclude_threshold = float(thresholds.get("exclude_max_probability", 0.25))
        keep_threshold = float(thresholds.get("keep_min_probability", 0.75))
        thresholds_valid = 0 <= exclude_threshold < keep_threshold <= 1
        requirements = payload.get("requirements") or {}
        metrics = payload.get("metrics") or {}
        gates = payload.get("gates") or {}
        quality_valid = bool(requirements.get("requirements_met")) and all(
            isinstance(metrics.get(name), (int, float)) and isinstance(gates.get(name), (int, float))
            for name in ("candidate_precision", "relevant_recall", "false_exclusion_rate")
        )
        if quality_valid:
            quality_valid = (
                float(metrics["candidate_precision"]) >= float(gates["candidate_precision"])
                and float(metrics["relevant_recall"]) >= float(gates["relevant_recall"])
                and float(metrics["false_exclusion_rate"]) <= float(gates["false_exclusion_rate"])
            )
        return cls(
            version=str(payload.get("version") or "unavailable"),
            provider=str(payload.get("provider") or ""),
            model=str(payload.get("model") or ""),
            dimension=int(payload.get("dimension") or 0),
            query_version=str(payload.get("query_version") or ""),
            scoring_version=str(payload.get("scoring_version") or ""),
            enabled=(
                bool(payload.get("enabled"))
                and bool(signal_knots)
                and thresholds_valid
                and classifier_valid
                and quality_valid
            ),
            signal_knots=signal_knots,
            probability_knots=probability_knots,
            exclude_max_probability=exclude_threshold,
            keep_min_probability=keep_threshold,
            load_status=load_status,
            feature_order=feature_order,
            coefficients=coefficients,
            intercept=float(classifier.get("intercept") or 0.0),
            feature_means=feature_means,
            feature_scales=feature_scales,
        )

    def compatibility_status(
        self,
        *,
        provider: str,
        model: str,
        dimension: int,
        query_version: str = QUERY_VERSION,
        scoring_version: str = SCORING_VERSION,
    ) -> str:
        if self.load_status != "loaded":
            return "missing"
        if not self.enabled:
            return "disabled"
        if (
            self.provider != provider
            or self.model != model
            or self.dimension != dimension
            or self.query_version != query_version
            or self.scoring_version != scoring_version
        ):
            return "mismatch"
        return "ready"


def load_calibration(path: str | Path | None = None) -> RelevanceCalibration:
    if not path or not str(path).strip():
        return RelevanceCalibration.from_dict({}, load_status="missing")
    target = Path(path)
    try:
        return RelevanceCalibration.from_dict(json.loads(target.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return RelevanceCalibration.from_dict({}, load_status="missing")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return RelevanceCalibration.from_dict({}, load_status="invalid")


def normalize_vector(vector: list[float]) -> list[float]:
    values = [float(value) for value in vector]
    if not values or not all(math.isfinite(value) for value in values):
        raise ValueError("embedding vector must contain finite values")
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        raise ValueError("embedding vector must not be zero")
    return [value / norm for value in values]


def build_query_texts(candidate: dict[str, Any], *, custom_input: str | None = None) -> tuple[list[str], str | None]:
    title = str(custom_input or candidate.get("title") or "").strip()
    if not title:
        raise ValueError("theme title is required")
    query_spec = candidate.get("_query_spec") if isinstance(candidate.get("_query_spec"), dict) else {}
    entailed = [str(value).strip() for value in query_spec.get("entailed_concepts", []) if str(value).strip()]
    negatives = [str(value).strip() for value in query_spec.get("negative_concepts", []) if str(value).strip()]
    anchored = f"一张主要视觉内容直接表现主题“{title}”的照片，而不是仅有相似背景或宽泛场景"
    if entailed:
        anchored = f"{anchored}；主题直接蕴含的视觉概念：{'、'.join(entailed)}"
    negative = f"与主题“{title}”外观相似但不满足主题核心含义的照片：{'、'.join(negatives)}" if negatives else None
    return [title, anchored], negative


class ThemeRelevanceEngine:
    async def build_query(
        self,
        candidate: dict[str, Any],
        *,
        connection: ProviderConnectionConfig,
        dimension: int,
        custom_input: str | None = None,
    ) -> ThemeQuery:
        texts, negative_text = build_query_texts(candidate, custom_input=custom_input)
        request_texts = [*texts, *([negative_text] if negative_text else [])]
        response = await get_multimodal_embedding_provider(connection.provider).embed_texts(
            TextEmbeddingRequest(
                texts=request_texts,
                model=connection.model,
                dimension=dimension,
                connection=connection,
            )
        )
        if response.model != connection.model or len(response.embeddings) != len(request_texts):
            raise ValueError("theme embedding response metadata mismatch")
        raw_vector = normalize_vector(response.embeddings[0])
        expansion_vectors = tuple(normalize_vector(vector) for vector in response.embeddings[1:2])
        negative_vectors = tuple(normalize_vector(vector) for vector in response.embeddings[2:]) if negative_text else ()
        return ThemeQuery(
            positive_vector=raw_vector,
            provider=response.provider,
            model=response.model,
            dimension=dimension,
            expansion_vectors=expansion_vectors,
            negative_vectors=negative_vectors,
        )

    @staticmethod
    def score_record(
        *,
        photo_id: str,
        taken_at: Any,
        feature: dict[str, Any] | None,
        candidate: dict[str, Any],
        query: ThemeQuery | None,
        calibration: RelevanceCalibration,
        provisional_auto_decision_enabled: bool = False,
        provisional_decision_threshold: float = 0.60,
    ) -> dict[str, Any]:
        if candidate.get("id") == "complete_record":
            return {
                "photo_id": photo_id,
                "relevance_score": 1.0,
                "relevance_label": "relevant",
                "suggested_decision": "keep",
                "user_decision": None,
                "reasons_json": ["complete_record"],
                "evidence_json": {
                    "method": "complete_record",
                    "calibration_status": "bypassed",
                    "score_kind": "explicit_user_choice",
                },
                "scoring_version": "complete-record-v1",
                "feature_version": (feature or {}).get("feature_version"),
            }
        return score_photo_relevance(
            photo_id=photo_id,
            photo_vector=(feature or {}).get("embedding"),
            photo_provider=(feature or {}).get("embedding_provider"),
            photo_model=(feature or {}).get("embedding_model"),
            photo_dimension=(feature or {}).get("embedding_dimension"),
            taken_at=taken_at,
            query=query,
            calibration=calibration,
            provisional_auto_decision_enabled=provisional_auto_decision_enabled,
            provisional_decision_threshold=provisional_decision_threshold,
            constraints=dict(candidate.get("explicit_constraints") or {}),
            feature_version=(feature or {}).get("feature_version"),
        )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_normalized = normalize_vector(left)
    right_normalized = normalize_vector(right)
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left_normalized, right_normalized))))


def relevance_signal(positive_similarity: float, negative_similarity: float | None) -> float:
    penalty = max(0.0, (negative_similarity or -1.0) - positive_similarity) * 0.5
    return positive_similarity - penalty


def query_similarity_features(photo_vector: list[float], query: ThemeQuery) -> dict[str, float | None]:
    raw_similarity = cosine_similarity(photo_vector, query.positive_vector)
    expansion_similarities = [cosine_similarity(photo_vector, vector) for vector in query.expansion_vectors]
    negative_similarities = [cosine_similarity(photo_vector, vector) for vector in query.negative_vectors]
    expanded_similarity = (
        sum(expansion_similarities) / len(expansion_similarities)
        if expansion_similarities
        else raw_similarity
    )
    negative_similarity = max(negative_similarities) if negative_similarities else None
    positive_similarity = 0.7 * raw_similarity + 0.3 * expanded_similarity
    margin = positive_similarity - negative_similarity if negative_similarity is not None else positive_similarity
    return {
        "raw_query_similarity": raw_similarity,
        "expanded_query_similarity": expanded_similarity,
        "positive_similarity": positive_similarity,
        "negative_similarity": negative_similarity,
        "margin": margin,
        "signal": relevance_signal(positive_similarity, negative_similarity),
    }


def calibrated_probability(
    signal: float,
    calibration: RelevanceCalibration,
    features: dict[str, float | None] | None = None,
) -> float | None:
    if not calibration.enabled:
        return None
    mapping_input = signal
    if calibration.feature_order:
        if features is None:
            return None
        values: list[float] = []
        for name, mean, scale in zip(calibration.feature_order, calibration.feature_means, calibration.feature_scales):
            raw = features.get(name)
            values.append((float(raw) - mean) / scale if raw is not None else 0.0)
        logit = calibration.intercept + sum(weight * value for weight, value in zip(calibration.coefficients, values))
        mapping_input = 1.0 / (1.0 + math.exp(-max(-40.0, min(40.0, logit))))
    xs = calibration.signal_knots
    ys = calibration.probability_knots
    if mapping_input <= xs[0]:
        return max(0.0, min(1.0, ys[0]))
    if mapping_input >= xs[-1]:
        return max(0.0, min(1.0, ys[-1]))
    for left, right in zip(range(len(xs)), range(1, len(xs))):
        if mapping_input <= xs[right]:
            ratio = (mapping_input - xs[left]) / (xs[right] - xs[left])
            value = ys[left] + ratio * (ys[right] - ys[left])
            return max(0.0, min(1.0, value))
    return None


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _time_constraint_result(taken_at: Any, constraints: dict[str, Any]) -> tuple[str | None, list[str]]:
    raw_time = constraints.get("time") if isinstance(constraints.get("time"), dict) else {}
    years = {
        int(value)
        for value in raw_time.get("years", [])
        if str(value).isdigit() and len(str(value)) == 4
    }
    start = _date_value(raw_time.get("start_date"))
    end = _date_value(raw_time.get("end_date"))
    captured = _date_value(taken_at)
    if (years or start or end) and captured is None:
        return "review", ["missing_capture_time"]
    if captured is None:
        return None, []
    if years and captured.year not in years:
        return "exclude", ["outside_requested_year"]
    if (start and captured < start) or (end and captured > end):
        return "exclude", ["outside_requested_date_range"]
    reasons = ["matched_time_constraint"] if years or start or end else []
    return None, reasons


def score_photo_relevance(
    *,
    photo_id: str,
    photo_vector: list[float] | None,
    photo_provider: str | None,
    photo_model: str | None,
    photo_dimension: int | None,
    taken_at: Any,
    query: ThemeQuery | None,
    calibration: RelevanceCalibration,
    provisional_auto_decision_enabled: bool = False,
    provisional_decision_threshold: float = 0.60,
    constraints: dict[str, Any] | None = None,
    feature_version: str | None = None,
) -> dict[str, Any]:
    forced, reasons = _time_constraint_result(taken_at, constraints or {})
    calibration_status = (
        calibration.compatibility_status(
            provider=query.provider,
            model=query.model,
            dimension=query.dimension,
            query_version=query.query_version,
        )
        if query is not None
        else "missing"
    )
    evidence: dict[str, Any] = {
        "method": "cross_modal_embedding",
        "scoring_version": SCORING_VERSION,
        "query_version": query.query_version if query else QUERY_VERSION,
        "calibration_version": calibration.version,
        "calibration_status": calibration_status,
        "provider": query.provider if query else None,
        "model": query.model if query else photo_model,
        "dimension": query.dimension if query else photo_dimension,
        "positive_similarity": None,
        "raw_query_similarity": None,
        "expanded_query_similarity": None,
        "negative_similarity": None,
        "margin": None,
        "signal": None,
        "calibrated": False,
        "score_kind": "calibrated_probability" if calibration_status == "ready" else "embedding_similarity_rank",
        "decision_mode": "calibrated" if calibration_status == "ready" else "manual_review",
        "provisional_threshold": None,
    }

    unavailable_reason = None
    if query is None:
        unavailable_reason = "theme_query_unavailable"
    elif not photo_vector:
        unavailable_reason = "photo_embedding_unavailable"
    elif (
        photo_provider != query.provider
        or photo_model != query.model
        or photo_dimension != query.dimension
        or len(photo_vector) != query.dimension
    ):
        unavailable_reason = "embedding_model_mismatch"
    if unavailable_reason:
        return _payload(
            photo_id,
            0.5,
            "uncertain",
            "review",
            [*reasons, unavailable_reason],
            evidence,
            feature_version,
        )

    try:
        features = query_similarity_features(photo_vector, query)
    except (TypeError, ValueError):
        return _payload(
            photo_id,
            0.5,
            "uncertain",
            "review",
            [*reasons, "invalid_embedding_vector"],
            evidence,
            feature_version,
        )
    positive = float(features["positive_similarity"])
    negative = features["negative_similarity"]
    signal = float(features["signal"])
    probability = calibrated_probability(signal, calibration, features) if calibration_status == "ready" else None
    evidence.update({
        "raw_query_similarity": round(float(features["raw_query_similarity"]), 6),
        "expanded_query_similarity": round(float(features["expanded_query_similarity"]), 6),
        "positive_similarity": round(positive, 6),
        "negative_similarity": round(negative, 6) if negative is not None else None,
        "margin": round(float(features["margin"]), 6),
        "signal": round(signal, 6),
        "calibrated": probability is not None,
    })
    if probability is None:
        rank_score = max(0.0, min(1.0, (signal + 1.0) / 2.0))
        fallback_reason = {
            "disabled": "calibration_disabled",
            "mismatch": "calibration_model_mismatch",
            "missing": "calibration_missing",
        }.get(calibration_status, "calibration_unavailable")
        provisional_enabled = provisional_auto_decision_enabled and calibration_status in {"missing", "disabled"}
        if forced == "review":
            return _payload(photo_id, rank_score, "uncertain", "review", reasons, evidence, feature_version)
        if provisional_enabled:
            threshold = max(0.0, min(1.0, float(provisional_decision_threshold)))
            evidence.update({
                "decision_mode": "provisional_binary",
                "provisional_threshold": threshold,
            })
            if forced == "exclude":
                return _payload(photo_id, 0.0, "off_theme", "exclude", reasons, evidence, feature_version)
            if rank_score >= threshold:
                return _payload(
                    photo_id,
                    rank_score,
                    "relevant",
                    "keep",
                    [*reasons, "provisional_threshold_match", fallback_reason],
                    evidence,
                    feature_version,
                )
            return _payload(
                photo_id,
                rank_score,
                "off_theme",
                "exclude",
                [*reasons, "provisional_threshold_mismatch", fallback_reason],
                evidence,
                feature_version,
            )
        if forced == "exclude":
            reasons = [*reasons, "constraint_mismatch_unconfirmed"]
        return _payload(photo_id, rank_score, "uncertain", "review", [*reasons, fallback_reason], evidence, feature_version)
    if forced == "review":
        return _payload(photo_id, probability, "uncertain", "review", reasons, evidence, feature_version)
    if forced == "exclude":
        return _payload(photo_id, 0.0, "off_theme", "exclude", reasons, evidence, feature_version)
    if probability >= calibration.keep_min_probability:
        return _payload(photo_id, probability, "relevant", "keep", [*reasons, "cross_modal_match"], evidence, feature_version)
    if probability <= calibration.exclude_max_probability:
        return _payload(photo_id, probability, "off_theme", "exclude", [*reasons, "cross_modal_mismatch"], evidence, feature_version)
    return _payload(photo_id, probability, "uncertain", "review", [*reasons, "cross_modal_uncertain"], evidence, feature_version)


def _payload(
    photo_id: str,
    score: float,
    label: str,
    decision: str,
    reasons: list[str],
    evidence: dict[str, Any],
    feature_version: str | None,
) -> dict[str, Any]:
    return {
        "photo_id": photo_id,
        "relevance_score": round(max(0.0, min(1.0, float(score))), 4),
        "relevance_label": label,
        "suggested_decision": decision,
        "user_decision": None,
        "reasons_json": list(dict.fromkeys(reasons)),
        "evidence_json": evidence,
        "scoring_version": SCORING_VERSION,
        "feature_version": feature_version,
    }


__all__ = [
    "QUERY_VERSION",
    "SCORING_VERSION",
    "RelevanceCalibration",
    "ThemeQuery",
    "ThemeRelevanceEngine",
    "build_query_texts",
    "load_calibration",
    "query_similarity_features",
    "score_photo_relevance",
]
