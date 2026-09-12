"""Election-event youth candidacy analytics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from collections.abc import Iterable, Mapping
from typing import Any


def calculate_youth_candidacy(
    records: Iterable[Mapping[str, Any]],
    population_records: Iterable[Mapping[str, Any]],
    *,
    election_years_roc: Iterable[int],
) -> dict[str, Any]:
    """Calculate T1 election-district and V1 administrative-district rates."""

    years = {int(year) for year in election_years_roc}
    population = _population_denominators(population_records, years)
    t1_groups: dict[tuple[int, str], dict[str, Any]] = defaultdict(_empty_group)
    v1_groups: dict[tuple[int, str], dict[str, Any]] = defaultdict(_empty_group)
    quality = {"input_rows": 0, "excluded_year_rows": 0, "unknown_age_rows": 0}
    for raw in records:
        quality["input_rows"] += 1
        year = _roc_year(raw)
        if year not in years:
            quality["excluded_year_rows"] += 1
            continue
        election_type = raw.get("election_type")
        if election_type == "city_councilor" or raw.get("source_code") == "T1":
            key = (year, str(raw.get("election_district_code") or "unknown"))
            group = t1_groups[key]
            group.update(
                {
                    "election_district_code": str(raw.get("election_district_code") or "unknown"),
                    "election_district_name": raw.get("election_district_name"),
                    "district_id": None,
                    "district_name": None,
                }
            )
        elif election_type == "borough_chief" or raw.get("source_code") == "V1":
            district_id = raw.get("district_id")
            if district_id is None:
                quality["unknown_age_rows"] += 1
                continue
            key = (year, str(district_id))
            group = v1_groups[key]
            group.update(
                {
                    "district_id": str(district_id),
                    "district_name": raw.get("district_name"),
                }
            )
        else:
            continue
        group["election_year_roc"] = year
        group["candidate_count"] += 1
        age = _candidate_age(raw)
        if age is None:
            quality["unknown_age_rows"] += 1
            continue
        group["age_known_candidate_count"] += 1
        if 18 <= age <= 35:
            group["youth_candidate_count"] += 1
            if bool(raw.get("elected")) or raw.get("elected_mark") == "*":
                group["youth_elected_count"] += 1
        if bool(raw.get("elected")) or raw.get("elected_mark") == "*":
            group["elected_count"] += 1

    t1_rows = [
        _finalize_group(
            group,
            denominator=population.get(year, {}).get("city"),
            denominator_scope="citywide",
        )
        for (year, _), group in sorted(t1_groups.items())
    ]
    v1_rows = []
    for _, group in sorted(v1_groups.items()):
        denominator = population.get(group["election_year_roc"], {}).get("districts", {}).get(group["district_id"])
        v1_rows.append(_finalize_group(group, denominator=denominator, denominator_scope="district"))
    city_rows = []
    for year in sorted(years):
        groups = [group for (row_year, _), group in t1_groups.items() if row_year == year]
        merged = _empty_group()
        merged.update({"election_year_roc": year, "district_id": None, "district_name": None})
        for group in groups:
            for key in ("candidate_count", "age_known_candidate_count", "youth_candidate_count", "elected_count", "youth_elected_count"):
                merged[key] += group[key]
        if merged["candidate_count"]:
            city_rows.append(_finalize_group(merged, denominator=population.get(year, {}).get("city"), denominator_scope="citywide"))
    return {
        "metric_id": "youthCandidacyRate",
        "election_years_roc": sorted(years),
        "city_councilor_t1": t1_rows,
        "borough_chief_v1": v1_rows,
        "city_councilor_t1_citywide": city_rows,
        "_quality": quality,
    }


def _empty_group() -> dict[str, Any]:
    return {
        "election_year_roc": None,
        "election_district_name": None,
        "district_id": None,
        "district_name": None,
        "candidate_count": 0,
        "age_known_candidate_count": 0,
        "youth_candidate_count": 0,
        "elected_count": 0,
        "youth_elected_count": 0,
    }


def _finalize_group(group: Mapping[str, Any], *, denominator: float | int | None, denominator_scope: str) -> dict[str, Any]:
    output = dict(group)
    output["youth_population_18_35"] = denominator
    output["denominator_scope"] = denominator_scope
    output["youth_candidacy_rate"] = (
        None if denominator in (None, 0) else group["youth_candidate_count"] / float(denominator) * 100000
    )
    output["source_period"] = str(group["election_year_roc"])
    output["period_type"] = "election_event"
    output["quality_status"] = "observed" if denominator is not None else "unavailable"
    output["source_datasets"] = ["elections", "population"]
    return output


def _population_denominators(records: Iterable[Mapping[str, Any]], years: set[int]) -> dict[int, dict[str, Any]]:
    latest: dict[tuple[int, str], tuple[str, float]] = {}
    for raw in records:
        if raw.get("metric_id") != "youth_18_35_total":
            continue
        year = _roc_year(raw)
        district_id = raw.get("district_id")
        value = _number(raw.get("value"))
        if year not in years or district_id is None or value is None:
            continue
        period = str(raw.get("period_end") or raw.get("period_start") or "")
        key = (year, str(district_id))
        if key not in latest or period >= latest[key][0]:
            latest[key] = (period, value)
    output: dict[int, dict[str, Any]] = {}
    for (year, district_id), (_, value) in latest.items():
        item = output.setdefault(year, {"districts": {}, "city": 0.0})
        item["districts"][district_id] = value
        item["city"] += value
    return output


def _roc_year(row: Mapping[str, Any]) -> int | None:
    value = row.get("election_roc_year") or row.get("year_roc")
    if value is not None:
        try:
            number = int(str(value).rstrip("年"))
            return number if number < 1911 else number - 1911
        except (TypeError, ValueError):
            pass
    period = str(row.get("election_date") or row.get("period_start") or "")
    try:
        return date.fromisoformat(period[:10]).year - 1911
    except ValueError:
        return None


def _candidate_age(row: Mapping[str, Any]) -> int | None:
    election = _parse_date(row.get("election_date"))
    birth = _parse_date(row.get("birth_date"))
    if election and birth:
        age = election.year - birth.year - ((election.month, election.day) < (birth.month, birth.day))
        return age
    birth_year = row.get("birth_year_roc")
    try:
        if birth_year is not None and election:
            return election.year - (int(str(birth_year)) + 1911)
    except (TypeError, ValueError):
        pass
    try:
        value = row.get("source_age_numeric") or row.get("source_age")
        return int(str(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


__all__ = ["calculate_youth_candidacy"]
