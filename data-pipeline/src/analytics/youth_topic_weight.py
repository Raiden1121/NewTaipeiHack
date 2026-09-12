"""Calculate annual youth-topic signals and frontend weights."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .config import TopicWeights, YouthTopicRules, match_topic_labels
from .io import atomic_json_write


def calculate_youth_topic_weights(
    join_records: Iterable[Mapping[str, Any]],
    minute_records: Iterable[Mapping[str, Any]],
    *,
    rules: YouthTopicRules,
    weights: TopicWeights,
) -> dict[str, Any]:
    _load_optional_jieba(rules)
    join_rows = [dict(row) for row in join_records]
    minute_rows = [dict(row) for row in minute_records]
    years: set[int] = set()
    join_mentions: dict[tuple[int, str], int] = defaultdict(int)
    join_support: dict[tuple[int, str], float] = defaultdict(float)
    minute_mentions: dict[tuple[int, str], int] = defaultdict(int)
    resolved: set[tuple[int, str]] = set()
    escalated: set[tuple[int, str]] = set()
    join_seen: dict[tuple[int, str], set[str]] = defaultdict(set)
    minute_seen: dict[tuple[int, str], set[str]] = defaultdict(set)

    for index, row in enumerate(join_rows):
        year = _row_year(row)
        if year is None:
            continue
        years.add(year)
        if row.get("youth_topic_proxy") is not True:
            continue
        text = " ".join(str(row.get(key) or "") for key in ("title", "content"))
        record_id = _record_id(row, index, "join")
        endorsement = _non_negative_number(row.get("endorsement_count"))
        for label in match_topic_labels(text, rules):
            key = (year, label)
            if record_id in join_seen[key]:
                continue
            join_seen[key].add(record_id)
            join_mentions[key] += 1
            join_support[key] += 1.0 + math.log1p(endorsement)

    for index, row in enumerate(minute_rows):
        year = _row_year(row)
        if year is None:
            continue
        years.add(year)
        text = str(row.get("source_text") or "")
        record_id = _record_id(row, index, "minutes")
        for label in match_topic_labels(text, rules):
            key = (year, label)
            if record_id not in minute_seen[key]:
                minute_seen[key].add(record_id)
                minute_mentions[key] += 1
            if row.get("resolved") is True:
                resolved.add(key)
            if row.get("escalated") is True:
                escalated.add(key)

    output_years: list[dict[str, Any]] = []
    for year in sorted(years):
        year_join_max = max(
            (value for (row_year, _), value in join_support.items() if row_year == year),
            default=0.0,
        )
        year_minute_max = max(
            (value for (row_year, _), value in minute_mentions.items() if row_year == year),
            default=0,
        )
        rows: list[dict[str, Any]] = []
        raw_scores: dict[str, float] = {}
        for topic in rules.topics:
            key = (year, topic.label)
            normalized_join = join_support[key] / year_join_max if year_join_max else 0.0
            normalized_minutes = minute_mentions[key] / year_minute_max if year_minute_max else 0.0
            raw_score = (
                weights.w_join * normalized_join
                + weights.w_minutes * normalized_minutes
                + weights.w_resolved * (1.0 if key in resolved else 0.0)
                + weights.w_escalated * (1.0 if key in escalated else 0.0)
            )
            raw_scores[topic.label] = raw_score

        max_raw_score = max(raw_scores.values(), default=0.0)
        for topic in rules.topics:
            key = (year, topic.label)
            raw_score = raw_scores[topic.label]
            if max_raw_score <= 0:
                weight = 1
            else:
                weight = max(1, min(5, math.floor(1.0 + 4.0 * raw_score / max_raw_score + 0.5)))
            if minute_mentions[key] > 0:
                weight = max(weight, 3)
            if key in escalated:
                weight = 5
            signal = None
            if key in escalated:
                signal = "escalated"
            elif minute_mentions[key] > 0:
                signal = "minutes"
            elif join_mentions[key] > 0:
                signal = "join"
            rows.append(
                {
                    "label": topic.label,
                    "weight": weight,
                    "signal": signal,
                    "join_mentions": join_mentions[key],
                    "minutes_mentions": minute_mentions[key],
                    "resolved": key in resolved,
                    "escalated": key in escalated,
                    "join_support_score": round(join_support[key], 6),
                    "raw_score": round(raw_score, 6),
                }
            )
        output_years.append({"year_roc": year, "topics": rows})

    return {
        "metric_id": "youth_topic_weight",
        "calculation_version": "1",
        "source_datasets": ["join_proposals", "youth_council_minutes"],
        "config_version": rules.version,
        "normalization": weights.normalization,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "years": output_years,
        "_quality": {
            "join_input_rows": len(join_rows),
            "minutes_input_rows": len(minute_rows),
            "years": [item["year_roc"] for item in output_years],
        },
    }


def write_youth_topic_weights(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    root = Path(output_dir)
    output = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(root / "analytics" / "youth_topic_weight" / "all.json", output)
    quality = {
        "metric_id": "youth_topic_weight",
        "calculation_version": result.get("calculation_version"),
        "config_version": result.get("config_version"),
        "source_datasets": result.get("source_datasets"),
        **dict(result.get("_quality") or {}),
    }
    quality_path = atomic_json_write(root / "quality" / "analytics_youth_topic_weight.json", quality)
    return output_path, quality_path


def _load_optional_jieba(rules: YouthTopicRules) -> None:
    try:
        import jieba  # type: ignore
    except ImportError:
        return
    if rules.userdict_path and rules.userdict_path.exists():
        jieba.load_userdict(str(rules.userdict_path))


def _row_year(row: Mapping[str, Any]) -> int | None:
    value = row.get("year_roc")
    if value is not None:
        try:
            year = int(str(value).strip())
            return year - 1911 if year > 1911 else year
        except (TypeError, ValueError):
            return None
    period_start = row.get("period_start")
    if isinstance(period_start, str):
        try:
            return datetime.fromisoformat(period_start[:10]).year - 1911
        except ValueError:
            return None
    return None


def _record_id(row: Mapping[str, Any], index: int, prefix: str) -> str:
    value = row.get("source_record_id")
    if value is not None:
        return str(value)
    payload = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return f"{prefix}:{index}:{hashlib.sha256(payload).hexdigest()[:16]}"


def _non_negative_number(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return 0.0
    try:
        return max(0.0, float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0.0
