"""All-ages movement context metrics by district and month."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any, Iterable, Mapping

from .common import TransformValueError, build_common_metadata, get_source_value, parse_int, parse_roc_month
from .contracts import TransformResult
from .geography import DistrictResolver
from .population import _month_bounds, _sum_complete
from .quality import QualityCollector


def transform_movement(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    groups: dict[tuple[str, str], dict[str, Any]] = {}

    for index, raw in enumerate(raw_rows):
        match = resolver.resolve_name(raw.get("site_id")) or resolver.resolve_code(raw.get("district_code"))
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        try:
            period = parse_roc_month(get_source_value(raw, "statistic_yyymm"), field="statistic_yyymm")
            numeric = {
                key: parse_int(value, field=key)
                for key, value in raw.items()
                if key.startswith("in_") or key.startswith("out_")
            }
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        district_id, district_name = match
        group = groups.setdefault(
            (district_id, period),
            {"district_name": district_name, "metrics": defaultdict(list), "raw_records": [], "source_record_ids": []},
        )
        for metric_id, value in numeric.items():
            group["metrics"][metric_id].append(value)
            if value is None:
                quality.record_missing(metric_id)
        group["raw_records"].append(deepcopy(raw))
        group["source_record_ids"].append(str(raw.get("district_code") or f"{raw.get('site_id', '')}:{raw.get('village', '')}"))

    output: list[dict[str, Any]] = []
    for (district_id, period), group in sorted(groups.items()):
        aggregated = {metric_id: _sum_complete(values) for metric_id, values in group["metrics"].items()}
        movement_in = _sex_total(aggregated, "in_total")
        movement_out = _sex_total(aggregated, "out_total")
        net = None if movement_in is None or movement_out is None else movement_in - movement_out
        if net is None:
            quality.warn("incomplete_movement_totals")
        metrics = dict(aggregated)
        metrics.update(
            {
                "movement_in_total": movement_in,
                "movement_out_total": movement_out,
                "net_movement_total": net,
            }
        )
        start, end = _month_bounds(period)
        for metric_id, value in sorted(metrics.items()):
            curated = build_common_metadata(
                dataset="movement",
                source="moi_household_registration",
                source_record_id=f"movement:{district_id}:{period}",
                geo_level="district",
                district_id=district_id,
                district_name=group["district_name"],
                period_start=start,
                period_end=end,
                period_type="month",
                metric_id=metric_id,
                value=value,
                unit="people",
                age_scope="all_ages",
                age_min=None,
                age_max=None,
                youth_eligibility="context_only",
                fetched_at=fetched_at,
                quality_flags=["incomplete_movement_totals"] if net is None and metric_id == "net_movement_total" else None,
            )
            curated["source_record_ids"] = list(group["source_record_ids"])
            curated["raw_records"] = deepcopy(group["raw_records"])
            output.append(curated)
            quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def _sex_total(metrics: dict[str, int | None], prefix: str) -> int | None:
    if prefix in metrics:
        return metrics[prefix]
    male = metrics.get(f"{prefix}_m")
    female = metrics.get(f"{prefix}_f")
    return None if male is None or female is None else male + female
