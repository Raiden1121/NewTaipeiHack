"""Fertility-page analytics built from curated pipeline outputs."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .annual_metrics import calculate_annual_fertility
from .config import HomepageAnalyticsConfig
from .homepage import _source_periods
from .homepage_math import calculate_ols_regression, normalize_p5_p95
from .input_resolver import HomepageInputResolver
from .io import CuratedSlice, atomic_json_write
from .service_coverage import calculate_population_service_coverage


def calculate_annual_fertility_metrics(
    birth_records: Iterable[Mapping[str, Any]],
    population_records: Iterable[Mapping[str, Any]],
    *,
    annual_years_roc: Iterable[int],
    districts: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Calculate annual fertility and youth-ratio rows for every district."""

    expected = [
        {"district_id": str(row["district_id"]), "district_name": row.get("district_name")}
        for row in districts
        if row.get("district_id") is not None
    ]
    annual = calculate_annual_fertility(
        birth_records,
        population_records,
        annual_years_roc=annual_years_roc,
    )
    birth_lookup = _birth_lookup(birth_records, annual_years_roc)
    population_lookup = _latest_population_lookup(population_records, annual_years_roc)
    output_years: list[dict[str, Any]] = []

    for annual_row in annual.get("years", []):
        year = int(annual_row["year_roc"])
        fertility_rows = {
            str(row.get("district_id")): row
            for row in annual_row.get("districts", [])
            if row.get("district_id") is not None
        }
        rows: list[dict[str, Any]] = []
        for district in expected:
            district_id = district["district_id"]
            fertility = fertility_rows.get(district_id, {})
            population = population_lookup.get((year, district_id), {})
            births_present = (year, district_id) in birth_lookup
            total_births = birth_lookup.get((year, district_id)) if births_present else None
            fertility_rate = fertility.get("fertility_rate")
            youth_ratio = _ratio(
                population.get("youth_18_35_total"),
                population.get("people_total"),
                multiplier=100,
            )
            available_months = fertility.get("available_months", 0)
            row_status = _row_status(
                fertility_rate,
                youth_ratio,
                complete=available_months == 12 and births_present,
            )
            rows.append(
                {
                    "district_id": district_id,
                    "district_name": district.get("district_name") or fertility.get("district_name"),
                    "totalBirths": _number(total_births),
                    "fertilityRate": _number(
                        None if fertility_rate is None else fertility_rate
                    ),
                    "youthRatio": _number(youth_ratio),
                    "averageMonthlyFemale18_35": _number(
                        fertility.get("average_monthly_female_18_35")
                    ),
                    "availableMonths": int(available_months or 0),
                    "coverageRatio": _number(fertility.get("coverage_ratio")) or 0.0,
                    "sourcePeriod": [str(year)],
                    "status": row_status,
                }
            )

        city = _city_summary(rows, annual_row.get("city", {}), population_lookup, year)
        output_years.append(
            {
                "year_roc": year,
                "citySummary": city,
                "districts": rows,
                "status": city["status"],
                "sourcePeriod": [str(year)],
            }
        )

    return {"metric_id": "fertilityAnnual", "years": output_years}


