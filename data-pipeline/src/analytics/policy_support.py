"""Policy-support outcome analytics from curated wages and population data."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .io import CuratedSlice, atomic_json_write


DEFAULT_WAGE_YEARS_ROC = tuple(range(108, 114))
DEFAULT_POPULATION_YEARS_ROC = tuple(range(111, 116))
DEFAULT_POPULATION_MONTH = 7


def calculate_wage_trend(
    records: Iterable[Mapping[str, Any]],
    *,
    annual_years_roc: Iterable[int],
) -> list[dict[str, Any]]:
    """Return one wage row per requested ROC year.

    The source publishes county-level age groups rather than an exact 18--35
    wage.  The policy-support definition therefore selects New Taipei's
    official ``25-29歲`` average only; median and other age groups never enter
    the trend or its YoY calculation.
    """

    years = [int(year) for year in annual_years_roc]
    values: dict[int, float] = {}
    for row in records:
        year = _record_roc_year(row)
        if year not in years:
            continue
        if str(row.get("official_age_group") or "").strip() != "25-29歲":
            continue
        if str(row.get("statistic_method") or "").strip() != "平均數":
            continue
        county = str(row.get("county_name") or "").strip()
        if county and county not in {"新北市", "新北"}:
            continue
        value = _number(row.get("value"))
        if value is not None:
            values[year] = value

    output: list[dict[str, Any]] = []
    for year_roc in years:
        value = values.get(year_roc)
        previous = values.get(year_roc - 1)
        output.append(
            {
                "year": year_roc + 1911,
                "year_roc": year_roc,
                "wage": value,
                "yoy": _yoy(value, previous),
            }
        )
    return output


def calculate_population_trend(
    records: Iterable[Mapping[str, Any]],
    *,
    annual_years_roc: Iterable[int],
    expected_district_ids: Iterable[str],
    month: int = DEFAULT_POPULATION_MONTH,
) -> list[dict[str, Any]]:
    """Return city youth-population totals from one fixed month per year.

    A city's total is emitted only when every expected district has a valid
    ``youth_18_35_total`` record for that exact July snapshot.  This prevents
    an incomplete district set from looking like a real decline in the city
    trend.
    """

    years = [int(year) for year in annual_years_roc]
    district_ids = {str(value) for value in expected_district_ids if value is not None}
    values_by_year: dict[int, dict[str, float]] = {year: {} for year in years}
    for row in records:
        if row.get("metric_id") != "youth_18_35_total":
            continue
        district_id = row.get("district_id")
        if district_id is None or str(district_id) not in district_ids:
            continue
        year_month = str(row.get("period_start") or "")[:7]
        year = _record_roc_year(row)
        if year not in values_by_year or year_month != f"{year + 1911:04d}-{month:02d}":
            continue
        value = _number(row.get("value"))
        if value is not None:
            values_by_year[year][str(district_id)] = value

    output: list[dict[str, Any]] = []
    for year_roc in years:
        district_values = values_by_year[year_roc]
        population = (
            sum(district_values.values())
            if district_ids and district_ids.issubset(district_values)
            else None
        )
        previous = None
        if output and output[-1]["year_roc"] == year_roc - 1:
            previous = output[-1].get("population")
        output.append(
            {
                "year": year_roc + 1911,
                "year_roc": year_roc,
                "population": population,
                "yoy": _yoy(population, previous),
            }
        )
    return output


def generate_policy_support_data(
    *,
    resolver: Any,
    wage_years_roc: Iterable[int] = DEFAULT_WAGE_YEARS_ROC,
    population_years_roc: Iterable[int] = DEFAULT_POPULATION_YEARS_ROC,
    population_month: int = DEFAULT_POPULATION_MONTH,
) -> dict[str, Any]:
    """Generate public Policy Support analytics and its quality metadata."""

    wage_years = tuple(int(year) for year in wage_years_roc)
    population_years = tuple(int(year) for year in population_years_roc)
    generated_at = datetime.now(timezone.utc).isoformat()
    wage_records: list[dict[str, Any]] = []
    population_records: list[dict[str, Any]] = []
    source_period: dict[str, list[str]] = {"wages": [], "population": []}
    paths: dict[str, list[str]] = {"wages": [], "population": []}
    missing_periods: dict[str, list[str]] = {"wages": [], "population": []}

    for year in wage_years:
        period = str(year)
        try:
            item = resolver.period("wages", period)
        except ValueError:
            missing_periods["wages"].append(period)
            continue
        wage_records.extend(dict(row) for row in item.records)
        _record_slice(item, source_period, paths)

    for year in population_years:
        period = f"{year}{population_month:02d}"
        try:
            item = resolver.period("population", period)
        except ValueError:
            missing_periods["population"].append(period)
            continue
        population_records.extend(dict(row) for row in item.records)
        _record_slice(item, source_period, paths)

    districts = [
        dict(row)
        for row in getattr(resolver, "districts", [])
        if isinstance(row, Mapping) and row.get("district_id") is not None
    ]
    district_ids = [str(row["district_id"]) for row in districts]
    wage_trend = calculate_wage_trend(wage_records, annual_years_roc=wage_years)
    population_trend = calculate_population_trend(
        population_records,
        annual_years_roc=population_years,
        expected_district_ids=district_ids,
        month=population_month,
    )

    proxy_usage = [
        {
            "metric": "wageTrend",
            "reason": "官方資料提供 25-29 歲年齡組，作為青年薪資 proxy，並非精確 18-35 歲薪資",
            "source_field": "official_age_group",
        }
    ]
    blocking_reasons: list[str] = []
    for dataset, periods in missing_periods.items():
        for period in periods:
            blocking_reasons.append(f"missing_{dataset}_period:{period}")

    valid_wage_years = sum(row.get("wage") is not None for row in wage_trend)
    valid_population_years = sum(row.get("population") is not None for row in population_trend)
    population_district_counts = _population_district_counts(
        population_records, population_years, population_month, district_ids
    )
    for year_roc, count in population_district_counts.items():
        if count != len(district_ids):
            blocking_reasons.append(
                f"population_district_coverage_incomplete:{year_roc}"
            )
    if valid_wage_years == 0:
        blocking_reasons.append("wage_value_unavailable")
    if valid_population_years == 0:
        blocking_reasons.append("population_value_unavailable")

    total_valid_values = valid_wage_years + valid_population_years
    status = "unavailable" if total_valid_values == 0 else "partial" if blocking_reasons else "observed"
    coverage = {
        "wage_years_requested": len(wage_years),
        "wage_years_available": len(source_period["wages"]),
        "wage_years_with_value": valid_wage_years,
        "population_years_requested": len(population_years),
        "population_month": population_month,
        "population_years_available": len(source_period["population"]),
        "population_years_with_value": valid_population_years,
        "population_expected_district_count": len(district_ids),
        "population_district_counts": {
            str(year): count for year, count in population_district_counts.items()
        },
    }
    outcomes = {
        "wageTrend": wage_trend,
        "populationTrend": population_trend,
        "currentWageGrowth": _last_yoy(wage_trend),
        "currentPopGrowth": _last_yoy(population_trend),
    }
    quality = {
        "metric_id": "policy_support",
        "calculation_version": "1",
        "generated_at": generated_at,
        "source_periods": source_period,
        "paths": paths,
        "coverage": coverage,
        "proxy_usage": proxy_usage,
        "blocking_reasons": blocking_reasons,
        "missing_periods": missing_periods,
        "warnings": [],
    }
    result = {
        "metric_id": "policy_support",
        "calculation_version": "1",
        "generated_at": generated_at,
        "status": status,
        "source_period": source_period,
        "coverage": coverage,
        "proxy_usage": proxy_usage,
        "blocking_reasons": blocking_reasons,
        "time_policy": {
            "wage_years_roc": list(wage_years),
            "population_years_roc": list(population_years),
            "population_month": population_month,
            "population_metric": "youth_18_35_total",
        },
        "policyOutcomes": outcomes,
        "_quality": quality,
    }
    return _sanitize(result)


def write_policy_support_data(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    """Write the public policy-support payload and its quality artifact."""

    root = Path(output_dir)
    quality = dict(result.get("_quality") or {})
    public = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(
        root / "analytics" / "policy_support" / "all.json", _strip_raw_fields(public)
    )
    quality_path = atomic_json_write(
        root / "quality" / "analytics_policy_support.json", _strip_raw_fields(quality)
    )
    return output_path, quality_path


def _record_slice(
    item: CuratedSlice,
    source_period: dict[str, list[str]],
    paths: dict[str, list[str]],
) -> None:
    source_period[item.dataset] = sorted(
        set(source_period[item.dataset]) | set(str(value) for value in item.source_periods)
    )
    paths[item.dataset] = sorted(set(paths[item.dataset]) | set(item.paths))


def _population_district_counts(
    records: Iterable[Mapping[str, Any]],
    years: Iterable[int],
    month: int,
    expected_district_ids: Iterable[str],
) -> dict[int, int]:
    expected = {str(value) for value in expected_district_ids}
    counts: dict[int, set[str]] = {int(year): set() for year in years}
    for row in records:
        if row.get("metric_id") != "youth_18_35_total":
            continue
        year = _record_roc_year(row)
        if year not in counts:
            continue
        if str(row.get("period_start") or "")[:7] != f"{year + 1911:04d}-{month:02d}":
            continue
        if str(row.get("district_id")) not in expected:
            continue
        if _number(row.get("value")) is not None:
            counts[year].add(str(row["district_id"]))
    return {year: len(values) for year, values in counts.items()}


def _record_roc_year(row: Mapping[str, Any]) -> int | None:
    explicit = row.get("year_roc")
    if explicit is not None:
        try:
            return int(explicit)
        except (TypeError, ValueError):
            return None
    period = str(row.get("period_start") or "")
    try:
        return int(period[:4]) - 1911
    except (TypeError, ValueError):
        return None


def _last_yoy(rows: Iterable[Mapping[str, Any]]) -> float | None:
    for row in reversed(list(rows)):
        value = _number(row.get("yoy"))
        if value is not None:
            return value
    return None


def _number(value: Any) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def _yoy(value: Any, previous: Any) -> float | None:
    current_number = _number(value)
    previous_number = _number(previous)
    if current_number is None or previous_number in (None, 0):
        return None
    return round((current_number - previous_number) / previous_number * 100, 2)


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _strip_raw_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_raw_fields(item)
            for key, item in value.items()
            if key not in {"raw_record", "raw_records"}
        }
    if isinstance(value, list):
        return [_strip_raw_fields(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_raw_fields(item) for item in value]
    return _sanitize(value)


__all__ = [
    "DEFAULT_POPULATION_MONTH",
    "DEFAULT_POPULATION_YEARS_ROC",
    "DEFAULT_WAGE_YEARS_ROC",
    "calculate_population_trend",
    "calculate_wage_trend",
    "generate_policy_support_data",
    "write_policy_support_data",
]
