"""Youth participation analytics and published-analysis orchestration.

This module owns the cross-dataset calculations used by the youth-participation
page.  Curated rows are the only inputs; source documents and ``raw_record``
fields never cross the public analytics boundary.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .annual_metrics import calculate_budget_series
from .data_gaps import explain_reason_codes
from .config import (
    HomepageAnalyticsConfig,
    load_keyword_config,
    load_topic_rules,
    load_topic_weights,
    normalize_topic_text,
)
from .elections import _candidate_age, _roc_year, calculate_youth_candidacy
from .homepage import _source_periods
from .input_resolver import HomepageInputResolver
from .io import CuratedSlice, atomic_json_write
from .service_coverage import calculate_service_coverage
from .youth_keyword_frequency import calculate_youth_keyword_frequency
from .youth_topic_weight import calculate_youth_topic_weights


def calculate_youth_borough_metrics(
    records: Iterable[Mapping[str, Any]],
    population_records: Iterable[Mapping[str, Any]],
    *,
    election_years_roc: Iterable[int],
    districts: Iterable[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Calculate V1 candidate, elected-seat and youth representation metrics.

    V1 is the village/borough-chief election and maps naturally to one of the
    29 administrative districts.  When age-specific voter data is unavailable,
    the 18--35 population share is deliberately exposed as a denominator
    proxy; it is never presented as an election-register share.
    """

    years = sorted({int(year) for year in election_years_roc})
    population = _population_reference(population_records, years)
    groups: dict[tuple[int, str], dict[str, Any]] = defaultdict(_empty_borough_group)
    quality = {
        "input_rows": 0,
        "excluded_year_rows": 0,
        "excluded_non_v1_rows": 0,
        "unknown_age_rows": 0,
        "unknown_district_rows": 0,
    }

    for raw in records:
        quality["input_rows"] += 1
        year = _row_year(raw)
        if year not in years:
            quality["excluded_year_rows"] += 1
            continue
        if not (raw.get("election_type") == "borough_chief" or raw.get("source_code") == "V1"):
            quality["excluded_non_v1_rows"] += 1
            continue
        district_id = raw.get("district_id")
        if district_id is None:
            quality["unknown_district_rows"] += 1
            continue
        key = (year, str(district_id))
        group = groups[key]
        group.update(
            {
                "election_year_roc": year,
                "district_id": str(district_id),
                "district_name": raw.get("district_name"),
            }
        )
        group["candidate_count"] += 1
        elected = bool(raw.get("elected")) or raw.get("elected_mark") == "*"
        if elected:
            group["elected_seat_count"] += 1
        age = _candidate_age(raw)
        if age is None:
            quality["unknown_age_rows"] += 1
            continue
        group["age_known_candidate_count"] += 1
        if 18 <= age <= 35:
            group["youth_candidate_count"] += 1
            if elected:
                group["youth_elected_count"] += 1

    expected_districts = {
        str(row.get("district_id")): row.get("district_name")
        for row in (districts or [])
        if row.get("district_id") is not None
    }
    expected_districts.update(
        {
            district_id: item.get("district_name")
            for year_data in population.values()
            for district_id, item in year_data.get("districts", {}).items()
            if district_id not in expected_districts
        }
    )

    output_years: list[dict[str, Any]] = []
    for year in years:
        district_ids = set(expected_districts)
        district_ids.update(
            district_id for row_year, district_id in groups if row_year == year
        )
        rows: list[dict[str, Any]] = []
        for district_id in sorted(district_ids):
            group = groups.get((year, district_id), _empty_borough_group())
            district_name = group.get("district_name") or expected_districts.get(district_id)
            denominator = population.get(year, {}).get("districts", {}).get(district_id, {})
            rows.append(
                _finalize_borough_group(
                    group,
                    district_name=district_name,
                    population=denominator,
                )
            )
        output_years.append(
            {
                "year_roc": year,
                "districts": rows,
                "source_period": str(year),
                "status": _collection_status(rows),
            }
        )

    return {
        "metric_id": "youthParticipationIndex",
        "election_type": "V1",
        "election_years_roc": years,
        "years": output_years,
        "_quality": quality,
    }