def calculate_fafi_scores(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate the equal-weighted Family-Friendly Index for district rows."""

    indexed = {
        str(row.get("district_id")): dict(row)
        for row in rows
        if row.get("district_id") is not None
    }
    coverage_values = {
        district_id: _number(row.get("daycareCoverage"))
        for district_id, row in indexed.items()
    }
    wage_values = {
        district_id: _number(row.get("estimatedWage"))
        for district_id, row in indexed.items()
    }
    normalized_coverage = normalize_p5_p95(coverage_values)
    normalized_wage = normalize_p5_p95(wage_values)

    fafi_values: dict[str, float | None] = {}
    result_rows: dict[str, dict[str, Any]] = {}
    for district_id, row in indexed.items():
        coverage_score = normalized_coverage.get(district_id)
        wage_score = normalized_wage.get(district_id)
        housing_score = _number(row.get("score_housing"))
        fafi = _mean_if_complete((coverage_score, housing_score, wage_score))
        fafi_values[district_id] = fafi
        result_rows[district_id] = {
            "daycareCoverageScore": coverage_score,
            "housingScore": housing_score,
            "wageScore": wage_score,
            "fafiScore": fafi,
            "fafiLevel": None,
        }

    valid = [value for value in fafi_values.values() if value is not None]
    q1 = _percentile(valid, 0.25) if valid else None
    q3 = _percentile(valid, 0.75) if valid else None
    for district_id, item in result_rows.items():
        value = item["fafiScore"]
        if value is None or q1 is None or q3 is None:
            continue
        item["fafiLevel"] = (
            "low" if value <= q1 else "high" if value >= q3 else "medium"
        )

    missing_count = sum(value is None for value in fafi_values.values())
    if not indexed or not valid:
        status = "unavailable"
    elif missing_count:
        status = "partial"
    else:
        status = "observed"
    return {
        "metric_id": "fafi",
        "status": status,
        "normalization": {
            "method": "p5_p95",
            "inputs": ["daycareCoverage", "score_housing", "estimatedWage"],
            "q1": q1,
            "q3": q3,
        },
        "districts": result_rows,
        "blocking_reasons": ["fafi_component_missing"] if missing_count else [],
    }


def generate_fertility_data(
    *,
    resolver: HomepageInputResolver,
    config: HomepageAnalyticsConfig,
    homepage_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the public fertility analytics payload and quality metadata."""

    generated_at = datetime.now(timezone.utc).isoformat()
    quality: dict[str, Any] = {
        "metric_id": "fertility",
        "calculation_version": "1",
        "generated_at": generated_at,
        "inputs": {},
        "source_periods": {},
        "warnings": [],
        "blocking_reasons": [],
        "proxy_usage": [],
        "excluded": {},
    }
    loaded: dict[str, CuratedSlice] = {}

    def load_periods(dataset: str, periods: list[str]) -> list[dict[str, Any]]:
        try:
            item = resolver.available_periods(dataset, periods)
        except (AttributeError, ValueError) as exc:
            _record_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, item)
        loaded[f"{dataset}:{','.join(item.source_periods)}"] = item
        return [dict(row) for row in item.records]

    def load_latest(dataset: str) -> list[dict[str, Any]]:
        try:
            item = resolver.latest(dataset)
        except (AttributeError, ValueError) as exc:
            _record_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, item)
        loaded[dataset] = item
        return [dict(row) for row in item.records]

    annual_years = list(config.annual_years_roc)
    population_records = load_periods(
        "population",
        [f"{year:03d}{month:02d}" for year in annual_years for month in range(1, 13)],
    )
    birth_records = load_periods("births", [f"{year:03d}" for year in annual_years])
    village_population = load_periods(
        "population_villages",
        [
            f"{config.population_reference_year_roc:03d}{month:02d}"
            for month in range(1, 13)
        ],
    )
    boundaries = load_latest("village_boundaries")
    daycare_points = load_latest("babysitting_places")
    daycare_source_periods = list(
        loaded.get("babysitting_places").source_periods
        if loaded.get("babysitting_places") is not None
        else ()
    )

    annual = calculate_annual_fertility_metrics(
        birth_records,
        population_records,
        annual_years_roc=annual_years,
        districts=resolver.districts,
    )
    reference_year = config.population_reference_year_roc
    reference_year_row = next(
        (row for row in annual["years"] if row["year_roc"] == reference_year),
        {"year_roc": reference_year, "citySummary": {}, "districts": []},
    )

    daycare = calculate_population_service_coverage(
        daycare_points,
        boundaries,
        village_population,
        radius_m=1000,
        population_field="youth_18_35_female",
        metric_id="daycareCoverageRate",
        output_prefix="female_18_35",
        source_datasets=["babysitting_places", "village_boundaries", "population_villages"],
    )
    if daycare["status"] != "observed":
        quality["warnings"].extend(daycare.get("blocking_reasons", []))
        quality["blocking_reasons"].extend(daycare.get("blocking_reasons", []))
    quality["excluded"]["babysitting_places"] = {
        "total_rows": len(daycare_points),
        "verified_rows": daycare.get("verified_point_count", 0),
        "excluded_rows": daycare.get("excluded_point_count", 0),
    }

    homepage = homepage_result or {}
    homepage_rows = homepage.get("current_yoi", {}).get("districts")
    if not isinstance(homepage_rows, list):
        homepage_rows = homepage.get("districts", [])
    homepage_by_district = {
        str(row.get("district_id")): row
        for row in homepage_rows
        if isinstance(row, Mapping) and row.get("district_id") is not None
    }
    daycare_by_district = {
        str(row.get("district_id")): row
        for row in daycare.get("districts", [])
        if row.get("district_id") is not None
    }
    annual_by_district = {
        str(row.get("district_id")): row
        for row in reference_year_row.get("districts", [])
        if row.get("district_id") is not None
    }

    current_rows: list[dict[str, Any]] = []
    for district in resolver.districts:
        district_id = str(district["district_id"])
        annual_row = annual_by_district.get(district_id, {})
        homepage_row = homepage_by_district.get(district_id, {})
        daycare_row = daycare_by_district.get(district_id, {})
        components = homepage_row.get("yoiComponents")
        if not isinstance(components, Mapping):
            components = {}
        current_rows.append(
            {
                **annual_row,
                "district_id": district_id,
                "district_name": district.get("district_name") or annual_row.get("district_name"),
                "opportunityIndex": _number(homepage_row.get("opportunityIndex")),
                "daycareCoverage": _number(daycare_row.get("value")),
                "daycareCoverageStatus": daycare.get("status"),
                "score_housing": _number(components.get("housing")),
                "estimatedWage": _number(homepage_row.get("adjusted_youth_wage")),
                "sourcePeriod": {
                    "fertility": [str(reference_year)],
                    "daycare": daycare_source_periods,
                },
            }
        )

    fafi = calculate_fafi_scores(current_rows)
    if daycare.get("status") != "observed":
        fafi["status"] = _merge_statuses(fafi.get("status"), daycare.get("status"))
        fafi["blocking_reasons"] = sorted(
            set(fafi.get("blocking_reasons", [])) | {"daycare_coverage_partial"}
        )
    for row in current_rows:
        fafi_row = fafi["districts"].get(str(row["district_id"]), {})
        row.update(fafi_row)
        row["fertilityLevel"] = _quartile_level(
            row.get("fertilityRate"),
            [item.get("fertilityRate") for item in current_rows],
        )

    scatter_points = [
        {
            "district_id": row["district_id"],
            "district_name": row.get("district_name"),
            "x": row.get("opportunityIndex"),
            "y": row.get("fertilityRate"),
        }
        for row in current_rows
    ]
    regression = calculate_ols_regression(
        [(point["x"], point["y"]) for point in scatter_points]
    )
    quality["coverage"] = {
        "district_count": len(current_rows),
        "expected_district_count": len(resolver.districts),
        "daycare_verified_point_count": daycare.get("verified_point_count", 0),
        "daycare_excluded_point_count": daycare.get("excluded_point_count", 0),
        "daycare_joined_village_count": daycare.get("joined_village_count", 0),
        "daycare_boundary_village_count": daycare.get("boundary_village_count", 0),
        "scatter_point_count": len(scatter_points),
        "scatter_regression_sample_size": regression["sample_size"],
    }
    quality["source_periods"] = _source_periods(loaded)
    if isinstance(homepage.get("_quality"), Mapping):
        quality["homepage_source_periods"] = dict(
            homepage["_quality"].get("source_periods") or {}
        )
        for dataset, periods in quality["homepage_source_periods"].items():
            if not isinstance(periods, list):
                continue
            quality["source_periods"][dataset] = sorted(
                set(quality["source_periods"].get(dataset, [])) | set(periods)
            )
        quality["proxy_usage"].extend(homepage["_quality"].get("proxy_usage", []))

    current_city = dict(reference_year_row.get("citySummary") or {})
    current_city["daycareCoverage"] = _number(daycare.get("value"))
    current_city["daycareCoverageStatus"] = daycare.get("status")
    current_city["sourcePeriod"] = {
        "fertility": [str(reference_year)],
        "daycare": daycare_source_periods,
    }
    current_status = _merge_statuses(
        reference_year_row.get("status"), daycare.get("status"), fafi.get("status")
    )
    return _sanitize(
        {
            "metric_id": "fertility",
            "calculation_version": "1",
            "generated_at": generated_at,
            "time_policy": {
                "annual_years_roc": annual_years,
                "reference_year_roc": reference_year,
                "daycare_radius_m": 1000,
                "current_yoi": "latest_available_snapshot",
            },
            "status": current_status,
            "source_period": quality["source_periods"],
            "coverage": quality["coverage"],
            "proxy_usage": quality["proxy_usage"],
            "blocking_reasons": sorted(set(quality["blocking_reasons"])),
            "citySummary": current_city,
            "districts": current_rows,
            "daycareCoverage": daycare,
            "fafi": fafi,
            "scatter": {
                "title": "生育率 vs. 青年就業機會指數",
                "x_label": "青年就業機會指數",
                "y_label": "青年生育率 (‰)",
                "points": scatter_points,
                "regression": regression,
            },
            "annual": annual,
            "_quality": quality,
        }
    )


