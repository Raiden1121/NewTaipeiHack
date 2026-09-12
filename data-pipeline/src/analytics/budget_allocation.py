"""Calculate Youth Bureau budget allocation analytics from curated rows."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


EXPECTED_ALLOCATION_CODES = ("01", "02", "03", "04")
_DOCUMENT_STATUS_PRIORITY = ("legal_budget", "proposed_budget")
_PERCENT_QUANTUM = Decimal("0.01")


def calculate_budget_allocation(
    records: Iterable[Mapping[str, Any]], *, reference_year_roc: int
) -> dict[str, Any]:
    """Build the public allocation payload for one explicitly selected ROC year.

    Allocation rows are measured in TWD.  The source summary row is measured in
    thousand TWD, so it is converted only for the total-consistency check.  A
    complete, matching set of 01-04 rows is the only case marked ``observed``.
    """

    year = int(reference_year_roc)
    rows = [dict(row) for row in records]
    candidate_rows = [
        row
        for row in rows
        if _roc_year(row) == year and row.get("row_type") == "allocation"
    ]
    document_status = _select_document_status(candidate_rows, rows, year)
    if document_status is not None:
        candidate_rows = [
            row for row in candidate_rows if row.get("document_status") == document_status
        ]

    by_code: dict[str, dict[str, Any]] = {}
    duplicate_codes: set[str] = set()
    invalid_amount_count = 0
    for row in candidate_rows:
        code = _text(row.get("allocation_code") or row.get("code"))
        amount = _integer(row.get("value"), row.get("budget_amount"))
        if code not in EXPECTED_ALLOCATION_CODES or amount is None:
            invalid_amount_count += 1
            continue
        if code in by_code:
            duplicate_codes.add(code)
            continue
        by_code[code] = row | {"_amount": amount}

    missing_codes = [code for code in EXPECTED_ALLOCATION_CODES if code not in by_code]
    calculated_total = sum(row["_amount"] for row in by_code.values())
    source_total = _find_source_total(rows, year=year, document_status=document_status)

    blocking_reasons: list[str] = []
    if missing_codes or invalid_amount_count:
        blocking_reasons.append("budget_allocation_rows_incomplete")
    if duplicate_codes:
        blocking_reasons.append("budget_allocation_duplicate_code")
    if source_total is None:
        blocking_reasons.append("budget_allocation_source_total_unavailable")
    elif calculated_total != source_total:
        blocking_reasons.append("budget_allocation_total_mismatch")

    denominator = source_total
    if denominator is None and not missing_codes and not duplicate_codes:
        denominator = calculated_total
    items = [
        _public_item(row, denominator=denominator)
        for code, row in by_code.items()
    ]
    if not items:
        status = "unavailable"
    elif not blocking_reasons and len(items) == len(EXPECTED_ALLOCATION_CODES):
        status = "observed"
    else:
        status = "partial"

    total_amount = source_total
    if total_amount is None and not missing_codes and not duplicate_codes:
        total_amount = calculated_total

    return {
        "metric_id": "youthBudgetAllocation",
        "budget_year_roc": year,
        "document_status": document_status,
        "total_amount": total_amount,
        "unit": "TWD",
        "items": items,
        "status": status,
        "source_datasets": ["youth_budgets"],
        "source_period": [str(year)],
        "coverage": {
            "expected_allocation_count": len(EXPECTED_ALLOCATION_CODES),
            "observed_allocation_count": len(items),
            "missing_codes": missing_codes,
            "duplicate_codes": sorted(duplicate_codes),
            "calculated_total_amount": calculated_total if items else None,
            "source_total_amount": source_total,
            "total_matches_source": (
                source_total is not None and calculated_total == source_total
            ),
        },
        "blocking_reasons": blocking_reasons,
    }


def _select_document_status(
    allocation_rows: Iterable[Mapping[str, Any]],
    all_rows: Iterable[Mapping[str, Any]],
    year: int,
) -> str | None:
    statuses = {
        _text(row.get("document_status"))
        for row in all_rows
        if _roc_year(row) == year and row.get("row_type") in {"allocation", "detail", "total"}
    }
    allocation_statuses = {
        _text(row.get("document_status")) for row in allocation_rows
    }
    for status in _DOCUMENT_STATUS_PRIORITY:
        if status in allocation_statuses:
            return status
    for status in _DOCUMENT_STATUS_PRIORITY:
        if status in statuses:
            return status
    return next((status for status in statuses if status), None)


def _find_source_total(
    records: Iterable[Mapping[str, Any]], *, year: int, document_status: str | None
) -> int | None:
    for row in records:
        if (
            _roc_year(row) != year
            or row.get("row_type") != "detail"
            or row.get("business_plan") != "青年發展業務"
            or document_status is not None
            and row.get("document_status") != document_status
        ):
            continue
        amount = _integer(row.get("budget_amount"), row.get("value"))
        if amount is None:
            continue
        unit = _text(row.get("unit")) or _text(row.get("unit_label"))
        if unit in {"TWD_thousand", "新臺幣千元"}:
            return amount * 1000
        if unit in {"TWD", "新臺幣元"}:
            return amount
    return None


def _public_item(row: Mapping[str, Any], *, denominator: int | None) -> dict[str, Any]:
    amount = int(row["_amount"])
    share = None
    if denominator not in (None, 0):
        share = float(
            (Decimal(amount) * Decimal(100) / Decimal(denominator)).quantize(
                _PERCENT_QUANTUM, rounding=ROUND_HALF_UP
            )
        )
    return {
        "code": _text(row.get("allocation_code") or row.get("code")),
        "name": _text(row.get("allocation_name") or row.get("name") or row.get("work_plan")),
        "amount": amount,
        "share_percent": share,
        "budget_section": _text(row.get("budget_section")),
        "account_category": _text(row.get("account_category")),
        "source_pdf_sha256": _text(row.get("source_pdf_sha256")),
    }


def _integer(*values: Any) -> int | None:
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            text = str(value).strip().replace(",", "")
            if not text:
                continue
            return int(Decimal(text))
        except (InvalidOperation, TypeError, ValueError):
            continue
    return None


def _roc_year(row: Mapping[str, Any]) -> int | None:
    value = row.get("budget_year_roc") or row.get("year_roc")
    if value is None:
        return None
    try:
        parsed = int(str(value).rstrip("年"))
    except (TypeError, ValueError):
        return None
    return parsed - 1911 if parsed >= 1911 else parsed


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["EXPECTED_ALLOCATION_CODES", "calculate_budget_allocation"]
