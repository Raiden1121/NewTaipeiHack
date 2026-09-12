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


_DOCUMENT_STATUSES = frozenset(
    {"proposed_budget", "legal_budget", "final_settlement"}
)
_ROW_TYPES = frozenset({"total", "detail", "allocation"})
_ALLOCATION_CODES = frozenset({"01", "02", "03", "04"})


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
            if (
                document_status != "final_settlement"
                and row_type == "detail"
                and work_plan is None
            ):
                raise TransformValueError("missing_work_plan")
            if (
                document_status != "final_settlement"
                and row_type == "total"
                and work_plan is not None
            ):
                raise TransformValueError("total_work_plan_must_be_null")
            allocation_code = clean_text(raw.get("allocation_code"))
            allocation_name = clean_text(raw.get("allocation_name"))
            if row_type == "allocation":
                if allocation_code not in _ALLOCATION_CODES:
                    raise TransformValueError(
                        f"allocation_code is unsupported: {allocation_code!r}"
                    )
                if allocation_name is None:
                    raise TransformValueError("allocation_name is required")
                if work_plan is None:
                    raise TransformValueError("allocation_work_plan_is_required")
            unit_label = _required_text(raw, "unit_label")
            expected_unit = (
                "新臺幣元" if document_status == "final_settlement" else "新臺幣千元"
            )
            if row_type == "allocation":
                expected_unit = "新臺幣元"
            if unit_label != expected_unit:
                raise TransformValueError(f"unit_label is unsupported: {unit_label!r}")
            ratio = None
            if row_type == "allocation":
                budget_amount = parse_int(
                    raw.get("budget_amount"), field="budget_amount", allow_none=False
                )
                settlement_amount = None
                realized_amount = None
                payable_amount = None
                reserved_amount = None
                surplus_amount = None
                source_execution_ratio = None
                value = budget_amount
                metric_id = "budget_allocation_amount"
                unit = "TWD"
            elif document_status == "final_settlement":
                budget_amount = parse_int(
                    raw.get("budget_amount"), field="budget_amount", allow_none=False
                )
                settlement_amount = parse_int(
                    raw.get("settlement_amount"),
                    field="settlement_amount",
                )
                realized_amount = parse_int(
                    raw.get("realized_amount"), field="realized_amount"
                )
                payable_amount = parse_int(
                    raw.get("payable_amount"), field="payable_amount"
                )
                reserved_amount = parse_int(
                    raw.get("reserved_amount"), field="reserved_amount"
                )
                surplus_amount = _parse_signed_int(
                    raw.get("surplus_amount"), field="surplus_amount"
                )
                source_execution_ratio = parse_decimal(
                    raw.get("source_execution_ratio_percent"),
                    field="source_execution_ratio_percent",
                )
                value = settlement_amount
                metric_id = "settlement_amount"
                unit = "TWD"
            else:
                budget_amount = parse_int(
                    raw.get("budget_amount"), field="budget_amount", allow_none=False
                )
                settlement_amount = None
                realized_amount = None
                payable_amount = None
                reserved_amount = None
                surplus_amount = None
                source_execution_ratio = None
                ratio = parse_decimal(
                    raw.get("ratio_percent"), field="ratio_percent", allow_none=False
                )
                value = budget_amount
                metric_id = "budget_amount"
                unit = "TWD_thousand"
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
            metric_id=metric_id,
            value=value,
            unit=unit,
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
                "budget_ratio_percent": ratio if document_status != "final_settlement" else None,
                "budget_amount": budget_amount,
                "allocation_code": allocation_code,
                "allocation_name": allocation_name,
                "budget_section": clean_text(raw.get("budget_section")),
                "account_category": clean_text(raw.get("account_category")),
                "realized_amount": realized_amount,
                "payable_amount": payable_amount,
                "reserved_amount": reserved_amount,
                "settlement_amount": settlement_amount,
                "surplus_amount": surplus_amount,
                "source_execution_ratio_percent": source_execution_ratio,
                "source_pdf_sha256": clean_text(raw.get("source_pdf_sha256")),
                "source_page_number": raw.get("source_page_number"),
                "source_document_url": clean_text(raw.get("source_document_url")),
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


def _parse_signed_int(value: Any, *, field: str) -> int | None:
    text = clean_text(value)
    if text is None:
        return None
    normalized = text.replace(",", "")
    if not normalized.lstrip("+").lstrip("-").isdigit():
        raise TransformValueError(f"{field} must be an integer: {value!r}")
    return int(normalized)