def calculate_proposal_funnel(
    records: Iterable[Mapping[str, Any]], *, recent_year_count: int = 3
) -> dict[str, Any]:
    """Build the observable part of the youth proposal funnel.

    Meeting minutes do not prove internal case tracking, so stages four and
    five remain ``null`` until a tracker dataset is supplied.  Duplicate
    parser rows are merged by meeting, item number and normalized topic.
    """

    rows = [dict(row) for row in records]
    available_years = sorted({year for row in rows if (year := _row_year(row)) is not None})
    selected_years = available_years[-max(1, int(recent_year_count)) :]
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for index, row in enumerate(rows):
        year = _row_year(row)
        if year not in selected_years:
            continue
        meeting_id = str(row.get("meeting_id") or f"row-{index}")
        item_no = str(row.get("item_no") or "")
        topic = normalize_topic_text(row.get("topic_text") or row.get("source_text"))
        key = (meeting_id, item_no, topic)
        existing = deduped.get(key)
        if existing is None:
            existing = {
                "discussed": False,
                "resolved": False,
                "escalated": False,
                "manual_review_required": False,
                "parse_status": "complete",
            }
            deduped[key] = existing
        for field in ("discussed", "resolved", "escalated", "manual_review_required"):
            existing[field] = bool(existing[field] or row.get(field) is True)
        if row.get("parse_status") == "partial" or row.get("manual_review_required") is True:
            existing["parse_status"] = "partial"

    total = len(deduped)
    discussed = sum(item["discussed"] for item in deduped.values())
    resolved = sum(item["resolved"] for item in deduped.values())
    escalated = sum(item["escalated"] for item in deduped.values())
    manual_review = sum(item["manual_review_required"] for item in deduped.values())
    if not rows:
        status = "unavailable"
    else:
        # The meeting records support stages 1--3 only; the missing tracker
        # intentionally keeps this metric partial even when parsing is clean.
        status = "partial"
    return {
        "metric_id": "youthProposalFunnel",
        "source_datasets": ["youth_council_minutes"],
        "coverage_scope": "meeting_records",
        "source_period": [str(year) for year in selected_years],
        "stages": [
            {"stage": 1, "name": "identified", "count": total},
            {"stage": 2, "name": "discussed", "count": discussed},
            {"stage": 3, "name": "resolved", "count": resolved},
            {"stage": 4, "name": "tracked", "count": None},
            {"stage": 5, "name": "implemented", "count": None},
        ],
        "coverage": {
            "available_year_count": len(selected_years),
            "deduplicated_item_count": total,
            "manual_review_required_count": manual_review,
        },
        "escalated_to_council": escalated,
        "deduplicated_item_count": total,
        "manual_review_required_count": manual_review,
        "status": status,
        "proxy_usage": [],
        "blocking_reasons": ["youth_proposal_tracker_unavailable"],
    }


