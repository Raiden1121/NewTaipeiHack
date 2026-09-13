"""Project a published analytics snapshot into DynamoDB items.

The item catalog, the exclusions, and the write ordering are defined by
`infrastructure/dynamodb_schema.md`; this module is the writer side of that
contract, and `modules/api/lambda/handler.py` is the reader side.

api_contract.md §0.2 puts metric calculation in data-pipeline and forbids
request-time computation, but explicitly allows this projection stage to pin a
year and map fields into the API's shape. That is all that happens here: the
111-term borough-chief scalars are *mapped* from the participation analysis
(`youth_borough_chief_ratio`, `yrr`), not recomputed. The one aggregate this
module does compute is the citywide borough-chief row, and §6.2 spells out that
formula precisely, including that the 29 district `yrr` values must not be
averaged.

Pure functions over already-loaded snapshot payloads: no AWS, no file IO, so
it can be exercised against any local `data/analytics/published/<id>/`.
"""

from __future__ import annotations

import gzip
import json
from decimal import Decimal
from typing import Any, Mapping, Sequence

__all__ = ["build_items", "to_dynamodb_types", "MANIFEST_KEY", "AI_CONTEXT_PK"]

MANIFEST_KEY = ("META", "MANIFEST")

# AI context items, read by ai-service's DynamoEvidenceRepository. The dashboard
# items below are trimmed to api_contract.md's shapes; ai-service needs the full
# published artifacts so its evidence -- and the precompute fingerprints built
# from it -- match what it gets from the local snapshot files.
AI_CONTEXT_PK = "AI_CONTEXT"
AI_CONTEXT_ENCODING = "gzip+json"
# Mirrors ai-service's SKIPPED_ARTIFACT_KEYS (src/context/analyticsSnapshot.ts).
_AI_CONTEXT_SKIPPED_ARTIFACTS = ("district_details",)
# DynamoDB rejects items over 400KB; leave room for the key and other attributes.
_AI_CONTEXT_MAX_PAYLOAD_BYTES = 350_000

# api_contract.md §8.1: fixed semantics, not data -- wages rising is good, and
# youth population falling is the risk being tracked, so both want "up".
DESIRED_DIRECTION = {"wageGrowth": "up", "populationChange": "up"}

# api_contract.md §6.2: only the 111 term has a trustworthy candidate-age
# denominator, so every borough-chief scalar is pinned to it.
BOROUGH_CHIEF_YEAR_ROC = 111

# dynamodb_schema.md "明確排除" -- village/precinct detail no endpoint serves.
_SERVICE_COVERAGE_DROP = ("villages", "districts")
_ELECTIONS_DROP = ("city_councilor_t1",)

# employment.json keys -> the plot ids api_contract.md §5.3 defines.
_SCATTER_PLOT_IDS = {
    "knowledge_job_vs_estimated_wage": "knowledge-wage",
    "monthly_wage_vs_house_price": "wage-housing",
}

# The canonical §6.4 keyword-frequency fields. `generated_at` and `metric_id`
# are dropped: the snapshot's own manifest already carries provenance.
_KEYWORD_FREQUENCY_FIELDS = (
    "analysis_id",
    "calculation_version",
    "config_version",
    "source_datasets",
    "period_scope",
    "source_periods",
    "normalization",
    "weight_normalization",
    "candidate_mode",
    "keywords",
)