def write_fertility_data(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    """Write public fertility analytics and its separate quality artifact."""

    root = Path(output_dir)
    quality = dict(result.get("_quality") or {})
    output = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(
        root / "analytics" / "fertility" / "all.json", _sanitize(output)
    )
    quality_path = atomic_json_write(
        root / "quality" / "analytics_fertility.json", _sanitize(quality)
    )
    return output_path, quality_path


def _birth_lookup(
    records: Iterable[Mapping[str, Any]], years: Iterable[int]
) -> dict[tuple[int, str], float]:
    allowed = {int(year) for year in years}
    output: dict[tuple[int, str], float] = {}
    for row in records:
        year = _roc_year(row)
        district_id = row.get("district_id")
        value = _number(row.get("value"))
        if year not in allowed or district_id is None or value is None:
            continue
        output[(year, str(district_id))] = output.get((year, str(district_id)), 0.0) + value
    return output


def _latest_population_lookup(
    records: Iterable[Mapping[str, Any]], years: Iterable[int]
) -> dict[tuple[int, str], dict[str, float]]:
    allowed = {int(year) for year in years}
    latest: dict[tuple[int, str, str], Mapping[str, Any]] = {}
    for row in records:
        year = _roc_year(row)
        district_id = row.get("district_id")
        metric = row.get("metric_id")
        if year not in allowed or district_id is None or metric not in {
            "people_total",
            "youth_18_35_total",
        }:
            continue
        key = (year, str(district_id), str(metric))
        existing = latest.get(key)
        if existing is None or _period_key(row) >= _period_key(existing):
            latest[key] = row
    output: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
    for (year, district_id, metric), row in latest.items():
        value = _number(row.get("value"))
        if value is not None:
            output[(year, district_id)][metric] = value
    return dict(output)


def _city_summary(
    rows: list[Mapping[str, Any]],
    existing: Mapping[str, Any],
    population_lookup: Mapping[tuple[int, str], Mapping[str, float]],
    year: int,
) -> dict[str, Any]:
    total_births = _sum_present(row.get("totalBirths") for row in rows)
    female_denominator = _number(existing.get("average_monthly_female_18_35"))
    fertility_rate = _number(existing.get("fertility_rate"))
    youth_total = _sum_present(
        population_lookup.get((year, str(row.get("district_id"))), {}).get(
            "youth_18_35_total"
        )
        for row in rows
    )
    people_total = _sum_present(
        population_lookup.get((year, str(row.get("district_id"))), {}).get("people_total")
        for row in rows
    )
    youth_ratio = _ratio(youth_total, people_total, multiplier=100)
    available_months = int(existing.get("available_months") or 0)
    complete_rows = sum(row.get("status") == "observed" for row in rows)
    status = _row_status(
        fertility_rate,
        youth_ratio,
        complete=available_months == 12 and complete_rows == len(rows),
    )
    return {
        "totalBirths": total_births,
        "fertilityRate": fertility_rate,
        "youthRatio": youth_ratio,
        "averageMonthlyFemale18_35": female_denominator,
        "availableMonths": available_months,
        "coverageRatio": _number(existing.get("coverage_ratio")) or 0.0,
        "status": status,
        "sourcePeriod": [str(year)],
    }


def _row_status(
    fertility_rate: Any, youth_ratio: Any, *, complete: bool
) -> str:
    if fertility_rate is None and youth_ratio is None:
        return "unavailable"
    if complete and fertility_rate is not None and youth_ratio is not None:
        return "observed"
    return "partial"


def _quartile_level(value: Any, values: Iterable[Any]) -> str | None:
    number = _number(value)
    valid = [item for item in (_number(value) for value in values) if item is not None]
    if number is None or not valid:
        return None
    q1 = _percentile(valid, 0.25)
    q3 = _percentile(valid, 0.75)
    return "low" if number <= q1 else "high" if number >= q3 else "medium"


def _merge_statuses(*statuses: Any) -> str:
    values = [status for status in statuses if status in {"observed", "partial", "unavailable"}]
    if not values or all(status == "unavailable" for status in values):
        return "unavailable"
    if "unavailable" in values or "partial" in values:
        return "partial"
    return "observed"


def _record_input(quality: dict[str, Any], item: CuratedSlice) -> None:
    current = quality["inputs"].setdefault(
        item.dataset, {"source_periods": [], "paths": [], "row_count": 0}
    )
    current["source_periods"] = sorted(
        set(current["source_periods"]) | set(item.source_periods)
    )
    current["paths"] = sorted(set(current["paths"]) | set(item.paths))
    current["row_count"] += len(item.records)
    quality["source_periods"][item.dataset] = list(item.source_periods)


def _record_failure(quality: dict[str, Any], dataset: str, reason: str) -> None:
    current = quality["inputs"].setdefault(
        dataset, {"source_periods": [], "paths": [], "row_count": 0}
    )
    current.setdefault("failures", []).append(reason)
    quality["warnings"].append(f"{dataset}: {reason}")
    quality["blocking_reasons"].append(f"{dataset}_unavailable")


def _roc_year(row: Mapping[str, Any]) -> int | None:
    period = str(row.get("period_start") or row.get("period_end") or "")
    if len(period) < 4 or not period[:4].isdigit():
        return None
    return int(period[:4]) - 1911


def _period_key(row: Mapping[str, Any]) -> str:
    return str(row.get("period_end") or row.get("period_start") or "")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _sum_present(values: Iterable[Any]) -> float | None:
    numbers = [_number(value) for value in values]
    numbers = [value for value in numbers if value is not None]
    return None if not numbers else sum(numbers)


def _ratio(numerator: Any, denominator: Any, *, multiplier: float) -> float | None:
    numerator_number = _number(numerator)
    denominator_number = _number(denominator)
    if numerator_number is None or denominator_number in (None, 0):
        return None
    return numerator_number / denominator_number * multiplier


def _mean_if_complete(values: Iterable[Any]) -> float | None:
    numbers = [_number(value) for value in values]
    return None if any(value is None for value in numbers) else sum(numbers) / len(numbers)


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


__all__ = [
    "calculate_annual_fertility_metrics",
    "calculate_fafi_scores",
    "generate_fertility_data",
    "write_fertility_data",
]
