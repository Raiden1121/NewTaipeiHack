"""Reusable pure functions for homepage index calculations."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any


def normalize_p5_p95(
    values: Mapping[str, float | int | None],
    *,
    inverse: bool = False,
    constant_value: float = 50,
) -> dict[str, float | None]:
    """Clip values to P5/P95 and normalize to 0–100 while preserving nulls."""

    valid = [float(value) for value in values.values() if _finite(value)]
    if not valid:
        return {key: None for key in values}
    lower = _percentile(valid, 0.05)
    upper = _percentile(valid, 0.95)
    if math.isclose(lower, upper):
        return {key: (None if not _finite(value) else float(constant_value)) for key, value in values.items()}
    output: dict[str, float | None] = {}
    for key, value in values.items():
        if not _finite(value):
            output[key] = None
            continue
        clipped = min(upper, max(lower, float(value)))
        normalized = (clipped - lower) / (upper - lower) * 100.0
        output[key] = 100.0 - normalized if inverse else normalized
    return output


def shannon_entropy(category_counts: Mapping[Any, float | int | None] | Iterable[float | int | None]) -> float:
    """Return Shannon entropy in bits for non-negative category counts."""

    raw = category_counts.values() if isinstance(category_counts, Mapping) else category_counts
    values = [float(value) for value in raw if _finite(value) and float(value) > 0]
    total = sum(values)
    if total <= 0:
        return 0.0
    return -sum((value / total) * math.log2(value / total) for value in values)


def calculate_quartile_risk(scores: Mapping[str, float | int | None]) -> dict[str, str]:
    """Classify low opportunity risk at or above Q3 and high risk at or below Q1."""

    valid = [float(value) for value in scores.values() if _finite(value)]
    if not valid:
        return {key: "unavailable" for key in scores}
    q1 = _percentile(valid, 0.25)
    q3 = _percentile(valid, 0.75)
    output: dict[str, str] = {}
    for key, value in scores.items():
        if not _finite(value):
            output[key] = "unavailable"
        elif float(value) <= q1:
            output[key] = "high"
        elif float(value) >= q3:
            output[key] = "low"
        else:
            output[key] = "medium"
    return output


def weighted_score(
    parts: Mapping[str, float | int | None], weights: Mapping[str, float | int]
) -> float | None:
    """Return a weighted average over available, non-negative component weights."""

    numerator = 0.0
    denominator = 0.0
    for key, weight in weights.items():
        if not _finite(weight) or float(weight) < 0:
            continue
        value = parts.get(key)
        if not _finite(value):
            continue
        numerator += float(value) * float(weight)
        denominator += float(weight)
    return None if denominator <= 0 else numerator / denominator


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


__all__ = [
    "calculate_quartile_risk",
    "normalize_p5_p95",
    "shannon_entropy",
    "weighted_score",
]
