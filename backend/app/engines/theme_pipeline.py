from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.ai.factory import get_ai_provider
from app.ai.schemas import ThemeCandidateBatchOutput, ThemeCandidateOutput, ThemeConceptEntailmentOutput
from app.ai.types import ImagePayload, ProviderConnectionConfig, ProviderRequest


class ThemePipelineError(RuntimeError):
    pass


def complete_record_candidate() -> dict[str, Any]:
    return {
        "id": "complete_record",
        "title": "完整记录",
        "constraints": normalize_theme_constraints({}),
        "recommended_strategy": "balanced",
        "source": "system",
    }


def summarize_theme_features(features: dict[str, dict]) -> dict[str, Any]:
    return {
        "photo_count": len(features),
        "embedding_count": sum(bool(item.get("embedding")) for item in features.values()),
    }


def selected_theme_text(candidate: dict[str, Any], custom_input: str | None) -> str:
    if candidate.get("source") == "custom" and str(custom_input or "").strip():
        return str(custom_input).strip()
    return str(candidate.get("title") or "").strip()


async def build_theme_query_spec(
    candidate: dict[str, Any],
    *,
    raw_theme: str,
    connection: ProviderConnectionConfig,
) -> dict[str, list[str]]:
    constraints = candidate.get("constraints") if isinstance(candidate.get("constraints"), dict) else {}
    positive_sources = [
        constraints.get("include_concepts", []),
        constraints.get("activities", []),
        constraints.get("locations", []),
        constraints.get("people", []),
    ]
    concepts = list(dict.fromkeys(
        str(value).strip().lower()
        for source in positive_sources
        for value in (source if isinstance(source, list) else [])
        if str(value).strip()
    ))[:24]
    explicit_negatives = list(dict.fromkeys(
        str(value).strip().lower()
        for source in (constraints.get("exclude_concepts", []),)
        for value in (source if isinstance(source, list) else [])
        if str(value).strip()
    ))[:24]
    if not concepts:
        return {"entailed_concepts": [], "negative_concepts": explicit_negatives}

    request = ProviderRequest(
        system_prompt=(
            "Judge strict semantic entailment between a user theme and candidate visual concepts. "
            "A concept is entailed only when the theme itself requires or directly implies it. "
            "Broadly associated, common, nearby, or album-derived concepts are not entailed."
        ),
        user_prompt=(
            "Return JSON only. Preserve every concept exactly once. "
            f"theme={raw_theme!r}\nconcepts={concepts}\n"
            "Format: {\"concepts\":[{\"concept\":str,\"entailed\":bool}]}"
        ),
        output_schema=ThemeConceptEntailmentOutput.model_json_schema(),
        model=connection.model,
        response_temperature=0.0,
        connection=connection,
    )
    try:
        response = await get_ai_provider(connection.provider).infer_json(request)
        parsed = ThemeConceptEntailmentOutput.model_validate(response.payload)
        decisions = {item.concept.strip().lower(): item.entailed for item in parsed.concepts}
    except Exception:  # noqa: BLE001
        return {"entailed_concepts": [], "negative_concepts": explicit_negatives}
    return {
        "entailed_concepts": [concept for concept in concepts if decisions.get(concept) is True],
        "negative_concepts": explicit_negatives,
    }


def _unique_strings(values: Any, *, limit: int = 12) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized and normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
        if len(result) >= limit:
            break
    return result


def extract_requested_years(text: str | None) -> list[int]:
    value = text or ""
    years = [int(item) for item in re.findall(r"(?:19|20)\d{2}", value)]
    for start, end in re.findall(r"((?:19|20)\d{2})\s*(?:-|~|\u81f3|\u5230)\s*((?:19|20)\d{2})", value):
        first, last = sorted((int(start), int(end)))
        if last - first <= 20:
            years.extend(range(first, last + 1))
    return list(dict.fromkeys(years))


def extract_requested_date_range(text: str | None) -> tuple[str | None, str | None]:
    pattern = r"((?:19|20)\d{2})\s*(?:\u5e74|[-/.])\s*(\d{1,2})\s*(?:\u6708|[-/.])\s*(\d{1,2})"
    dates = [f"{int(year):04d}-{int(month):02d}-{int(day):02d}" for year, month, day in re.findall(pattern, text or "")]
    if not dates:
        return None, None
    dates.sort()
    return dates[0], dates[-1]


def normalize_theme_constraints(raw: Any, *, custom_theme: str | None = None) -> dict[str, Any]:
    """Normalize model constraints and merge deterministic constraints from user text."""
    source = raw if isinstance(raw, dict) else {}
    raw_time = source.get("time") if isinstance(source.get("time"), dict) else {}
    raw_years = raw_time.get("years") or source.get("years") or []
    years = [int(value) for value in raw_years if str(value).isdigit() and len(str(value)) == 4]
    years.extend(extract_requested_years(custom_theme))
    years = sorted(set(years))
    evidence = _unique_strings(source.get("evidence"), limit=20)
    if custom_theme:
        evidence.append("user_input")
    start_date = raw_time.get("start_date")
    end_date = raw_time.get("end_date")
    if custom_theme:
        custom_start, custom_end = extract_requested_date_range(custom_theme)
        start_date = custom_start or start_date
        end_date = custom_end or end_date
    return {
        "time": {
            "years": years,
            "start_date": start_date,
            "end_date": end_date,
        },
        "locations": _unique_strings(source.get("locations") or source.get("location")),
        "activities": _unique_strings(source.get("activities") or source.get("events")),
        "people": _unique_strings(source.get("people") or source.get("groups")),
        "include_concepts": _unique_strings(source.get("include_concepts")),
        "exclude_concepts": _unique_strings(source.get("exclude_concepts")),
        "evidence": list(dict.fromkeys(evidence)),
    }


