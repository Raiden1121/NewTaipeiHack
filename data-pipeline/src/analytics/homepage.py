"""Homepage KPI, current YOI, election, and service coverage integration."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Mapping

from shapely.geometry import shape

from .annual_metrics import calculate_annual_fertility, calculate_annual_population, calculate_budget_series
from .config import HomepageAnalyticsConfig
from .data_gaps import explain_reason_codes
from .elections import calculate_youth_candidacy
from .homepage_math import calculate_quartile_risk, normalize_p5_p95, shannon_entropy, weighted_score
from .input_resolver import HomepageInputResolver
from .io import CuratedSlice, atomic_json_write
from .service_coverage import calculate_service_coverage


def generate_homepage_data(
    *, resolver: HomepageInputResolver, config: HomepageAnalyticsConfig
) -> dict[str, Any]:
    """Read curated inputs and generate the complete homepage payload."""

    quality: dict[str, Any] = {
        "metric_id": "homepage",
        "calculation_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {},
        "warnings": [],
        "blocking_reasons": [],
        "proxy_usage": [],
        "excluded": {},
    }
    loaded: dict[str, CuratedSlice] = {}

    def load_periods(dataset: str, periods: list[str], *, available: bool = True) -> list[dict[str, Any]]:
        try:
            item = (
                resolver.available_periods(dataset, periods)
                if available and hasattr(resolver, "available_periods")
                else resolver.periods(dataset, periods)
            )
        except (AttributeError, ValueError) as exc:
            _record_input_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, dataset, item)
        loaded[f"{dataset}:{','.join(item.source_periods)}"] = item
        return [dict(row) for row in item.records]

    def load_latest(dataset: str) -> list[dict[str, Any]]:
        try:
            item = resolver.latest(dataset)
        except (AttributeError, ValueError) as exc:
            _record_input_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, dataset, item)
        loaded[dataset] = item
        return [dict(row) for row in item.records]

    def load_all(dataset: str) -> list[dict[str, Any]]:
        try:
            item = resolver.all_available(dataset)
        except (AttributeError, ValueError) as exc:
            _record_input_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, dataset, item)
        loaded[dataset] = item
        return [dict(row) for row in item.records]

    annual_years = list(config.annual_years_roc)
    # Election events fall outside the annual window, so their denominators must
    # be requested explicitly; available_periods() skips the years the source
    # never published instead of failing the whole run.
    population_years = set(annual_years) | {min(annual_years) - 1} | set(config.election_years_roc)
    population_periods = [
        f"{year:03d}{month:02d}"
        for year in sorted(population_years)
        for month in range(1, 13)
    ]
    population_records = load_periods("population", population_periods)
    births_records = load_periods("births", [f"{year:03d}" for year in annual_years])
    wage_records: list[dict[str, Any]] = []
    college_records: list[dict[str, Any]] = []
    for dataset, target in (("wages", wage_records), ("college_majors", college_records)):
        target.extend(load_periods(dataset, [f"{year:03d}" for year in annual_years]))
    budget_records = load_all("youth_budgets")
    election_records = load_all("elections")
    snapshot_datasets = (
        "job_vacancies",
        "job_vacancy_salaries",
        "rentals",
        "house_prices",
        "bus_stops",
        "railway_stops",
        "bike_stops",
        "vt_courses",
        "training_numbers",
    )
    snapshots = {dataset: load_latest(dataset) for dataset in snapshot_datasets}
    talent_records = load_all("talent_demand")

    annual_population = calculate_annual_population(
        population_records, annual_years_roc=annual_years
    )
    annual_fertility = calculate_annual_fertility(
        births_records,
        population_records,
        annual_years_roc=annual_years,
    )
    budget_series = calculate_budget_series(
        budget_records,
        budget_records,
        annual_years_roc=annual_years,
    )
    elections = calculate_youth_candidacy(
        election_records,
        population_records,
        election_years_roc=config.election_years_roc,
    )

    # Village inputs are separate from the existing district population contract.
    village_population_periods = [config.village_population_reference_period]
    village_population = load_periods("population_villages", village_population_periods)
    boundaries = load_latest("village_boundaries")
    service_points = load_latest("youth_service_points")
    service_coverage = calculate_service_coverage(
        service_points,
        boundaries,
        village_population,
        radius_m=config.service_radius_m,
    )
    if service_coverage["status"] != "observed":
        quality["warnings"].extend(
            reason for reason in service_coverage.get("blocking_reasons", []) if reason not in quality["warnings"]
        )
        quality["blocking_reasons"] = sorted(
            set(quality["blocking_reasons"]) | set(service_coverage.get("blocking_reasons", []))
        )
    quality["excluded"]["youth_service_points"] = {
        "total_rows": service_coverage.get("verified_point_count", 0)
        + service_coverage.get("excluded_point_count", 0),
        "verified_rows": service_coverage.get("verified_point_count", 0),
        "excluded_rows": service_coverage.get("excluded_point_count", 0),
    }

    current_yoi = _calculate_current_yoi(
        districts=resolver.districts,
        population_records=population_records,
        population_reference_year_roc=config.population_reference_year_roc,
        snapshots=snapshots,
        talent_records=talent_records,
        wages=wage_records,
        house_prices=snapshots.get("house_prices", []),
        college_records=college_records,
        config=config,
        boundaries=boundaries,
        quality=quality,
        source_periods=_source_periods(loaded),
    )
    _attach_homepage_district_metrics(
        current_yoi,
        annual_fertility=annual_fertility,
        service_coverage=service_coverage,
        elections=elections,
        latest_annual_year=annual_years[-1],
        latest_election_year=max(config.election_years_roc),
    )
    kpi = _build_homepage_kpi(annual_population, annual_years, quality)
    policy = _build_homepage_policy(budget_series["trend"])

    result = {
        "metric_id": "homepage",
        "calculation_version": "1",
        "generated_at": quality["generated_at"],
        "time_policy": {
            "annual_years_roc": annual_years,
            "current_yoi": "latest_available_snapshot",
            "election_years_roc": list(config.election_years_roc),
        },
        "current_yoi": {
            "population_reference_year_roc": config.population_reference_year_roc,
            "districts": current_yoi,
        },
        # Compatibility projection for the existing frontend adapter. The
        # canonical contract remains current_yoi/annual/elections below.
        "kpi": kpi,
        "districts": current_yoi,
        "policy": policy,
        "annual": {
            "population": annual_population,
            "fertility": annual_fertility,
            "budget_trend": budget_series["trend"],
            "budget_execution": budget_series["execution"],
        },
        "elections": {
            "city_councilor_t1": elections["city_councilor_t1"],
            "borough_chief_v1": elections["borough_chief_v1"],
            "city_councilor_t1_citywide": elections["city_councilor_t1_citywide"],
        },
        "service_coverage": service_coverage,
        "_quality": {
            **quality,
            "source_limitations": explain_reason_codes(
                list(quality["blocking_reasons"])
                + [str(item.get("reason")) for item in quality["proxy_usage"] if isinstance(item, Mapping)],
                config_dir=Path(__file__).resolve().parents[2] / "config",
            ),
            "source_periods": _source_periods(loaded),
            "election_quality": elections.get("_quality", {}),
            "service_coverage": {
                "status": service_coverage.get("status"),
                "verified_point_count": service_coverage.get("verified_point_count", 0),
                "excluded_point_count": service_coverage.get("excluded_point_count", 0),
            },
        },
    }
    return _sanitize(result)


def _attach_homepage_district_metrics(
    districts: list[dict[str, Any]],
    *,
    annual_fertility: Mapping[str, Any],
    service_coverage: Mapping[str, Any],
    elections: Mapping[str, Any],
    latest_annual_year: int,
    latest_election_year: int,
) -> None:
    fertility_year = next(
        (
            year
            for year in annual_fertility.get("years", [])
            if year.get("year_roc") == latest_annual_year
        ),
        {},
    )
    fertility_by_district = {
        str(row.get("district_id")): row
        for row in fertility_year.get("districts", [])
        if row.get("district_id") is not None
    }
    service_by_district = {
        str(row.get("district_id")): row
        for row in service_coverage.get("districts", [])
        if row.get("district_id") is not None
    }
    participation_by_district = {
        str(row.get("district_id")): row
        for row in elections.get("borough_chief_v1", [])
        if row.get("election_year_roc") == latest_election_year
        and row.get("district_id") is not None
    }
    for row in districts:
        district_id = str(row["district_id"])
        fertility = fertility_by_district.get(district_id, {})
        service = service_by_district.get(district_id, {})
        participation = participation_by_district.get(district_id, {})
        row["fertilityRate"] = fertility.get("fertility_rate")
        row["fertilityVsCityAvg"] = fertility.get("fertilityVsCityAvg")
        row["serviceCoverageRate"] = service.get("value")
        row["serviceCoverageStatus"] = service_coverage.get("status", "unavailable")
        row["youthParticipationIndex"] = participation.get("youth_candidacy_rate")
        row["youthCandidacyRatePer100k"] = participation.get("youth_candidacy_rate")


def _build_homepage_kpi(
    annual_population: Mapping[str, Any], years: list[int], quality: dict[str, Any]
) -> dict[str, Any]:
    rows = list(annual_population.get("years", []))
    current = next((row for row in rows if row.get("year_roc") == years[-1]), {})
    previous = next((row for row in rows if row.get("year_roc") == years[-2]), {}) if len(years) > 1 else {}
    city = current.get("city", {})
    previous_city = previous.get("city", {})
    national_youth = 4_820_000
    quality["proxy_usage"].append(
        {
            "metric": "national_youth_population",
            "reason": "homepage_fallback_constant",
            "value": national_youth,
        }
    )
    people = _number(city.get("people_total"))
    youth = _number(city.get("youth_18_35_total"))
    previous_youth = _number(previous_city.get("youth_18_35_total"))
    return {
        "nationalYouthPopulation": national_youth,
        "nationalYouthPopulationQuality": "proxy",
        "cityYouthPopulation": youth,
        "cityYouthPopulationShare": None if people in (None, 0) or youth is None else youth / people * 100,
        "cityYouthPopulationYoY": _yoy(youth, previous_youth),
        "referenceYearRoc": years[-1],
    }


def _build_homepage_policy(trend: list[dict[str, Any]]) -> dict[str, Any]:
    available = [row for row in trend if row.get("legal_budget_amount") is not None]
    latest = available[-1] if available else {}
    return {
        "budgetTrend": [
            {
                "year_roc": row.get("year_roc"),
                "value_thousand": row.get("legal_budget_amount"),
                "budget_yoy_percent": row.get("budget_yoy_percent"),
                "quality_status": row.get("quality_status"),
            }
            for row in trend
        ],
        "currentBudget": latest.get("legal_budget_amount"),
        "budgetYoY": latest.get("budget_yoy_percent"),
        "executionRate": latest.get("execution_rate"),
        "executionFailure": latest.get("execution_failure"),
    }


def write_homepage_data(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    """Write public homepage JSON and its separate quality artifact."""

    root = Path(output_dir)
    quality = dict(result.get("_quality") or {})
    output = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(root / "analytics" / "homepage" / "all.json", _sanitize(output))
    quality_path = atomic_json_write(
        root / "quality" / "analytics_homepage.json", _sanitize(quality)
    )
    return output_path, quality_path


def _calculate_current_yoi(
    *,
    districts: list[dict[str, Any]],
    population_records: list[dict[str, Any]],
    population_reference_year_roc: int,
    snapshots: Mapping[str, list[dict[str, Any]]],
    talent_records: list[dict[str, Any]],
    wages: list[dict[str, Any]],
    house_prices: list[dict[str, Any]],
    college_records: list[dict[str, Any]],
    config: HomepageAnalyticsConfig,
    boundaries: list[dict[str, Any]],
    quality: dict[str, Any],
    source_periods: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    district_ids = [str(row["district_id"]) for row in districts]
    names = {str(row["district_id"]): row["district_name"] for row in districts}
    population = _population_anchor(population_records, population_reference_year_roc)
    youth_city = sum(
        value.get("youth_18_35_total", 0) or 0 for value in population.values()
    )
    areas = _district_areas(boundaries)
    vacancies = snapshots.get("job_vacancies", [])
    salary_rows = snapshots.get("job_vacancy_salaries", [])
    rentals = snapshots.get("rentals", [])
    houses = snapshots.get("house_prices", [])
    vt_courses = snapshots.get("vt_courses", [])
    training = snapshots.get("training_numbers", [])
    buses = snapshots.get("bus_stops", [])
    rails = snapshots.get("railway_stops", [])
    bikes = snapshots.get("bike_stops", [])
    latest_wage, wage_quality = _latest_youth_wage(wages, config.annual_years_roc)
    if wage_quality != "observed":
        quality["proxy_usage"].append({"metric": "adjusted_youth_wage", "reason": wage_quality})
    city_house_values = [_number(row.get("price_per_ping")) for row in houses]
    city_house_median = _median(city_house_values)
    salary_values = [
        _salary_midpoint(row)
        for row in salary_rows
        if _salary_midpoint(row) is not None
    ]
    city_salary_median = _median(salary_values)
    quality["excluded"]["job_vacancy_salaries"] = {
        "total_rows": len(salary_rows),
        "complete_midpoint_rows": len(salary_values),
        "complete_salary_position_count": sum(
            _number(row.get("position_count")) or 0
            for row in salary_rows
            if _salary_midpoint(row) is not None
        ),
        "excluded_no_complete_bounds": len(salary_rows) - len(salary_values),
        "unmapped_district_rows": sum(row.get("district_id") is None for row in salary_rows),
    }
    quality["excluded"]["job_vacancies"] = {
        "total_rows": len(vacancies),
        "district_rows": sum(row.get("geo_level") == "district" for row in vacancies),
        "total_position_count": sum(
            _number(row.get("position_count")) or 0
            for row in vacancies
            if row.get("geo_level") == "district"
        ),
        "unmapped_district_rows": sum(row.get("district_id") is None for row in vacancies),
    }
    for dataset in ("bus_stops", "bike_stops"):
        rows = snapshots.get(dataset, [])
        quality["excluded"][dataset] = {
            "total_rows": len(rows),
            "unmapped_district_rows": sum(row.get("district_id") is None for row in rows),
        }
    quality["excluded"]["college_majors"] = {
        "total_rows": len(college_records),
        "null_district_rows": sum(row.get("district_id") is None for row in college_records),
    }
    high_salary_threshold = None if city_salary_median is None else city_salary_median * 1.5
    talent_yoy = _talent_demand_yoy(talent_records, config.annual_years_roc)
    college_by_district: dict[str, float] = defaultdict(float)
    for row in college_records:
        district_id = row.get("district_id")
        student_count = _number(row.get("student_count"))
        if district_id is not None and student_count is not None:
            college_by_district[str(district_id)] += student_count
    vt_by_district = {str(row.get("district_id")): _number(row.get("value")) for row in vt_courses if row.get("district_id") is not None}
    observed_vt = [value for value in vt_by_district.values() if value is not None]
    vt_minimum = min(observed_vt) if observed_vt else 32.0
    train_people = sum(_number(row.get("training_people")) or 0 for row in training)
    training_per_10k = None if youth_city <= 0 else train_people / youth_city * 10000
    raw: dict[str, dict[str, Any]] = {}
    for district_id in district_ids:
        youth = _number(population.get(district_id, {}).get("youth_18_35_total"))
        district_vacancies = [row for row in vacancies if str(row.get("district_id")) == district_id and row.get("geo_level") == "district"]
        vacancy_positions = sum(_number(row.get("position_count")) or 0 for row in district_vacancies)
        occupation_counts: dict[str, float] = defaultdict(float)
        for row in district_vacancies:
            category = _occupation_category(row) or "unknown"
            occupation_counts[category] += _number(row.get("position_count")) or 0
        district_salaries = [row for row in salary_rows if str(row.get("district_id")) == district_id]
        valid_salaries = [_salary_midpoint(row) for row in district_salaries if _salary_midpoint(row) is not None]
        high_count = sum(
            _number(row.get("position_count")) or 0
            for row in district_salaries
            if _salary_midpoint(row) is not None and high_salary_threshold is not None and _salary_midpoint(row) > high_salary_threshold
        )
        district_house_all = [_number(row.get("price_per_ping")) for row in houses if str(row.get("district_id")) == district_id]
        district_house_residential = [
            _number(row.get("price_per_ping"))
            for row in houses
            if str(row.get("district_id")) == district_id and _is_residential_house(row)
        ]
        if not district_house_residential and names[district_id] == "平溪區":
            district_house_residential = district_house_all[:]
            _append_proxy(quality, "house_price", district_id, "pingxi_all_types")
        district_rents = [_number(row.get("rent_total")) for row in rentals if str(row.get("district_id")) == district_id]
        rent_values = [value for value in district_rents if value is not None]
        house_values = [value for value in district_house_residential if value is not None]
        rent_median = _median(rent_values)
        house_median = _median(house_values)
        if rent_median is None:
            all_rents = [_number(row.get("rent_total")) for row in rentals]
            rent_median = _minimum(all_rents)
            if rent_median is not None:
                _append_proxy(quality, "rent", district_id, "observed_minimum")
        if house_median is None:
            house_median = _minimum(
                [_number(row.get("price_per_ping")) for row in houses if _is_residential_house(row)]
            )
            if house_median is not None:
                _append_proxy(quality, "house_price", district_id, "residential_observed_minimum")
        price_ratio = None
        if city_house_median and district_house_all:
            district_all_median = _median(district_house_all)
            price_ratio = None if district_all_median is None else district_all_median / city_house_median
        adjusted_wage = None if latest_wage is None or price_ratio is None else latest_wage * price_ratio
        vt_value = vt_by_district.get(district_id)
        vt_quality = "observed"
        if vt_value is None and observed_vt:
            vt_value = vt_minimum
            vt_quality = "imputed"
            _append_proxy(quality, "vt_courses", district_id, "observed_minimum")
        area = areas.get(district_id)
        raw[district_id] = {
            "district_id": district_id,
            "district_name": names[district_id],
            "youth_18_35_total": youth,
            "vacancies_per_10k_youth": None if not youth else vacancy_positions / youth * 10000,
            "occupation_shannon_index": shannon_entropy(occupation_counts),
            "talent_demand_yoy": talent_yoy,
            "salary_median": _median(valid_salaries),
            "high_salary_ratio": None if vacancy_positions <= 0 else high_count / vacancy_positions,
            "adjusted_youth_wage": adjusted_wage,
            "college_student_density": None if area is None else college_by_district.get(district_id, 0.0) / area,
            "vt_course_count": vt_value,
            "training_people_per_10k_youth": training_per_10k,
            "rent_median": rent_median,
            "house_price_median": house_median,
            "rent_wage_ratio": None if rent_median is None or _median(valid_salaries) in (None, 0) else rent_median / _median(valid_salaries),
            "bus_stops_per_10k_youth": None if not youth else sum(str(row.get("district_id")) == district_id for row in buses) / youth * 10000,
            "railway_stop_density": None if area is None else sum(str(row.get("district_id")) == district_id for row in rails) / area,
            "bike_stop_density": None if area is None else sum(str(row.get("district_id")) == district_id for row in bikes) / area,
            "quality_flags": [flag for flag in (["vt_imputed"] if vt_quality == "imputed" else []) if flag],
        }
    normalized: dict[str, dict[str, float | None]] = {}
    columns = (
        ("vacancies_per_10k_youth", False),
        ("occupation_shannon_index", False),
        ("talent_demand_yoy", False),
        ("salary_median", False),
        ("high_salary_ratio", False),
        ("adjusted_youth_wage", False),
        ("college_student_density", False),
        ("vt_course_count", False),
        ("training_people_per_10k_youth", False),
        ("rent_median", True),
        ("house_price_median", True),
        ("rent_wage_ratio", True),
        ("bus_stops_per_10k_youth", False),
        ("railway_stop_density", False),
        ("bike_stop_density", False),
    )
    for column, inverse in columns:
        values = {district_id: raw[district_id].get(column) for district_id in district_ids}
        normalized[column] = normalize_p5_p95(
            values,
            inverse=inverse,
            constant_value=float(config.normalization.get("constant_value", 50)),
        )
    scores: dict[str, float | None] = {}
    output: list[dict[str, Any]] = []
    for district_id in district_ids:
        norm = {column: normalized[column].get(district_id) for column, _ in columns}
        components = {
            "job": weighted_score(
                {
                    "vacancies_per_10k_youth": norm["vacancies_per_10k_youth"],
                    "occupation_shannon_index": norm["occupation_shannon_index"],
                    "talent_demand_yoy": norm["talent_demand_yoy"],
                },
                {"vacancies_per_10k_youth": 0.5, "occupation_shannon_index": 0.3, "talent_demand_yoy": 0.2},
            ),
            "salary": weighted_score(
                {"salary_median": norm["salary_median"], "high_salary_ratio": norm["high_salary_ratio"], "adjusted_youth_wage": norm["adjusted_youth_wage"]},
                {"salary_median": 0.4, "high_salary_ratio": 0.3, "adjusted_youth_wage": 0.3},
            ),
            "talent": weighted_score(
                {"college_student_density": norm["college_student_density"], "vt_course_count": norm["vt_course_count"], "training_people_per_10k_youth": norm["training_people_per_10k_youth"]},
                {"college_student_density": 0.3, "vt_course_count": 0.35, "training_people_per_10k_youth": 0.35},
            ),
            "housing": weighted_score(
                {"rent_median": norm["rent_median"], "house_price_median": norm["house_price_median"], "rent_wage_ratio": norm["rent_wage_ratio"]},
                {"rent_median": 0.35, "house_price_median": 0.35, "rent_wage_ratio": 0.3},
            ),
            "transport": weighted_score(
                {"bus_stops_per_10k_youth": norm["bus_stops_per_10k_youth"], "railway_stop_density": norm["railway_stop_density"], "bike_stop_density": norm["bike_stop_density"]},
                {"bus_stops_per_10k_youth": 0.35, "railway_stop_density": 0.4, "bike_stop_density": 0.25},
            ),
        }
        score = weighted_score(components, config.yoi_weights)
        scores[district_id] = score
        output.append(
            {
                **raw[district_id],
                "opportunityIndex": None if score is None else round(score, 6),
                "yoiComponents": components,
                "normalizedInputs": norm,
                "sourcePeriods": dict(source_periods),
                "qualityStatus": "observed" if score is not None else "unavailable",
            }
        )
    risks = calculate_quartile_risk(scores)
    for row in output:
        row["retentionRiskLevel"] = risks.get(row["district_id"], "unavailable")
        row.pop("quality_flags", None)
    return output


def _record_input(quality: dict[str, Any], dataset: str, item: CuratedSlice) -> None:
    current = quality["inputs"].setdefault(dataset, {"source_periods": [], "paths": [], "row_count": 0})
    current["source_periods"] = sorted(set(current["source_periods"]) | set(item.source_periods))
    current["paths"] = sorted(set(current["paths"]) | set(item.paths))
    current["row_count"] += len(item.records)


def _record_input_failure(quality: dict[str, Any], dataset: str, reason: str) -> None:
    current = quality["inputs"].setdefault(dataset, {"source_periods": [], "paths": [], "row_count": 0})
    current.setdefault("failures", []).append(reason)
    quality["warnings"].append(f"{dataset}: {reason}")


def _population_anchor(records: list[dict[str, Any]], roc_year: int) -> dict[str, dict[str, Any]]:
    target_year = 1911 + roc_year
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in records:
        if str(row.get("period_start") or "")[:4] != str(target_year):
            continue
        district_id = row.get("district_id")
        metric = row.get("metric_id")
        if district_id is None or metric not in {"people_total", "youth_18_35_total", "youth_18_35_female"}:
            continue
        key = (str(district_id), str(metric))
        if key not in latest or str(row.get("period_end") or "") > str(latest[key].get("period_end") or ""):
            latest[key] = row
    output: dict[str, dict[str, Any]] = defaultdict(dict)
    for (district_id, metric), row in latest.items():
        output[district_id][metric] = _number(row.get("value"))
    return dict(output)


def _district_areas(boundaries: list[dict[str, Any]]) -> dict[str, float]:
    areas: dict[str, float] = defaultdict(float)
    for row in boundaries:
        district_id = row.get("district_id")
        geometry = row.get("geometry")
        if district_id is None or not isinstance(geometry, Mapping):
            continue
        try:
            polygon = shape(geometry)
        except (TypeError, ValueError):
            continue
        if polygon.is_empty or not polygon.is_valid:
            continue
        areas[str(district_id)] += polygon.area / 1_000_000
    return dict(areas)


def _latest_youth_wage(records: list[dict[str, Any]], years: list[int]) -> tuple[float | None, str]:
    candidates = [
        row for row in records
        if "25-29" in str(row.get("official_age_group") or "")
        and row.get("statistic_method") in {"平均數", "中位數"}
        and _number(row.get("value")) is not None
    ]
    if not candidates:
        return None, "unavailable"
    candidates.sort(key=lambda row: str(row.get("period_start") or ""), reverse=True)
    selected = candidates[0]
    year = int(str(selected.get("period_start"))[:4]) - 1911
    if year not in years:
        return _number(selected.get("value")), "latest_available_outside_window_official_age_group_proxy"
    return _number(selected.get("value")), "latest_available_official_age_group_proxy"


def _talent_demand_yoy(records: list[dict[str, Any]], years: list[int]) -> float | None:
    totals: dict[int, float] = defaultdict(float)
    for row in records:
        period = str(row.get("period_start") or "")
        value = _number(row.get("new_demand_count"))
        if len(period) >= 4 and value is not None:
            year = int(period[:4]) - 1911
            if year in years:
                totals[year] += value
    available = sorted(totals)
    if len(available) < 2 or totals[available[-2]] == 0:
        return None
    return (totals[available[-1]] - totals[available[-2]]) / totals[available[-2]] * 100


def _occupation_category(row: Mapping[str, Any]) -> str | None:
    raw = row.get("raw_record")
    if not isinstance(raw, Mapping):
        return None
    for key, value in raw.items():
        if "職務大類別名稱" in str(key) or str(key) in {"occupation", "category"}:
            return str(value) if value else None
    return None


def _is_residential_house(row: Mapping[str, Any]) -> bool:
    transaction_type = str(row.get("transaction_type") or "")
    if transaction_type == "住宅用":
        return True
    raw = row.get("raw_record")
    if not isinstance(raw, Mapping):
        return False
    usage = str(raw.get("rps12") or "")
    land_use = str(raw.get("rps04") or "")
    residential_usage = any(marker in usage for marker in ("住家", "住宅", "集合住宅"))
    residential_land = "住宅區" in land_use or land_use.strip() in {"住", "住宅"}
    return residential_usage or residential_land


def _salary_midpoint(row: Mapping[str, Any]) -> float | None:
    lower = _number(row.get("salary_lower"))
    upper = _number(row.get("salary_upper"))
    midpoint = _number(row.get("salary_midpoint"))
    return None if lower is None or upper is None or midpoint is None else midpoint


def _source_periods(loaded: Mapping[str, CuratedSlice]) -> dict[str, list[str]]:
    output: dict[str, list[str]] = defaultdict(list)
    for key, item in loaded.items():
        dataset = key.split(":", 1)[0]
        output[dataset] = sorted(set(output[dataset]) | set(item.source_periods))
    return dict(output)


def _append_proxy(quality: dict[str, Any], metric: str, district_id: str, reason: str) -> None:
    quality["proxy_usage"].append({"metric": metric, "district_id": district_id, "reason": reason})


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _median(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None and math.isfinite(value)]
    return None if not cleaned else float(median(cleaned))


def _minimum(values: list[float | None]) -> float | None:
    cleaned = [value for value in values if value is not None and math.isfinite(value)]
    return None if not cleaned else min(cleaned)


def _yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous * 100


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


__all__ = ["generate_homepage_data", "write_homepage_data"]