def calculate_grant_metrics(
    records: Iterable[Mapping[str, Any]], *, annual_years_roc: Iterable[int]
) -> dict[str, Any]:
    """Aggregate Youth Bureau grant rows by ROC year and resolved district."""

    years = [int(year) for year in annual_years_roc]
    trend_amounts: dict[int, float] = defaultdict(float)
    district_amounts: dict[tuple[int, str], dict[str, Any]] = defaultdict(
        lambda: {"amount_twd_thousand": 0.0, "grant_row_count": 0, "district_name": None}
    )
    unresolved = 0
    input_rows = 0
    source_years: set[int] = set()
    annual_rows = 0
    year_scopes: dict[int, str] = {}
    for raw in records:
        input_rows += 1
        year = _row_year(raw)
        amount = _number(raw.get("amount_twd_thousand", raw.get("value")))
        if year is not None:
            source_years.add(year)
        if year not in years or amount is None:
            continue
        annual_rows += 1
        year_scopes.setdefault(year, str(raw.get("coverage_scope") or "unknown"))
        trend_amounts[year] += amount
        district_id = raw.get("district_id")
        if district_id is None:
            unresolved += 1
            continue
        key = (year, str(district_id))
        item = district_amounts[key]
        item["amount_twd_thousand"] += amount
        item["grant_row_count"] += 1
        item["district_name"] = raw.get("district_name") or item.get("district_name")

    by_district: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (year, district_id), item in sorted(district_amounts.items()):
        by_district[str(year)].append(
            {
                "district_id": district_id,
                "district_name": item.get("district_name"),
                "amount_twd_thousand": _round(item["amount_twd_thousand"]),
                "grant_row_count": item["grant_row_count"],
            }
        )
    comparable_scope = _comparable_grant_scope(year_scopes)
    all_years = [
        {
            "year_roc": year,
            "amount_twd_thousand": _round(trend_amounts[year]) if year in trend_amounts else None,
            "coverage_scope": year_scopes.get(year),
            "status": "observed" if year in trend_amounts else "unavailable",
        }
        for year in years
    ]
    # Each source PDF accumulates to a different month, so only one reporting
    # scope may be plotted as a series; the rest stay visible in coverage.
    trend = [
        row
        for row in all_years
        if row["coverage_scope"] == comparable_scope or row["status"] == "unavailable"
    ]
    excluded_years = [
        row for row in all_years if row not in trend
    ]
    blocking_reasons = ["grant_district_unresolved"] if unresolved else []
    if excluded_years:
        blocking_reasons.append("grant_coverage_scope_mixed")
    if not input_rows:
        status = "unavailable"
    elif unresolved or excluded_years:
        status = "partial"
    else:
        status = "observed"
    return {
        "metric_id": "youthGrantDistribution",
        "source_datasets": ["youth_grants"],
        "source_period": [str(year) for year in sorted(source_years)],
        "trend": trend,
        "trend_coverage_scope": comparable_scope,
        "by_district": dict(by_district),
        "unresolved_district_row_count": unresolved,
        "input_row_count": input_rows,
        "coverage": {
            "annual_year_count": len(years),
            "annual_row_count": annual_rows,
            "district_resolved_row_count": annual_rows - unresolved,
            "coverage_scope_by_year": {
                str(year): scope for year, scope in sorted(year_scopes.items())
            },
            "excluded_years": excluded_years,
        },
        "status": status,
        "proxy_usage": [],
        "blocking_reasons": blocking_reasons,
    }


def _comparable_grant_scope(year_scopes: Mapping[int, str]) -> str | None:
    """Pick the reporting scope that forms the longest comparable series.

    Ties are broken towards the scope covering the most recent year so the
    trend keeps tracking how the bureau currently publishes.
    """

    if not year_scopes:
        return None
    counts: dict[str, int] = defaultdict(int)
    latest: dict[str, int] = {}
    for year, scope in year_scopes.items():
        counts[scope] += 1
        latest[scope] = max(latest.get(scope, year), year)
    return max(counts, key=lambda scope: (counts[scope], latest[scope]))


