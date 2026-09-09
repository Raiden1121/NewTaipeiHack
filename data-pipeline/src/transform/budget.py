"""Transform Youth Bureau budget rows at organization grain."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

from .common import (
    TransformValueError,
    build_common_metadata,
    clean_text,
    parse_decimal,
    parse_int,
    parse_roc_year,
)
from .contracts import TransformResult
from .quality import QualityCollector


_DOCUMENT_STATUSES = frozenset({"proposed_budget", "legal_budget"})
_ROW_TYPES = frozenset({"total", "detail"})


def transform_youth_budgets(
    records: Iterable[Mapping[str, Any]],
    *,
    fetched_at: str | None = None,
) -> TransformResult:
    raw_rows = [dict(record) for record in records]
    quality = QualityCollector(rows_in=len(raw_rows))
    output: list[dict[str, Any]] = []

    for index, raw in enumerate(raw_rows):
        try:
            document_id = _required_text(raw, "document_id")
            budget_year_roc = _required_text(raw, "budget_year_roc")
            year = parse_roc_year(budget_year_roc, field="budget_year_roc")
            document_status = _required_text(raw, "document_status")
            if document_status not in _DOCUMENT_STATUSES:
                raise TransformValueError(
                    f"document_status is unsupported: {document_status!r}"
                )
            row_type = _required_text(raw, "row_type")
            if row_type not in _ROW_TYPES:
                raise TransformValueError(f"row_type is unsupported: {row_type!r}")
            business_plan = _required_text(raw, "business_plan")
            work_plan = clean_text(raw.get("work_plan"))
            if row_type == "detail" and work_plan is None:
                raise TransformValueError("missing_work_plan")
            if row_type == "total" and work_plan is not None:
                raise TransformValueError("total_work_plan_must_be_null")
            unit_label = _required_text(raw, "unit_label")
            if unit_label != "新臺幣千元":
                raise TransformValueError(f"unit_label is unsupported: {unit_label!r}")
            amount = parse_int(raw.get("budget_amount"), field="budget_amount", allow_none=False)
            ratio = parse_decimal(raw.get("ratio_percent"), field="ratio_percent", allow_none=False)
        except TransformValueError as exc:
            quality.record_numeric_error()
            quality.reject(index, raw, f"invalid_value:{exc}")
            continue

        curated = build_common_metadata(
            dataset="youth_budgets",
            source="ntpc_youth_bureau_budget",
            source_record_id=document_id,
            geo_level="organization",
            district_id=None,
            district_name=None,
            period_start=f"{year}-01-01",
            period_end=f"{year}-12-31",
            period_type="year",
            metric_id="budget_amount",
            value=amount,
            unit="TWD_thousand",
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=fetched_at,
        )
        curated.update(
            {
                "organization_name": "新北市青年局",
                "budget_year_roc": budget_year_roc,
                "document_status": document_status,
                "document_status_label": clean_text(raw.get("document_status_label")),
                "row_type": row_type,
                "business_plan": business_plan,
                "work_plan": work_plan,
                "budget_ratio_percent": ratio,
                "source_pdf_sha256": clean_text(raw.get("source_pdf_sha256")),
                "raw_record": deepcopy(raw),
            }
        )
        output.append(curated)
        quality.accept()

    return TransformResult(output, quality.finish(), quality.quarantine)


def _required_text(record: Mapping[str, Any], field: str) -> str:
    value = clean_text(record.get(field))
    if value is None:
        raise TransformValueError(f"{field} is required")
    return value
