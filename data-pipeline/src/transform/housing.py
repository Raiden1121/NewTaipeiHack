"""Transaction-level housing and rental observations."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    parse_decimal,
    parse_roc_date,
)
from .contracts import TransformResult
from .geography import DistrictResolver
from .quality import QualityCollector


def transform_house_prices(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_housing(
        records,
        resolver=resolver,
        fetched_at=fetched_at,
        dataset="house_prices",
        date_field="transaction_date",
        domain_fields={
            "total_price": ("total_price", "TWD"),
            "building_area_sqm": ("building_area", "square_metre"),
            "price_per_sqm": ("price_per_sqm", "TWD_per_square_metre"),
            "price_per_ping": ("price_per_ping", "TWD_per_ping"),
        },
        passthrough=("transaction_type", "snapshot_fetched_at"),
    )


def transform_rentals(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None = None,
) -> TransformResult:
    return _transform_housing(
        records,
        resolver=resolver,
        fetched_at=fetched_at,
        dataset="rentals",
        date_field="rental_date",
        domain_fields={
            "rent_total": ("rent_total", "TWD"),
            "building_area_sqm": ("building_area", "square_metre"),
            "rent_per_sqm": ("rent_per_sqm", "TWD_per_square_metre"),
            "rent_per_ping": ("rent_per_ping", "TWD_per_ping"),
        },
        passthrough=("rent_per_sqm_source", "rental_type", "snapshot_fetched_at"),
    )


def _transform_housing(
    records: Iterable[Mapping[str, Any]],
    *,
    resolver: DistrictResolver,
    fetched_at: str | None,
    dataset: str,
    date_field: str,
    domain_fields: dict[str, tuple[str, str]],
    passthrough: tuple[str, ...],
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_rows):
        match = resolver.resolve_name(raw.get("district"))
        if match is None:
            quality.record_unmapped_district()
            quality.reject(index, raw, "unmapped_district")
            continue
        try:
            period = parse_roc_date(raw.get(date_field) or raw.get("rps07_yyymmddroc"), field=date_field)
            parsed_fields = {
                output_name: parse_decimal(raw.get(source_name), field=source_name)
                for source_name, (output_name, _unit) in domain_fields.items()
            }
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue
        district_id, district_name = match
        flags: list[str] = []
        if period is None:
            quality.record_missing(date_field)
            quality.warn(f"missing_period:{dataset}")
            flags.append("missing_period")
        curated = build_common_metadata(
            dataset=dataset,
            source="new_taipei_real_estate_open_data",
            source_record_id=build_source_record_id(dataset, index, raw),
            geo_level="district",
            district_id=district_id,
            district_name=district_name,
            period_start=period,
            period_end=period,
            period_type="day" if period else None,
            metric_id=None,
            value=None,
            unit=None,
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at or raw.get("snapshot_fetched_at"),
            quality_flags=flags,
        )
        for source_name, (output_name, unit) in domain_fields.items():
            value = parsed_fields[output_name]
            curated[output_name] = _coerce_number(value)
            curated[f"{output_name}_unit"] = unit
            if value is None:
                quality.record_missing(source_name)
        for field in passthrough:
            curated[field] = deepcopy(raw.get(field))
        curated["raw_record"] = deepcopy(raw)
        output.append(curated)
        quality.accept()
    return TransformResult(output, quality.finish(), quality.quarantine)


def _coerce_number(value: float | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if value.is_integer() else value