def generate_youth_participation_data(
    *,
    resolver: HomepageInputResolver,
    config: HomepageAnalyticsConfig,
    config_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Generate all youth-participation metrics from curated inputs."""

    quality: dict[str, Any] = {
        "metric_id": "youth_participation",
        "calculation_version": "1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {},
        "warnings": [],
        "blocking_reasons": [],
        "proxy_usage": [],
    }
    loaded: dict[str, CuratedSlice] = {}

    def load_periods(dataset: str, periods: list[str]) -> list[dict[str, Any]]:
        try:
            item = resolver.available_periods(dataset, periods)
        except (AttributeError, ValueError) as exc:
            _record_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, dataset, item)
        loaded[f"{dataset}:{','.join(item.source_periods)}"] = item
        return [dict(row) for row in item.records]

    def load_latest(dataset: str) -> list[dict[str, Any]]:
        try:
            item = resolver.latest(dataset)
        except (AttributeError, ValueError) as exc:
            _record_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, dataset, item)
        loaded[dataset] = item
        return [dict(row) for row in item.records]

    def load_all(dataset: str) -> list[dict[str, Any]]:
        try:
            item = resolver.all_available(dataset)
        except (AttributeError, ValueError) as exc:
            _record_failure(quality, dataset, str(exc))
            return []
        _record_input(quality, dataset, item)
        loaded[dataset] = item
        return [dict(row) for row in item.records]

    annual_years = list(config.annual_years_roc)
    requested_population_years = sorted(set(annual_years) | set(config.election_years_roc))
    population_records = load_periods(
        "population",
        [f"{year:03d}{month:02d}" for year in requested_population_years for month in range(1, 13)],
    )
    election_records = load_all("elections")
    minute_records = load_all("youth_council_minutes")
    join_records = load_all("join_proposals")
    grant_records = load_all("youth_grants")
    budget_records = load_all("youth_budgets")
    service_points = load_latest("youth_service_points")
    boundaries = load_latest("village_boundaries")
    village_population = load_periods(
        "population_villages",
        [f"{config.population_reference_year_roc:03d}{month:02d}" for month in range(1, 13)],
    )

    candidacy = calculate_youth_candidacy(
        election_records,
        population_records,
        election_years_roc=config.election_years_roc,
    )
    borough = calculate_youth_borough_metrics(
        election_records,
        population_records,
        election_years_roc=config.election_years_roc,
        districts=resolver.districts,
    )
    for row in _borough_rows(borough):
        if row.get("proxy"):
            quality["proxy_usage"].append(
                {
                    "metric": "yrr",
                    "district_id": row.get("district_id"),
                    "year_roc": row.get("election_year_roc"),
                    "reason": "age_specific_election_register_unavailable_population_share_used",
                }
            )
    service = calculate_service_coverage(
        service_points,
        boundaries,
        village_population,
        radius_m=config.service_radius_m,
    )
    funnel = calculate_proposal_funnel(minute_records)
    grants = calculate_grant_metrics(grant_records, annual_years_roc=annual_years)
    budget = calculate_budget_series(
        budget_records,
        budget_records,
        annual_years_roc=annual_years,
    )

    source_periods = _source_periods(loaded)
    t1_rows = list(candidacy.get("city_councilor_t1", []))
    v1_years = list(borough.get("years", []))
    v1_rows = _borough_rows(borough)
    election_blocking_reasons = []
    if any(row.get("quality_status") == "unavailable" for row in t1_rows) or any(
        row.get("status") == "unavailable" for row in v1_rows
    ):
        election_blocking_reasons.append("historical_population_denominator_unavailable")
    election_proxy_usage = [
        {
            "metric": "yrr",
            "reason": "age_specific_election_register_unavailable_population_share_used",
        }
    ]
    t1_public = _public(candidacy)
    t1_public.update(
        {
            "status": _status_for_rows(t1_rows, status_key="quality_status"),
            "source_period": [str(year) for year in config.election_years_roc],
            "coverage": {
                "election_district_row_count": len(t1_rows),
                "citywide_row_count": len(candidacy.get("city_councilor_t1_citywide", [])),
            },
            "proxy_usage": [],
            "blocking_reasons": list(election_blocking_reasons),
        }
    )
    v1_public = _public(borough)
    v1_public.update(
        {
            "status": _status_for_years(v1_years),
            "source_period": [str(year) for year in config.election_years_roc],
            "coverage": {
                "year_count": len(v1_years),
                "district_count_by_year": {
                    str(item.get("year_roc")): len(item.get("districts", []))
                    for item in v1_years
                },
                "latest_district_count": len(_borough_rows(borough, latest=True)),
            },
            "proxy_usage": election_proxy_usage,
            "blocking_reasons": list(election_blocking_reasons),
        }
    )
    elections_public = {
        "youth_candidacy": t1_public,
        "v1_borough_chief": v1_public,
        "status": _merge_statuses(t1_public["status"], v1_public["status"]),
        "source_period": [str(year) for year in config.election_years_roc],
        "coverage": {
            "v1_year_count": len(v1_years),
            "v1_latest_district_count": len(_borough_rows(borough, latest=True)),
            "t1_election_district_row_count": len(t1_rows),
        },
        "proxy_usage": election_proxy_usage,
        "blocking_reasons": list(election_blocking_reasons),
    }

    service_public = _public(service)
    service_public.update(
        {
            "source_period": {
                dataset: source_periods.get(dataset, [])
                for dataset in ("youth_service_points", "village_boundaries", "population_villages")
            },
            "coverage": {
                "boundary_village_count": service.get("boundary_village_count", 0),
                "joined_village_count": service.get("joined_village_count", 0),
                "population_coverage_ratio": service.get("population_coverage_ratio"),
            },
            "proxy_usage": [
                {"reason": "village_area_uniformity_assumption"},
            ],
        }
    )
    budget_public = _public(budget)
    budget_execution_rows = list(budget.get("execution", []))
    budget_blocking_reasons = (
        ["final_settlement_unavailable"]
        if any(row.get("execution_rate") is None for row in budget_execution_rows)
        else []
    )
    budget_public.update(
        {
            "status": _budget_status(budget),
            "source_period": [str(year) for year in annual_years],
            "coverage": {
                "annual_year_count": len(budget.get("trend", [])),
                "execution_observed_year_count": sum(
                    row.get("execution_rate") is not None for row in budget_execution_rows
                ),
            },
            "proxy_usage": [],
            "blocking_reasons": budget_blocking_reasons,
        }
    )
    rules_path = Path(config_dir) if config_dir is not None else Path(__file__).resolve().parents[2] / "config"
    rules = load_topic_rules(rules_path / "youth_topic_rules.json")
    weights = load_topic_weights(rules_path / "youth_topic_weights.json")
    keyword_config = load_keyword_config(rules_path / "youth_keyword_config.json")
    filtered_minutes = [row for row in minute_records if _row_year(row) in annual_years]
    filtered_join = [row for row in join_records if _row_year(row) in annual_years]
    topic_result = calculate_youth_topic_weights(
        filtered_join, filtered_minutes, rules=rules, weights=weights
    )
    keyword_result = calculate_youth_keyword_frequency(
        filtered_join, filtered_minutes, config=keyword_config, weights=weights
    )
    topics = {
        "topic_weight": _public(topic_result),
        "keyword_frequency": _public(keyword_result),
        "standalone_artifacts": {
            "topic_weight": "analytics/youth_topic_weight/all.json",
            "keyword_frequency": "analytics/youth_keyword_frequency/all.json",
        },
        "status": "observed" if filtered_join or filtered_minutes else "unavailable",
        "proxy_usage": [
            {
                "reason": "youth_topic_proxy_rules",
                "source_datasets": ["join_proposals", "youth_council_minutes"],
            }
        ],
    }
    topics["source_period"] = [str(year) for year in annual_years]
    topics["coverage"] = {
        "join_record_count": len(filtered_join),
        "minutes_record_count": len(filtered_minutes),
    }
    topics["blocking_reasons"] = []
    quality["proxy_usage"].extend(topics["proxy_usage"])
    quality["blocking_reasons"].extend(election_blocking_reasons)
    quality["blocking_reasons"].extend(service.get("blocking_reasons", []))
    quality["blocking_reasons"].extend(funnel.get("blocking_reasons", []))
    if grants.get("status") == "partial":
        quality["blocking_reasons"].extend(grants.get("blocking_reasons", []))
    if any(row.get("execution_rate") is None for row in budget.get("execution", [])):
        quality["warnings"].append("budget_execution_rate_missing_without_final_settlement")
    quality["blocking_reasons"] = sorted(set(quality["blocking_reasons"]))
    quality["source_limitations"] = explain_reason_codes(
        quality["blocking_reasons"], config_dir=rules_path
    )
    quality["source_periods"] = source_periods
    quality["coverage"] = {
        "expected_district_count": len(resolver.districts),
        "v1_year_count": len(borough.get("years", [])),
        "v1_latest_district_count": len(_borough_rows(borough, latest=True)),
        "t1_election_district_row_count": len(candidacy.get("city_councilor_t1", [])),
        "service_verified_point_count": service.get("verified_point_count", 0),
        "service_excluded_point_count": service.get("excluded_point_count", 0),
    }
    quality["metric_status"] = {
        "elections_v1": _status_for_years(borough.get("years", [])),
        "elections_t1": _status_for_rows(t1_rows, status_key="quality_status"),
        "service_coverage": service.get("status", "unavailable"),
        "proposal_funnel": funnel.get("status", "unavailable"),
        "grants": grants.get("status", "unavailable"),
        "budget_execution": _budget_status(budget),
        "topics": topics.get("status", "unavailable"),
    }

    latest_borough = _borough_rows(borough, latest=True)
    result = {
        "metric_id": "youth_participation",
        "calculation_version": "1",
        "generated_at": quality["generated_at"],
        "time_policy": {
            "annual_years_roc": annual_years,
            "election_years_roc": list(config.election_years_roc),
            "v1_primary": True,
            "t1_grain": "election_district",
            "proposal_funnel_years": funnel.get("source_period", []),
        },
        "overview": {
            "latest_v1_year_roc": max(config.election_years_roc, default=None),
            "latest_v1_district_count": len(latest_borough),
            "latest_v1_youth_elected_count": sum(row.get("youth_elected_count", 0) for row in latest_borough),
            "latest_v1_elected_seat_count": sum(row.get("elected_seat_count", 0) for row in latest_borough),
            "service_coverage_rate": service.get("value"),
        },
        "elections": {
            **elections_public,
        },
        "service_coverage": service_public,
        "proposal_funnel": funnel,
        "grants": grants,
        "budget": budget_public,
        "topics": topics,
        "_quality": quality,
    }
    return _public(result, keep_quality=True)


def write_youth_participation_data(
    result: Mapping[str, Any], *, output_dir: str | Path
) -> tuple[Path, Path]:
    """Write the public participation artifact and its private quality report."""

    root = Path(output_dir)
    quality = dict(result.get("_quality") or {})
    output = {key: value for key, value in result.items() if key != "_quality"}
    output_path = atomic_json_write(
        root / "analytics" / "youth_participation" / "all.json", _public(output)
    )
    quality_path = atomic_json_write(
        root / "quality" / "analytics_youth_participation.json", _public(quality)
    )
    return output_path, quality_path


def _empty_borough_group() -> dict[str, Any]:
    return {
        "election_year_roc": None,
        "district_id": None,
        "district_name": None,
        "candidate_count": 0,
        "age_known_candidate_count": 0,
        "youth_candidate_count": 0,
        "elected_seat_count": 0,
        "youth_elected_count": 0,
    }


def _finalize_borough_group(
    group: Mapping[str, Any], *, district_name: str | None, population: Mapping[str, Any]
) -> dict[str, Any]:
    youth_population = _number(population.get("youth_18_35_total"))
    people_total = _number(population.get("people_total"))
    youth_elected = int(group.get("youth_elected_count", 0))
    elected_seats = int(group.get("elected_seat_count", 0))
    youth_candidates = int(group.get("youth_candidate_count", 0))
    ratio = None if elected_seats <= 0 else youth_elected / elected_seats * 100
    candidacy_rate = None if youth_population in (None, 0) else youth_candidates / youth_population * 100000
    population_share = None if people_total in (None, 0) or youth_population is None else youth_population / people_total * 100
    yrr = None
    if population_share not in (None, 0) and ratio is not None:
        yrr = (ratio / 100) / (population_share / 100)
    # Candidate and seat counts come from the election records alone, so they
    # stay observable in years whose population was never published.  Only the
    # population-derived rates degrade.
    has_counts = int(group.get("candidate_count", 0)) > 0 or elected_seats > 0
    counts_status = "observed" if has_counts else "unavailable"
    status = "observed" if youth_population is not None and people_total is not None else "unavailable"
    denominator_reason = None if status == "observed" else "population_denominator_unpublished"
    return {
        "election_year_roc": group.get("election_year_roc"),
        "district_id": group.get("district_id"),
        "district_name": district_name,
        "counts_status": counts_status,
        "denominator_unavailable_reason": denominator_reason,
        "candidate_count": group.get("candidate_count", 0),
        "age_known_candidate_count": group.get("age_known_candidate_count", 0),
        "youth_candidate_count": youth_candidates,
        "elected_seat_count": elected_seats,
        "youth_elected_count": youth_elected,
        "youth_borough_chief_ratio": _round(ratio),
        "youth_candidacy_rate": _round(candidacy_rate),
        "youth_population_18_35": youth_population,
        "population_total": people_total,
        "youth_population_share": _round(population_share),
        "yrr": _round(yrr),
        "denominator_type": "population_proxy",
        "proxy": True,
        "source_period": str(group.get("election_year_roc")),
        "status": status,
    }


def _population_reference(
    records: Iterable[Mapping[str, Any]], years: Iterable[int]
) -> dict[int, dict[str, Any]]:
    wanted = set(years)
    latest: dict[tuple[int, str, str], tuple[str, dict[str, Any]]] = {}
    for raw in records:
        year = _row_year(raw)
        if year not in wanted:
            continue
        district_id = raw.get("district_id")
        metric = raw.get("metric_id")
        if district_id is None or metric not in {"people_total", "youth_18_35_total"}:
            continue
        value = _number(raw.get("value"))
        if value is None:
            continue
        period = str(raw.get("period_end") or raw.get("period_start") or "")
        key = (year, str(district_id), str(metric))
        if key not in latest or period >= latest[key][0]:
            latest[key] = (period, dict(raw))
    output: dict[int, dict[str, Any]] = {}
    for (year, district_id, metric), (_, raw) in latest.items():
        item = output.setdefault(year, {"districts": {}})["districts"].setdefault(
            district_id,
            {"district_name": raw.get("district_name")},
        )
        item[metric] = _number(raw.get("value"))
    return output


def _borough_rows(result: Mapping[str, Any], *, latest: bool = False) -> list[dict[str, Any]]:
    years = result.get("years", [])
    if not isinstance(years, list) or not years:
        return []
    selected = years[-1] if latest else None
    rows: list[dict[str, Any]] = []
    for year in years:
        if selected is not None and year != selected:
            continue
        values = year.get("districts", []) if isinstance(year, Mapping) else []
        rows.extend(row for row in values if isinstance(row, Mapping))
    return rows


def _collection_status(rows: list[Mapping[str, Any]]) -> str:
    if not rows:
        return "unavailable"
    # A year the elections source never covered has nothing to show; a year with
    # counts but no published population is partial, not empty.
    if all(row.get("counts_status", "unavailable") == "unavailable" for row in rows):
        return "unavailable"
    if any(row.get("status") != "observed" for row in rows):
        return "partial"
    return "observed"


def _status_for_years(years: Iterable[Mapping[str, Any]]) -> str:
    values = list(years)
    if not values:
        return "unavailable"
    if any(value.get("status") != "observed" for value in values):
        return "partial"
    return "observed"


def _status_for_rows(rows: Iterable[Mapping[str, Any]], *, status_key: str) -> str:
    values = list(rows)
    if not values:
        return "unavailable"
    statuses = [value.get(status_key) for value in values]
    if all(status == "unavailable" for status in statuses):
        return "unavailable"
    if any(status != "observed" for status in statuses):
        return "partial"
    return "observed"


def _merge_statuses(*statuses: str) -> str:
    values = [status for status in statuses if status]
    if not values or all(status == "unavailable" for status in values):
        return "unavailable"
    if any(status != "observed" for status in values):
        return "partial"
    return "observed"


def _budget_status(budget: Mapping[str, Any]) -> str:
    rows = budget.get("execution", [])
    if not rows or not any(row.get("execution_rate") is not None for row in rows):
        return "unavailable"
    return "partial" if any(row.get("execution_rate") is None for row in rows) else "observed"


def _record_input(quality: dict[str, Any], dataset: str, item: CuratedSlice) -> None:
    current = quality["inputs"].setdefault(dataset, {"source_periods": [], "paths": [], "row_count": 0})
    current["source_periods"] = sorted(set(current["source_periods"]) | set(item.source_periods))
    current["paths"] = sorted(set(current["paths"]) | set(item.paths))
    current["row_count"] += len(item.records)


def _record_failure(quality: dict[str, Any], dataset: str, reason: str) -> None:
    current = quality["inputs"].setdefault(dataset, {"source_periods": [], "paths": [], "row_count": 0})
    current.setdefault("failures", []).append(reason)
    quality["warnings"].append(f"{dataset}: {reason}")


def _row_year(row: Mapping[str, Any]) -> int | None:
    value = (
        row.get("year_roc")
        or row.get("election_roc_year")
        or row.get("budget_year_roc")
        or row.get("grant_year_roc")
    )
    if value is not None:
        try:
            number = int(str(value).rstrip("年"))
            return number - 1911 if number > 1911 else number
        except (TypeError, ValueError):
            pass
    return _roc_year(row)


def _number(value: Any) -> float | None:
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 6)


def _public(value: Any, *, keep_quality: bool = False) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _public(item, keep_quality=keep_quality)
            for key, item in value.items()
            if (keep_quality or key != "_quality") and key not in {"raw_record", "raw_records"}
        }
    if isinstance(value, list):
        return [_public(item, keep_quality=keep_quality) for item in value]
    if isinstance(value, tuple):
        return [_public(item, keep_quality=keep_quality) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


__all__ = [
    "calculate_grant_metrics",
    "calculate_proposal_funnel",
    "calculate_youth_borough_metrics",
    "generate_youth_participation_data",
    "write_youth_participation_data",
]
