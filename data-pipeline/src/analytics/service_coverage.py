"""Spatial service coverage analytics for verified startup-base points."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import unary_union


_WGS84_TO_TWD97 = Transformer.from_crs("EPSG:4326", "EPSG:3826", always_xy=True)


def calculate_service_coverage(
    service_points: Iterable[Mapping[str, Any]],
    village_boundaries: Iterable[Mapping[str, Any]],
    village_population: Iterable[Mapping[str, Any]],
    *,
    radius_m: float = 2500,
) -> dict[str, Any]:
    """Allocate village youth population by the area covered by union buffers."""

    return calculate_population_service_coverage(
        service_points,
        village_boundaries,
        village_population,
        radius_m=radius_m,
        population_field="youth_18_35_total",
        metric_id="serviceCoverageRate",
        output_prefix="youth",
        source_datasets=[
            "youth_service_points",
            "village_boundaries",
            "population_villages",
        ],
    )


def calculate_population_service_coverage(
    service_points: Iterable[Mapping[str, Any]],
    village_boundaries: Iterable[Mapping[str, Any]],
    village_population: Iterable[Mapping[str, Any]],
    *,
    radius_m: float = 2500,
    population_field: str = "youth_18_35_total",
    metric_id: str = "serviceCoverageRate",
    output_prefix: str = "youth",
    source_datasets: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Allocate any village population field by union-buffer area coverage."""

    if isinstance(radius_m, bool) or not isinstance(radius_m, (int, float)) or radius_m <= 0:
        raise ValueError("radius_m must be a positive number")
    point_rows = [dict(row) for row in service_points]
    valid_points: list[Point] = []
    for row in point_rows:
        point = _point_3826(row)
        if point is not None and row.get("geocode_status") == "matched":
            valid_points.append(point)
    excluded_point_count = len(point_rows) - len(valid_points)
    default_sources = [
        "service_points",
        "village_boundaries",
        "population_villages",
    ]
    base = {
        "metric_id": metric_id,
        "radius_m": float(radius_m),
        "population_field": population_field,
        "verified_point_count": len(valid_points),
        "excluded_point_count": excluded_point_count,
        "source_datasets": list(source_datasets or default_sources),
    }
    if not valid_points:
        return {
            **base,
            "value": None,
            "status": "unavailable",
            "blocking_reasons": ["no_verified_service_points"],
            "districts": [],
        }

    boundary_rows = _index_boundaries(village_boundaries)
    population_rows = _index_population(village_population)
    blocking_reasons: list[str] = []
    if not boundary_rows:
        blocking_reasons.append("village_boundaries_not_published")
    if not population_rows:
        blocking_reasons.append(
            "village_youth_population_not_published"
            if output_prefix == "youth"
            else "village_population_not_published"
        )
    covered_union = unary_union([point.buffer(float(radius_m)) for point in valid_points])
    district_totals: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "covered_population": 0.0,
            "target_population": 0.0,
            "village_count": 0,
            "covered_village_count": 0,
        }
    )
    village_details: list[dict[str, Any]] = []
    matched_population_count = 0
    for village_code, boundary in boundary_rows.items():
        population = population_rows.get(village_code)
        if population is None:
            continue
        matched_population_count += 1
        target_population = population.get(population_field)
        if not _finite_non_negative(target_population):
            continue
        area = float(boundary["geometry"].area)
        if area <= 0:
            continue
        intersection = covered_union.intersection(boundary["geometry"])
        ratio = max(0.0, min(1.0, float(intersection.area) / area))
        covered_population = ratio * float(target_population)
        district_id = population.get("district_id") or boundary.get("district_id")
        if district_id is None:
            continue
        district_name = population.get("district_name") or boundary.get("district_name")
        district_key = str(district_id)
        total = district_totals[district_key]
        total["district_name"] = district_name
        total["covered_population"] += covered_population
        total["target_population"] += float(target_population)
        total["village_count"] += 1
        total["covered_village_count"] += int(ratio > 0)
        village_detail = {
            "village_code": village_code,
            "district_id": district_key,
            "district_name": district_name,
            "target_population": int(target_population)
            if float(target_population).is_integer()
            else float(target_population),
            "covered_population": covered_population,
            "coverage_ratio": ratio,
        }
        if output_prefix == "youth":
            village_detail["youth_18_35_total"] = village_detail["target_population"]
            village_detail["covered_youth"] = covered_population
        village_details.append(village_detail)
    if not district_totals:
        blocking_reasons.append("no_boundary_population_join")
    expected_village_count = len(boundary_rows)
    population_coverage_ratio = (
        matched_population_count / expected_village_count if expected_village_count else 0.0
    )
    if expected_village_count and matched_population_count < expected_village_count:
        blocking_reasons.append("incomplete_village_population_coverage")
    total_population = sum(item["target_population"] for item in district_totals.values())
    total_covered = sum(item["covered_population"] for item in district_totals.values())
    value = None if total_population <= 0 else total_covered / total_population * 100.0
    status = "unavailable" if value is None else ("partial" if excluded_point_count or blocking_reasons else "observed")
    districts = []
    for district_id in sorted(district_totals):
        item = district_totals[district_id]
        district_value = (
            None
            if item["target_population"] <= 0
            else item["covered_population"] / item["target_population"] * 100.0
        )
        district_item = {
            "district_id": district_id,
            "district_name": item.get("district_name"),
            "value": district_value,
            "covered_population": item["covered_population"],
            "target_population": item["target_population"],
            "village_count": item["village_count"],
            "covered_village_count": item["covered_village_count"],
        }
        if output_prefix == "youth":
            district_item["covered_youth"] = item["covered_population"]
            district_item["youth_population"] = item["target_population"]
        districts.append(district_item)
    return {
        **base,
        "value": value,
        "status": status,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "population_coverage_ratio": population_coverage_ratio,
        "boundary_village_count": expected_village_count,
        "joined_village_count": matched_population_count,
        "districts": districts,
        "villages": village_details,
    }


def _index_boundaries(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for raw in rows:
        code = raw.get("village_code")
        geometry = raw.get("geometry")
        if not code or not isinstance(geometry, Mapping):
            continue
        try:
            polygon = shape(geometry)
        except (TypeError, ValueError):
            continue
        if polygon.is_empty or not polygon.is_valid or polygon.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        indexed[str(code)] = {**dict(raw), "geometry": polygon}
    return indexed


def _index_population(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for raw in rows:
        code = raw.get("village_code")
        if code is None:
            continue
        candidate = dict(raw)
        existing = indexed.get(str(code))
        if existing is None or _period_key(candidate) >= _period_key(existing):
            indexed[str(code)] = candidate
    return indexed


def _period_key(row: Mapping[str, Any]) -> str:
    return str(row.get("period_end") or row.get("period_start") or row.get("source_period") or "")


def _point_3826(row: Mapping[str, Any]) -> Point | None:
    x = _finite_number(row.get("x_3826"))
    y = _finite_number(row.get("y_3826"))
    if x is not None and y is not None:
        return Point(x, y)
    longitude = _finite_number(row.get("longitude"))
    latitude = _finite_number(row.get("latitude"))
    if longitude is None or latitude is None or not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        return None
    x, y = _WGS84_TO_TWD97.transform(longitude, latitude)
    return Point(x, y)


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _finite_non_negative(value: Any) -> bool:
    number = _finite_number(value)
    return number is not None and number >= 0


__all__ = ["calculate_population_service_coverage", "calculate_service_coverage"]