def _borough_chief_districts(participation: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The 111-term rows, which are the authoritative source for every
    borough-chief scalar (api_contract.md §6.2)."""

    years = (
        ((participation.get("elections") or {}).get("v1_borough_chief") or {}).get("years")
    ) or []
    for year in years:
        if isinstance(year, Mapping) and year.get("year_roc") == BOROUGH_CHIEF_YEAR_ROC:
            return [row for row in (year.get("districts") or []) if isinstance(row, Mapping)]
    return []


def _divide(numerator: Any, denominator: Any) -> float | None:
    """None whenever the ratio is not defined; never 0 as a stand-in
    (api_contract.md §1.3)."""

    if not isinstance(numerator, (int, float)) or not isinstance(denominator, (int, float)):
        return None
    if not denominator:
        return None
    return numerator / denominator


def _borough_chief_citywide(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Citywide scalars: totals first, formula once. §6.2 forbids averaging the
    29 district `yrr` values."""

    if not rows:
        return None

    def total(field: str) -> float:
        return sum(row.get(field) or 0 for row in rows)

    elected = total("elected_seat_count")
    youth_elected = total("youth_elected_count")
    seat_share = _divide(youth_elected, elected)
    youth_share = _divide(total("youth_population_18_35"), total("population_total"))

    return {
        "year_roc": BOROUGH_CHIEF_YEAR_ROC,
        "elected_count": elected,
        "youth_elected_count": youth_elected,
        "ratio_percent": None if seat_share is None else seat_share * 100,
        "yrr": None if seat_share is None or youth_share is None else _divide(seat_share, youth_share),
        # Same source semantics as the analysis rows they were summed from.
        "denominator_type": rows[0].get("denominator_type"),
        "proxy": rows[0].get("proxy"),
    }


def _districts_with_scalars(
    dashboard: Mapping[str, Any], participation: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """districts[] plus the 111-term scalars §6.2 requires overview to carry.

    Field mapping only -- both values are already computed by
    `calculate_youth_borough_metrics()`.
    """

    by_district = {row.get("district_id"): row for row in _borough_chief_districts(participation)}
    districts = []
    for district in dashboard.get("districts") or []:
        enriched = dict(district)
        row = by_district.get(enriched.get("district_id")) or {}
        enriched["youthBoroughChiefRatioPercent"] = row.get("youth_borough_chief_ratio")
        enriched["yrr"] = row.get("yrr")
        districts.append(enriched)
    return districts


def _employment_plots(employment: Mapping[str, Any]) -> list[dict[str, Any]]:
    scatter = employment.get("scatter") or {}
    plots = []
    for source_key, plot_id in _SCATTER_PLOT_IDS.items():
        plot = scatter.get(source_key)
        if isinstance(plot, Mapping):
            plots.append({"id": plot_id, **plot})
    return plots


def _fafi_districts(
    fertility: Mapping[str, Any], names: Mapping[str, str]
) -> list[dict[str, Any]]:
    """fafi.districts is keyed by district_id with camelCase scores; the
    contract serves a list using the snake_case field names."""

    fafi = (fertility.get("fafi") or {}).get("districts") or {}
    return [
        {
            "district_id": district_id,
            "district_name": names.get(district_id),
            "fafi_score": scores.get("fafiScore"),
            "fafi_level": scores.get("fafiLevel"),
        }
        for district_id, scores in sorted(fafi.items())
        if isinstance(scores, Mapping)
    ]


def _budget_by_department(participation: Mapping[str, Any]) -> list[dict[str, Any]]:
    """youthBudgetAllocation items -> api_contract.md §6.3's shape. `amount`
    is TWD; the contract field is thousands."""

    allocation = participation.get("budget_allocation") or {}
    return [
        {
            "label": item.get("name"),
            "amount_thousand": _divide(item.get("amount"), 1000),
            "share_percent": item.get("share_percent"),
        }
        for item in (allocation.get("items") or [])
        if isinstance(item, Mapping)
    ]


def _keyword_frequency(participation: Mapping[str, Any]) -> dict[str, Any]:
    """The canonical §6.4 analysis, kept in its full-period shape. The legacy
    `/youth-topic-weight` URL is an alias the reader resolves; no second item
    with `topics[]` or a `year_roc` is written."""

    source = (participation.get("topics") or {}).get("keyword_frequency") or {}
    item = {field: source.get(field) for field in _KEYWORD_FREQUENCY_FIELDS}
    item["analysis_id"] = source.get("analysis_id") or "youth-keyword-frequency"
    return item


def _gzip_json(value: Any, label: str) -> bytes:
    """JSON text rather than a DynamoDB map: maps do not keep key order, and the
    order decides which evidence survives ai-service's per-dataset truncation."""

    raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    payload = gzip.compress(raw, compresslevel=9, mtime=0)
    if len(payload) > _AI_CONTEXT_MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"AI context {label} is {len(payload)} bytes gzipped, "
            f"over the {_AI_CONTEXT_MAX_PAYLOAD_BYTES}-byte DynamoDB item budget"
        )
    return payload


def _ai_context_items(
    manifest: Mapping[str, Any],
    dashboard: Mapping[str, Any],
    analyses: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """The whole snapshot, untrimmed: villages and the other subtrees the
    dashboard items drop stay in, because ai-service's flattener skips them
    itself and must see exactly what the local snapshot files contain."""

    snapshot_id = manifest.get("snapshot_id")
    items: list[dict[str, Any]] = [
        {
            "pk": AI_CONTEXT_PK,
            "sk": "MANIFEST",
            "snapshot_id": snapshot_id,
            "encoding": AI_CONTEXT_ENCODING,
            "payload": _gzip_json(dict(manifest), "manifest"),
        }
    ]
    artifacts: dict[str, Mapping[str, Any]] = {"dashboard_overview": dashboard, **analyses}
    for artifact_key, content in artifacts.items():
        if artifact_key in _AI_CONTEXT_SKIPPED_ARTIFACTS:
            continue
        items.append(
            {
                "pk": AI_CONTEXT_PK,
                "sk": f"ARTIFACT#{artifact_key}",
                "snapshot_id": snapshot_id,
                "artifact_key": artifact_key,
                "encoding": AI_CONTEXT_ENCODING,
                "payload": _gzip_json(dict(content), artifact_key),
            }
        )
    return items


def build_items(
    *,
    manifest: Mapping[str, Any],
    dashboard: Mapping[str, Any],
    analyses: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Every DynamoDB item for one snapshot, `pk`/`sk` included.

    `analyses` is keyed by published artifact name (employment, fertility,
    participation, policy_support), matching manifest.artifacts.analyses.
    """

    employment = analyses.get("employment") or {}
    fertility = analyses.get("fertility") or {}
    participation = analyses.get("participation") or {}
    outcomes = (analyses.get("policy_support") or {}).get("policyOutcomes") or {}

    districts = _districts_with_scalars(dashboard, participation)
    names = {d.get("district_id"): d.get("district_name") for d in districts}
    policy = dashboard.get("policy") or {}

    items: list[dict[str, Any]] = [
        {
            "pk": "DASHBOARD",
            "sk": "KPIS",
            "kpis": dashboard.get("kpis"),
            "availability": dashboard.get("availability"),
        },
        {
            "pk": "DASHBOARD",
            "sk": "POLICY",
            **policy,
            # §6.3 pairs the rate with the year it belongs to. homepage selects
            # the latest usable execution year separately from the latest legal
            # budget; the key stays present (null) for snapshots that predate it.
            "executionRateYearRoc": policy.get("executionRateYearRoc"),
        },
        {
            "pk": "DASHBOARD",
            "sk": "SERVICE_COVERAGE",
            **{
                key: value
                for key, value in (dashboard.get("service_coverage") or {}).items()
                if key not in _SERVICE_COVERAGE_DROP
            },
        },
        {
            "pk": "DASHBOARD",
            "sk": "ELECTIONS",
            **{
                key: value
                for key, value in (dashboard.get("elections") or {}).items()
                if key not in _ELECTIONS_DROP
            },
            "borough_chief_v1_citywide": _borough_chief_citywide(
                _borough_chief_districts(participation)
            ),
        },
        {
            "pk": "DASHBOARD",
            "sk": "POPULATION_TREND",
            "years": ((dashboard.get("annual") or {}).get("population") or {}).get("years") or [],
        },
        {
            "pk": "DASHBOARD",
            "sk": "FERTILITY_TREND",
            "years": ((dashboard.get("annual") or {}).get("fertility") or {}).get("years") or [],
        },
        {"pk": "DASHBOARD", "sk": "DISTRICTS", "districts": districts},
    ]

    items.extend(
        {"pk": f"DISTRICT#{district['district_id']}", "sk": "SUMMARY", **district}
        for district in districts
    )

    items.extend(
        [
            {
                "pk": "ANALYSIS#employment-scatter",
                "sk": "DATA",
                "analysis_id": "employment-scatter",
                "geo_level": "district",
                "plots": _employment_plots(employment),
                "limitations": [],
            },
            {
                "pk": "ANALYSIS#fertility-overlay",
                "sk": "DATA",
                "analysis_id": "fertility-overlay",
                "geo_level": "district",
                **{
                    key: value
                    for key, value in (fertility.get("scatter") or {}).items()
                    if key in ("points", "regression")
                },
            },
            {
                "pk": "ANALYSIS#fertility-family-friendliness",
                "sk": "DATA",
                "analysis_id": "fertility-family-friendliness",
                "geo_level": "district",
                "districts": _fafi_districts(fertility, names),
            },
            {
                "pk": "ANALYSIS#youth-keyword-frequency",
                "sk": "DATA",
                **_keyword_frequency(participation),
            },
            {
                "pk": "ANALYSIS#politics-resource-io",
                "sk": "DATA",
                "analysis_id": "politics-resource-io",
                "geo_level": "county",
                "budget_by_department": _budget_by_department(participation),
            },
            {
                "pk": "ANALYSIS#policy-outcomes",
                "sk": "DATA",
                "analysis_id": "policy-outcomes",
                "geo_level": "county",
                "wageTrend": outcomes.get("wageTrend") or [],
                "currentWageGrowth": outcomes.get("currentWageGrowth"),
                "currentPopGrowth": outcomes.get("currentPopGrowth"),
                "desiredDirection": dict(DESIRED_DIRECTION),
            },
        ]
    )

    items.extend(_ai_context_items(manifest, dashboard, analyses))

    # Written last: readers use it to decide the snapshot is complete.
    items.append(
        {
            "pk": MANIFEST_KEY[0],
            "sk": MANIFEST_KEY[1],
            "schema_version": manifest.get("schema_version"),
            "snapshot_id": manifest.get("snapshot_id"),
            "generated_at": manifest.get("generated_at"),
            "calculation_version": dashboard.get("calculation_version"),
            "districts_count": len(districts),
            "time_policy": dashboard.get("time_policy"),
            "warnings": manifest.get("warnings") or [],
        }
    )
    return items


def to_dynamodb_types(value: Any) -> Any:
    """boto3's resource client rejects float; everything else passes through."""

    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, Mapping):
        return {key: to_dynamodb_types(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [to_dynamodb_types(item) for item in value]
    return value
