"""Plan collector executions from their source period strategies."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .contracts import CollectorSpec, ExecutionUnit, PeriodStrategy


def current_roc_period(now: datetime) -> str:
    """Return the current Gregorian datetime as a five-digit ROC month."""

    return f"{now.year - 1911:03d}{now.month:02d}"


def build_current_execution_units(
    specs: Iterable[CollectorSpec], now: datetime
) -> list[ExecutionUnit]:
    """Build source-aware execution units for the current ROC month."""

    period = current_roc_period(now)
    return build_execution_units(specs, period, period)


def build_execution_units(
    specs: Iterable[CollectorSpec], start_period: str, end_period: str
) -> list[ExecutionUnit]:
    """Build ordered collection units for an inclusive ROC month range."""

    periods = list(_iter_periods(start_period, end_period))
    units: list[ExecutionUnit] = []
    for spec in specs:
        if spec.period_strategy is PeriodStrategy.MONTHLY:
            units.extend(
                ExecutionUnit(spec, source_period=period, output_key=period)
                for period in periods
            )
            continue
        if spec.period_strategy is PeriodStrategy.ANNUAL:
            years = dict.fromkeys(period[:3] for period in periods)
            units.extend(
                ExecutionUnit(spec, source_period=f"{year}01", output_key=year)
                for year in years
            )
            continue
        if spec.period_strategy is PeriodStrategy.SNAPSHOT:
            units.append(ExecutionUnit(spec, source_period=end_period, output_key="latest"))
            continue
        if spec.period_strategy is PeriodStrategy.ALL_AVAILABLE:
            units.append(ExecutionUnit(spec, source_period=end_period, output_key="all"))
            continue
        raise ValueError(f"unsupported period strategy: {spec.period_strategy!r}")
    return units


def _iter_periods(start_period: str, end_period: str):
    _validate_period(start_period)
    _validate_period(end_period)
    start_year, start_month = int(start_period[:3]), int(start_period[3:])
    end_year, end_month = int(end_period[:3]), int(end_period[3:])
    if start_month < 1 or start_month > 12 or end_month < 1 or end_month > 12:
        raise ValueError("period month must be between 01 and 12")
    start_index = start_year * 12 + start_month - 1
    end_index = end_year * 12 + end_month - 1
    if start_index > end_index:
        raise ValueError("start_period must not be later than end_period")
    for index in range(start_index, end_index + 1):
        year, month = divmod(index, 12)
        yield f"{year:03d}{month + 1:02d}"


def _validate_period(period: str) -> None:
    if not isinstance(period, str) or len(period) != 5 or not period.isdigit():
        raise ValueError("period must be a five-digit ROC month such as 11507")