async def generate_theme_candidates(
    feature_summary: dict[str, Any],
    *,
    images: list[ImagePayload],
    candidate_count: int,
    provider_connection: ProviderConnectionConfig,
    custom_theme: str | None = None,
    excluded_titles: set[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    excluded_titles = {str(title).strip().lower() for title in (excluded_titles or set()) if str(title).strip()}
    custom_instruction = ""
    if custom_theme:
        custom_instruction = (
            f"用户自定义主题是：{custom_theme!r}。第一个候选必须忠实采用或概括该主题，"
            "其余候选可以给出相邻但不同的叙事方向。"
        )
    request = ProviderRequest(
        system_prompt=(
            "你是谨慎的家庭相册主题编辑。只生成叙事主题候选和结构化约束，"
            "不识别人物身份，不猜测具体地点，不决定具体照片的最终去留。"
        ),
        user_prompt=(
            "Output a constraints object with time.years/start_date/end_date, locations, activities, people, include_concepts, exclude_concepts, and evidence arrays.\n"
            f"根据照片语义摘要和代表图生成 {candidate_count} 个互不重复的主题候选。"
            "输出 JSON：{\"themes\":[{\"title\":str,\"include_concepts\":[str],\"exclude_concepts\":[str],"
            "\"recommended_strategy\":str}]}。\n"
            "title 必须是 2 至 8 个简体中文字符，不得包含英文、标点、解释或说明。"
            "不要输出 summary、description 或其他主题说明字段。"
            "概念必须使用简短、通用、英文小写标签，并以代表图中可直接观察到的内容为依据。"
            "recommended_strategy 只能是 balanced/activity_first/time_first/location_first。"
            "亲友聚会、庆祝活动等流程型主题优先 activity_first；旅行地点主题优先 location_first；"
            "成长、年度记录优先 time_first。不要输出“完整记录”，系统会另行添加。\n"
            f"不要使用这些已有主题标题：{sorted(excluded_titles)}。\n{custom_instruction}\nfeature_summary={feature_summary}"
        ),
        output_schema=ThemeCandidateBatchOutput.model_json_schema(),
        model=provider_connection.model,
        images=images,
        connection=provider_connection,
    )
    response = await get_ai_provider(provider_connection.provider).infer_json(request)
    raw_themes = response.payload.get("themes") if isinstance(response.payload, dict) else None
    if not isinstance(raw_themes, list):
        raise ThemePipelineError("theme candidate response did not contain a themes list")
    themes: list[ThemeCandidateOutput] = []
    validation_errors: list[str] = []
    for index, raw_theme in enumerate(raw_themes[:5]):
        if custom_theme and not excluded_titles and index == 0 and isinstance(raw_theme, dict):
            # Validate the provider payload with a schema-safe placeholder;
            # the original custom text is restored when the candidate is built.
            raw_theme = {**raw_theme, "title": "\u4e3b\u9898"}
        try:
            themes.append(ThemeCandidateOutput.model_validate(raw_theme))
        except ValidationError as exc:
            validation_errors.append(str(exc))
    if not themes:
        detail = validation_errors[0] if validation_errors else "response was empty"
        raise ThemePipelineError(f"theme candidate schema validation failed: {detail}")
    candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    for index, item in enumerate(themes):
        is_custom_candidate = bool(custom_theme and not excluded_titles and index == 0)
        # AI titles remain normalized, but a user supplied theme is an exact
        # instruction and must survive candidate generation unchanged.
        title = custom_theme.strip() if is_custom_candidate else item.title.strip()
        normalized_title = title.lower()
        if normalized_title in seen_titles or normalized_title in excluded_titles:
            continue
        seen_titles.add(normalized_title)
        constraints = normalize_theme_constraints(
            item.constraints,
            custom_theme=custom_theme if is_custom_candidate else None,
        )
        constraints["include_concepts"] = list(dict.fromkeys([
            *constraints.get("include_concepts", []),
            *[value.strip().lower() for value in item.include_concepts if value.strip()],
        ]))[:12]
        constraints["exclude_concepts"] = list(dict.fromkeys([
            *constraints.get("exclude_concepts", []),
            *[value.strip().lower() for value in item.exclude_concepts if value.strip()],
        ]))[:12]
        candidate = {
            "id": f"candidate-{index + 1}",
            "title": title,
            "constraints": constraints,
            "recommended_strategy": item.recommended_strategy,
            "source": "custom" if is_custom_candidate else "ai",
        }
        candidates.append(candidate)
        if len(candidates) >= candidate_count:
            break
    if not candidates:
        raise ThemePipelineError("theme candidate response was empty")
    return candidates, response.debug | {"provider": response.provider, "model": response.model}
