"""Annual population, fertility, and Youth Bureau budget analytics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any


def calculate_annual_population(
    population_by_period: Iterable[Mapping[str, Any]], *, annual_years_roc: Iterable[int]
) -> dict[str, Any]:
    """Use the latest available monthly population row in each ROC year."""

    years = [int(year) for year in annual_years_roc]
    latest: dict[tuple[int, str, str], dict[str, Any]] = {}
    for raw in population_by_period:
        year = _roc_year(raw)
        district_id = raw.get("district_id")
        metric = raw.get("metric_id")
        if year is None or year not in set(years) | {min(years) - 1} or district_id is None or metric not in {"people_total", "youth_18_35_total"}:
            continue
        key = (year, str(district_id), str(metric))
        if key not in latest or _period_key(raw) >= _period_key(latest[key]):
            latest[key] = dict(raw)
    output_years: list[dict[str, Any]] = []
    city_totals: dict[int, dict[str, float]] = {}
    for year in years:
        districts: dict[str, dict[str, Any]] = {}
        source_periods: set[str] = set()
        for (row_year, district_id, metric), raw in latest.items():
            if row_year != year:
                continue
            value = _number(raw.get("value"))
            if value is None:
                continue
            item = districts.setdefault(district_id, {"district_id": district_id, "district_name": raw.get("district_name")})
            item[metric] = value
            source_periods.add(str(raw.get("period_start") or raw.get("period_end") or ""))
        for item in districts.values():
            total = item.get("people_total")
            youth = item.get("youth_18_35_total")
            item["youth_share_percent"] = None if total in (None, 0) or youth is None else youth / total * 100
        city_total = sum(item.get("people_total", 0) for item in districts.values())
        city_youth = sum(item.get("youth_18_35_total", 0) for item in districts.values())
        city_totals[year] = {"people_total": city_total, "youth_18_35_total": city_youth}
        output_years.append(
            {
                "year_roc": year,
                "source_period": sorted(source_periods),
                "period_type": "annual",
                "quality_status": "observed" if districts else "unavailable",
                "districts": sorted(districts.values(), key=lambda row: row["district_id"]),
                "city": {
                    "people_total": city_total if districts else None,
                    "youth_18_35_total": city_youth if districts else None,
                    "youth_share_percent": None if not districts or city_total == 0 else city_youth / city_total * 100,
                },
            }
        )
    for index, year in enumerate(years):
        baseline = city_totals.get(year - 1)
        if baseline is None:
            baseline = _city_totals_from_latest(latest, year - 1)
        current = city_totals.get(year)
        city = output_years[index]["city"]
        city["yoy_percent"] = _yoy(current.get("people_total") if current else None, baseline.get("people_total") if baseline else None)
    return {"metric_id": "annualPopulation", "years": output_years}


def _city_totals_from_latest(
    latest: Mapping[tuple[int, str, str], Mapping[str, Any]], year: int
) -> dict[str, float] | None:
    totals = {"people_total": 0.0, "youth_18_35_total": 0.0}
    found = False
    for (row_year, _district_id, metric), raw in latest.items():
        if row_year != year or metric not in totals:
            continue
        value = _number(raw.get("value"))
        if value is None:
            continue
        totals[metric] += value
        found = True
    return totals if found else None


def calculate_annual_fertility(
    birth_records: Iterable[Mapping[str, Any]],
    population_by_month: Iterable[Mapping[str, Any]],
    *,
    annual_years_roc: Iterable[int],
) -> dict[str, Any]:
    """Calculate age-18–35 births per 1,000 average monthly female population."""

    years = [int(year) for year in annual_years_roc]
    births: dict[tuple[int, str], float] = defaultdict(float)
    for raw in birth_records:
        year = _roc_year(raw)
        district_id = raw.get("district_id")
        value = _number(raw.get("value"))
        if year in years and district_id is not None and value is not None:
            births[(year, str(district_id))] += value
    female: dict[tuple[int, str, str], float] = {}
    for raw in population_by_month:
        if raw.get("metric_id") != "youth_18_35_female":
            continue
        year = _roc_year(raw)
        district_id = raw.get("district_id")
        value = _number(raw.get("value"))
        month = str(raw.get("period_start") or "")[:7]
        if year in years and district_id is not None and value is not None and month:
            female[(year, str(district_id), month)] = value
    output_years: list[dict[str, Any]] = []
    for year in years:
        districts = sorted({district for row_year, district in births if row_year == year} | {district for row_year, district, _ in female if row_year == year})
        monthly_city: dict[str, float] = defaultdict(float)
        for (row_year, district, month), value in female.items():
            if row_year == year:
                monthly_city[month] += value
        available_months = len(monthly_city)
        city_denominator = sum(monthly_city.values()) / available_months if available_months else None
        district_rows: list[dict[str, Any]] = []
        for district in districts:
            month_values = [value for (row_year, row_district, _), value in female.items() if row_year == year and row_district == district]
            denominator = sum(month_values) / len(month_values) if month_values else None
            numerator = births.get((year, district), 0.0)
            district_rows.append(
                {
                    "district_id": district,
                    "births_mother_age_18_35": numerator,
                    "average_monthly_female_18_35": denominator,
                    "fertility_rate": None if denominator in (None, 0) else numerator / denominator * 1000,
                    "available_months": len(month_values),
                    "coverage_ratio": len(month_values) / 12,
                    "source_period": str(year),
                    "period_type": "annual",
                }
            )
        numerator = sum(births.get((year, district), 0.0) for district in districts)
        city_rate = None if city_denominator in (None, 0) else numerator / city_denominator * 1000
        if city_rate not in (None, 0):
            for row in district_rows:
                district_rate = row.get("fertility_rate")
                row["fertilityVsCityAvg"] = (
                    None if district_rate is None else district_rate / city_rate * 100
                )
        output_years.append(
            {
                "year_roc": year,
                "city": {
                    "births_mother_age_18_35": numerator,
                    "average_monthly_female_18_35": city_denominator,
                    "fertility_rate": city_rate,
                    "available_months": available_months,
                    "coverage_ratio": available_months / 12,
                    "quality_status": "observed" if available_months == 12 else ("partial" if available_months else "unavailable"),
                },
                "districts": district_rows,
            }
        )
    return {"metric_id": "generalFertilityRate", "years": output_years}


def calculate_budget_series(
    budget_records: Iterable[Mapping[str, Any]],
    settlement_records: Iterable[Mapping[str, Any]],
    *,
    annual_years_roc: Iterable[int],
) -> dict[str, Any]:
    """Separate legal budget trend from final-settlement execution rates."""

    years = [int(year) for year in annual_years_roc]
    legal: dict[int, dict[str, Any]] = {}
    for raw in budget_records:
        year = _int(raw.get("budget_year_roc"))
        if year not in years or raw.get("row_type") != "total" or raw.get("document_status") != "legal_budget":
            continue
        amount = _number(raw.get("budget_amount") if raw.get("budget_amount") is not None else raw.get("value"))
        if amount is not None:
            legal[year] = dict(raw) | {"_amount": amount}
    settlements: dict[int, dict[str, Any]] = {}
    for raw in settlement_records:
        year = _int(raw.get("budget_year_roc"))
        if year not in years or raw.get("row_type") != "total" or raw.get("document_status") != "final_settlement":
            continue
        settlements[year] = dict(raw)
    trend: list[dict[str, Any]] = []
    previous_amount: float | None = None
    for year in years:
        legal_row = legal.get(year)
        settlement = settlements.get(year)
        amount = legal_row.get("_amount") if legal_row else None
        realized = _number(settlement.get("realized_amount")) if settlement else None
        source_execution_ratio = (
            _number(settlement.get("source_execution_ratio_percent"))
            if settlement
            else None
        )
        source_record_type = _source_record_type(settlement) if settlement else None
        execution_source = None
        if (
            source_record_type == "prior_year_settlement_summary"
            and source_execution_ratio is not None
        ):
            # This is an official ratio reported in a prior-year summary. Its
            # settlement and budget amounts do not share the legal-budget
            # denominator used by the normal realised-amount calculation.
            execution = source_execution_ratio
            execution_source = "source_execution_ratio_percent"
            execution_denominator = None
            execution_denominator_unit = None
            conversion = None
        else:
            execution_denominator, conversion = _execution_denominator(
                amount, legal_row, settlement
            )
            execution_denominator_unit = settlement.get("unit") if settlement else None
            execution = (
                None
                if execution_denominator in (None, 0) or realized is None
                else realized / execution_denominator * 100
            )
            if execution is not None:
                execution_source = "realized_amount"
        failure = None
        if settlement is None:
            failure = "final_settlement_unavailable"
        elif execution is None and realized is None:
            failure = "realized_amount_unparsed"
        trend.append(
            {
                "year_roc": year,
                "legal_budget_amount": amount,
                "budget_unit": legal_row.get("unit") if legal_row else None,
                "budget_status": "legal_budget" if legal_row else "unavailable",
                "budget_yoy_percent": _yoy(amount, previous_amount),
                "realized_amount": realized,
                "legal_budget_amount_for_execution": execution_denominator,
                "execution_denominator_unit": execution_denominator_unit,
                "execution_unit_conversion": conversion,
                "settlement_amount": _number(settlement.get("settlement_amount")) if settlement else None,
                "payable_amount": _number(settlement.get("payable_amount")) if settlement else None,
                "reserved_amount": _number(settlement.get("reserved_amount")) if settlement else None,
                "surplus_amount": _number(settlement.get("surplus_amount")) if settlement else None,
                "execution_rate": execution,
                "execution_failure": failure,
                "execution_rate_source": execution_source,
                "execution_source_record_type": source_record_type,
                "source_period": [str(year)],
                "period_type": "annual",
                "quality_status": "observed" if legal_row else "unavailable",
            }
        )
        if amount is not None:
            previous_amount = amount
    return {
        "metric_id": "youthBureauBudget",
        "trend": trend,
        "execution": trend,
        "source_datasets": ["youth_budgets"],
    }


def _roc_year(row: Mapping[str, Any]) -> int | None:
    value = row.get("year_roc") or row.get("budget_year_roc")
    if value is not None:
        try:
            parsed = int(str(value).rstrip("年"))
            return parsed if parsed < 1911 else parsed - 1911
        except (TypeError, ValueError):
            pass
    period = str(row.get("period_start") or "")
    try:
        return int(period[:4]) - 1911
    except (TypeError, ValueError):
        return None


def _period_key(row: Mapping[str, Any]) -> str:
    return str(row.get("period_end") or row.get("period_start") or "")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and abs(number) != float("inf") else None


def _source_record_type(row: Mapping[str, Any]) -> str | None:
    raw_record = row.get("raw_record")
    if isinstance(raw_record, Mapping) and raw_record.get("source_record_type") is not None:
        return str(raw_record["source_record_type"])
    value = row.get("source_record_type")
    return str(value) if value is not None else None


def _int(value: Any) -> int | None:
    try:
        return int(str(value).rstrip("年"))
    except (TypeError, ValueError):
        return None


def _yoy(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / previous * 100


def _execution_denominator(
    legal_amount: float | None,
    legal_row: Mapping[str, Any] | None,
    settlement: Mapping[str, Any] | None,
) -> tuple[float | None, str | None]:
    """Align legal-budget and settlement units before applying the ratio."""

    if legal_amount is None:
        return None, None
    legal_unit = legal_row.get("unit") if legal_row else None
    settlement_unit = settlement.get("unit") if settlement else None
    if legal_unit == "TWD_thousand" and settlement_unit == "TWD":
        return legal_amount * 1000, "legal_budget_thousand_to_twd"
    if legal_unit == settlement_unit or settlement_unit is None:
        return legal_amount, None
    return None, "incompatible_budget_units"


__all__ = [
    "calculate_annual_fertility",
    "calculate_annual_population",
    "calculate_budget_series",
]
