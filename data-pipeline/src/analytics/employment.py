"""Employment-page analytics built on top of the homepage YOI result."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .config import HomepageAnalyticsConfig
from .homepage import generate_homepage_data
from .homepage_math import calculate_ols_regression
from .io import CuratedSlice, atomic_json_write


_COLLEGE_KEYWORDS = ("大學", "專科", "學士", "碩士", "博士")


def generate_employment_data(
    *,
    resolver: Any,
    config: HomepageAnalyticsConfig,
    homepage_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate the employment page contract from curated latest snapshots.

    YOI remains owned by homepage analytics.  This module only projects its
    five component scores and adds the two employment scatter plots.
    """

    homepage = (
        dict(homepage_result)
        if homepage_result is not None
        else generate_homepage_data(resolver=resolver, config=config)
    )
    generated_at = datetime.now(timezone.utc).isoformat()
    quality: dict[str, Any] = {
        "metric_id": "employment",
        "calculation_version": "1",
        "generated_at": generated_at,
        "inputs": {},
        "source_periods": {},
        "warnings": [],
        "blocking_reasons": [],
        "proxy_usage": [],
        "excluded": {},
    }

    vacancy_slice = resolver.latest("job_vacancies")
    house_slice = resolver.latest("house_prices")
    _record_input(quality, vacancy_slice)
    _record_input(quality, house_slice)
    vacancies = [dict(row) for row in vacancy_slice.records]
    houses = [dict(row) for row in house_slice.records]

    homepage_quality = homepage.get("_quality")
    if isinstance(homepage_quality, Mapping):
        quality["homepage_source_periods"] = dict(homepage_quality.get("source_periods") or {})
        for item in homepage_quality.get("proxy_usage", []):
            if isinstance(item, Mapping) and item.get("metric") == "adjusted_youth_wage":
                quality["proxy_usage"].append(dict(item))

    homepage_districts = homepage.get("current_yoi", {}).get("districts")
    if not isinstance(homepage_districts, list):
        homepage_districts = homepage.get("districts", [])
    district_rows = [dict(row) for row in homepage_districts if isinstance(row, Mapping)]

    vacancy_by_district: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in vacancies:
        if row.get("geo_level") != "district" or row.get("district_id") is None:
            continue
        vacancy_by_district[str(row["district_id"])].append(row)

    knowledge_ratios: dict[str, float | None] = {}
    for district_id, rows in vacancy_by_district.items():
        total = sum(_position_count(row) for row in rows)
        college = sum(
            _position_count(row)
            for row in rows
            if _requires_college_education(row)
        )
        knowledge_ratios[district_id] = None if total <= 0 else college / total * 100

    district_output: list[dict[str, Any]] = []
    scatter_one_points: list[dict[str, Any]] = []
    scatter_two_points: list[dict[str, Any]] = []
    for row in district_rows:
        district_id = str(row.get("district_id"))
        # Homepage stores the wage proxy in the documented unit 萬元／年;
        # house_price_median is raw TWD／坪 and is converted below.
        estimated_wage = _wage_wan(row.get("adjusted_youth_wage"))
        house_price = _to_wan(row.get("house_price_median"))
        monthly_wage = None if estimated_wage is None else estimated_wage / 12
        components = row.get("yoiComponents")
        if not isinstance(components, Mapping):
            components = {}
        district_output.append(
            {
                "district_id": row.get("district_id"),
                "district_name": row.get("district_name"),
                "opportunityIndex": row.get("opportunityIndex"),
                "retentionRiskLevel": row.get("retentionRiskLevel"),
                "score_job": components.get("job"),
                "score_salary": components.get("salary"),
                "score_talent": components.get("talent"),
                "score_housing": components.get("housing"),
                "score_transport": components.get("transport"),
                "yoiComponents": dict(components),
                "knowledge_job_ratio": knowledge_ratios.get(district_id),
                "estimated_wage": estimated_wage,
                "estimated_monthly_wage": monthly_wage,
                "house_price_median_wan": house_price,
                "quality_status": row.get("qualityStatus", "unavailable"),
                "sourcePeriods": dict(row.get("sourcePeriods") or {}),
            }
        )
        scatter_one_points.append(
            {
                "district_id": row.get("district_id"),
                "district_name": row.get("district_name"),
                "x": knowledge_ratios.get(district_id),
                "y": estimated_wage,
            }
        )
        scatter_two_points.append(
            {
                "district_id": row.get("district_id"),
                "district_name": row.get("district_name"),
                "x": monthly_wage,
                "y": house_price,
            }
        )

    quality["excluded"]["job_vacancies"] = {
        "total_rows": len(vacancies),
        "district_rows": sum(row.get("geo_level") == "district" for row in vacancies),
        "unmapped_district_rows": sum(row.get("district_id") is None for row in vacancies),
    }
    quality["excluded"]["house_prices"] = {
        "total_rows": len(houses),
        "unmapped_district_rows": sum(row.get("district_id") is None for row in houses),
    }

    regression_one = calculate_ols_regression(
        [(point["x"], point["y"]) for point in scatter_one_points]
    )
    regression_two = calculate_ols_regression(
        [(point["x"], point["y"]) for point in scatter_two_points]
    )
    quality["coverage"] = {
        "district_count": len(district_output),
        "plot1_point_count": len(scatter_one_points),
        "plot1_regression_sample_size": regression_one["sample_size"],
        "plot2_point_count": len(scatter_two_points),
        "plot2_regression_sample_size": regression_two["sample_size"],
    }

    result = {
        "metric_id": "employment",
        "calculation_version": "1",
        "generated_at": generated_at,
        "time_policy": {
            "current_yoi": "latest_available_snapshot",
            "annual_years_roc": list(config.annual_years_roc),
            "wage_note": "latest_available_within_or_near_annual_window",
        },
        "districts": district_output,
        "scatter": {
            "knowledge_job_vs_estimated_wage": {
                "title": "起薪與知識型職缺密度相關性（各行政區）",
                "x_label": "知識型職缺比例（%）",
                "y_label": "估算起薪（萬元／年）",
                "points": scatter_one_points,
                "regression": regression_one,
                "note": "X 軸為職缺要求大專以上學歷的比例（非居住人口教育程度）",
            },
            "monthly_wage_vs_house_price": {
                "title": "房價與平均薪資關聯（各行政區）",
                "x_label": "青年平均月薪（萬元）",
                "y_label": "每坪平均房價（萬元）",
                "points": scatter_two_points,
                "regression": regression_two,
                "note": "薪資為以房價代理估算之值；房價僅含住宅用（平溪例外使用全類型）",
            },
        },
        "_quality": quality,
    }
    return _sanitize(result)


def write_employment_data(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    """Write public employment analytics and its separate quality artifact."""

    root = Path(output_dir)
    quality = dict(result.get("_quality") or {})
    output = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(
        root / "analytics" / "employment" / "all.json", _sanitize(output)
    )
    quality_path = atomic_json_write(
        root / "quality" / "analytics_employment.json", _sanitize(quality)
    )
    return output_path, quality_path


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


def _requires_college_education(row: Mapping[str, Any]) -> bool:
    raw = row.get("raw_record")
    if isinstance(raw, Mapping):
        education = raw.get("EDGRDESC（最低學歷要求）", raw.get("EDGRDESC", ""))
    else:
        education = row.get("EDGRDESC（最低學歷要求）", row.get("EDGRDESC", ""))
    text = str(education or "")
    return any(keyword in text for keyword in _COLLEGE_KEYWORDS)


def _position_count(row: Mapping[str, Any]) -> float:
    value = row.get("position_count")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) and number >= 0 else 0.0


def _to_wan(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number / 10000


def _wage_wan(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _sanitize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


__all__ = ["generate_employment_data", "write_employment_data"]
