"""Run the local data pipeline: collect, persist raw data, transform, and report quality."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from collectors.birth_nums import fetch_birth_numbers
from collectors.bike_stop import fetch_bike_stops
from collectors.bus_stop import fetch_bus_stops
from collectors.college_major import fetch_college_majors
from collectors.graduate_major import fetch_graduate_majors
from collectors.house_price import fetch_house_prices
from collectors.job_vacancy import fetch_new_taipei_job_vacancies
from collectors.job_vacancy_salary import fetch_job_posted_salaries
from collectors.marriage_nums import fetch_marriage_numbers
from collectors.moving_in import fetch_moving
from collectors.population_collector import fetch_population
from collectors.railway_stop import fetch_railway_stops
from collectors.rental_price import fetch_rental_prices
from collectors.talent_demand import fetch_talent_demand
from collectors.training_nums import fetch_training_numbers
from collectors.vt_course import fetch_vt_courses
from collectors.wage import fetch_wage
from collectors.errors import CollectorNoDataError
from orchestration.contracts import CollectorSpec, ExecutionUnit, PeriodStrategy
from orchestration.retry import collect_with_retry
from orchestration.schedule import build_execution_units
from orchestration.state import (
    SCHEMA_VERSION,
    TRANSFORM_VERSION,
    ResumeAction,
    choose_resume_action,
    find_latest_raw,
)
from transform.geography import DistrictResolver
from transform.io import (
    write_collection_report,
    write_curated,
    write_dataset_index,
    write_period_range_report,
    write_raw,
)
from transform.pipeline import canonicalize_dataset, dataset_requires_resolver, run_transform


LOGGER = logging.getLogger("data_pipeline")


def _collect_college(period: str) -> dict[str, Any]:
    academic_year = period[:3]
    return {
        "overview_records": fetch_college_majors(
            academic_year=academic_year, county="新北市", include_student_detail=False
        ),
        "detail_records": fetch_college_majors(
            academic_year=academic_year, county="新北市", include_student_detail=True
        ),
    }


def _collect_births(period: str) -> Any:
    return fetch_birth_numbers(period[:3], county="新北市")


def _collect_marriages(period: str) -> Any:
    return fetch_marriage_numbers(period[:3], county="新北市")


def _collect_graduate_majors(period: str) -> Any:
    # Dataset 9620 has no county field, so the collector must remain national.
    return fetch_graduate_majors(academic_year=period[:3], county=None)


def _collect_wages(period: str) -> Any:
    return fetch_wage(county="新北市", year=period[:3])


DEFAULT_COLLECTOR_SPECS: tuple[CollectorSpec, ...] = (
    CollectorSpec("population", lambda period: fetch_population(period, county="新北市")),
    CollectorSpec("movement", lambda period: fetch_moving(period, county="新北市")),
    CollectorSpec("births", _collect_births, PeriodStrategy.ANNUAL),
    CollectorSpec("marriages", _collect_marriages, PeriodStrategy.ANNUAL),
    CollectorSpec("house_prices", lambda period: fetch_house_prices(), PeriodStrategy.SNAPSHOT),
    CollectorSpec("rentals", lambda period: fetch_rental_prices(), PeriodStrategy.SNAPSHOT),
    CollectorSpec(
        "job_vacancies", lambda period: fetch_new_taipei_job_vacancies(), PeriodStrategy.SNAPSHOT
    ),
    CollectorSpec(
        "job_vacancy_salaries", lambda period: fetch_job_posted_salaries(), PeriodStrategy.SNAPSHOT
    ),
    CollectorSpec("wages", _collect_wages, PeriodStrategy.ANNUAL),
    CollectorSpec("college_majors", _collect_college, PeriodStrategy.ANNUAL),
    CollectorSpec("graduate_majors", _collect_graduate_majors, PeriodStrategy.ANNUAL),
    CollectorSpec("vt_courses", lambda period: fetch_vt_courses(county="新北市"), PeriodStrategy.SNAPSHOT),
    CollectorSpec(
        "training_numbers", lambda period: fetch_training_numbers(county="新北市"), PeriodStrategy.SNAPSHOT
    ),
    CollectorSpec("talent_demand", lambda period: fetch_talent_demand(), PeriodStrategy.ALL_AVAILABLE),
)


TDX_COLLECTOR_SPECS: tuple[CollectorSpec, ...] = (
    CollectorSpec("bus_stops", lambda period: fetch_bus_stops(), PeriodStrategy.SNAPSHOT),
    CollectorSpec(
        "railway_stops", lambda period: fetch_railway_stops(location_city="新北市"), PeriodStrategy.SNAPSHOT
    ),
    CollectorSpec("bike_stops", lambda period: fetch_bike_stops(), PeriodStrategy.SNAPSHOT),
)


def run_execution_unit(
    unit: ExecutionUnit,
    *,
    output_dir: str | Path,
    config_dir: str | Path,
    strict: bool,
    resume: bool,
    force: bool,
) -> dict[str, Any]:
    """Run one source-aware collection unit with a partitioned output key."""

    return _run_execution_unit(
        unit,
        output_dir=output_dir,
        config_dir=config_dir,
        strict=strict,
        resume=resume,
        force=force,
        period_partitioned=True,
    )


def _run_execution_unit(
    unit: ExecutionUnit,
    *,
    output_dir: str | Path,
    config_dir: str | Path,
    strict: bool,
    resume: bool,
    force: bool,
    period_partitioned: bool,
) -> dict[str, Any]:
    """Execute collection and transform work shared by range and single-month runs."""

    _ = strict
    spec = unit.spec
    output_root = Path(output_dir)
    canonical_hint = _canonical_dataset_or_name(spec.dataset)
    output_path = _curated_output_path(
        output_root,
        canonical_hint,
        unit.output_key if period_partitioned else None,
    )
    raw_path = find_latest_raw(output_root, canonical_hint, unit)
    previous_status = _load_previous_unit_status(
        output_root,
        unit,
        period_partitioned=period_partitioned,
    )
    action = choose_resume_action(
        report=previous_status,
        output_path=output_path,
        raw_path=raw_path,
        resume=resume,
        force=force,
    )
    status: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "status": "running",
        "source_period": unit.source_period,
        "output_key": unit.output_key,
        "period_strategy": spec.period_strategy.value,
        "action": action.value,
        "attempts": 0,
        "downloaded": False,
        "reused_raw": False,
        "reused_output": False,
    }
    collection_attempts = 0
    LOGGER.debug(
        "action dataset=%s action=%s source_period=%s output_key=%s",
        spec.dataset,
        action.value,
        unit.source_period,
        unit.output_key,
    )

    if action is ResumeAction.REUSE_OUTPUT:
        status.update(
            {
                "status": "ok",
                "reused_output": True,
                "curated_path": str(output_path),
            }
        )
        _copy_previous_status_fields(status, previous_status)
        LOGGER.debug(
            "reuse output dataset=%s source_period=%s output_key=%s curated=%s",
            spec.dataset,
            unit.source_period,
            unit.output_key,
            output_path,
        )
        return status

    if action is ResumeAction.KEEP_NO_DATA:
        status.update(
            {
                "status": "skipped",
                "reason": "no_data",
                "source_message": (previous_status or {}).get("source_message", ""),
            }
        )
        LOGGER.debug(
            "collect skipped dataset=%s source_period=%s output_key=%s reason=no_data action=keep_no_data",
            spec.dataset,
            unit.source_period,
            unit.output_key,
        )
        return status

    try:
        if action is ResumeAction.REUSE_RAW:
            canonical_dataset = canonicalize_dataset(spec.dataset)
            if raw_path is None:
                raise FileNotFoundError("selected raw input no longer exists")
            with raw_path.open(encoding="utf-8") as handle:
                raw_payload = json.load(handle)
            transform_input, raw_fetched_at = _payload_records(
                canonical_dataset, raw_payload
            )
            fetched_at = raw_fetched_at or datetime.now(timezone.utc).isoformat()
            status.update({"reused_raw": True, "raw_path": str(raw_path)})
            LOGGER.debug(
                "reuse raw dataset=%s source_period=%s output_key=%s raw=%s",
                spec.dataset,
                unit.source_period,
                unit.output_key,
                raw_path,
            )
        else:
            fetched_at = datetime.now(timezone.utc).isoformat()

            def collect() -> Any:
                nonlocal collection_attempts
                collection_attempts += 1
                return spec.collect(unit.source_period)

            LOGGER.debug(
                "collect start dataset=%s source_period=%s output_key=%s",
                spec.dataset,
                unit.source_period,
                unit.output_key,
            )
            status["downloaded"] = True
            retry_result = collect_with_retry(
                collect,
                on_retry=lambda attempt, exc: LOGGER.debug(
                    "collect retry dataset=%s source_period=%s output_key=%s attempt=%d reason=%s",
                    spec.dataset,
                    unit.source_period,
                    unit.output_key,
                    attempt,
                    exc,
                ),
            )
            status["attempts"] = retry_result.attempts
            canonical_dataset = canonicalize_dataset(spec.dataset)
            raw_payload, transform_input = _raw_and_transform_payload(
                canonical_dataset,
                retry_result.value,
                period=unit.source_period,
                fetched_at=fetched_at,
            )
            LOGGER.debug(
                "collect complete dataset=%s source_period=%s records=%d attempts=%d",
                spec.dataset,
                unit.source_period,
                _record_count(canonical_dataset, transform_input),
                retry_result.attempts,
            )
            raw_path = write_raw(
                raw_payload,
                dataset=canonical_dataset,
                snapshot=_snapshot_name(unit.source_period, fetched_at),
                output_dir=output_root,
            )
            status["raw_path"] = str(raw_path)

        if not _has_records(canonical_dataset, transform_input):
            status.update(
                {
                    "status": "skipped",
                    "reason": "no_data",
                    "source_message": "collector or reusable raw returned no records",
                }
            )
            LOGGER.debug(
                "collect skipped dataset=%s source_period=%s output_key=%s reason=no_data raw=%s",
                spec.dataset,
                unit.source_period,
                unit.output_key,
                raw_path,
            )
            return status
        resolver = _load_resolver_if_needed((spec,), config_dir)
        result = run_transform(
            canonical_dataset,
            transform_input,
            resolver=resolver,
            fetched_at=fetched_at,
        )
        curated_path, quality_path, quarantine_path = write_curated(
            result,
            dataset=canonical_dataset,
            output_dir=output_root,
            period=unit.output_key if period_partitioned else None,
        )
        status.update(
            {
                "status": "ok",
                "raw_path": str(raw_path),
                "curated_path": str(curated_path),
                "quality_path": str(quality_path),
                "quarantine_path": str(quarantine_path),
                "rows_in": result.quality["rows_in"],
                "rows_out": result.quality["rows_out"],
                "rows_rejected": result.quality["rows_rejected"],
            }
        )
        LOGGER.debug(
            "transform complete dataset=%s source_period=%s output_key=%s rows_in=%d rows_out=%d rows_rejected=%d",
            spec.dataset,
            unit.source_period,
            unit.output_key,
            result.quality["rows_in"],
            result.quality["rows_out"],
            result.quality["rows_rejected"],
        )
        LOGGER.debug(
            "output complete dataset=%s source_period=%s output_key=%s curated=%s quality=%s quarantine=%s",
            spec.dataset,
            unit.source_period,
            unit.output_key,
            curated_path,
            quality_path,
            quarantine_path,
        )
    except CollectorNoDataError as exc:
        status.update(
            {
                "status": "skipped",
                "reason": "no_data",
                "source_message": str(exc),
                "attempts": collection_attempts,
            }
        )
        LOGGER.debug(
            "collect skipped dataset=%s source_period=%s output_key=%s reason=no_data message=%s",
            spec.dataset,
            unit.source_period,
            unit.output_key,
            exc,
        )
    except Exception as exc:  # one unavailable source must not drop all data
        status.update(
            {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "attempts": collection_attempts,
            }
        )
        LOGGER.debug(
            "pipeline error dataset=%s source_period=%s output_key=%s error=%s",
            spec.dataset,
            unit.source_period,
            unit.output_key,
            status["error"],
        )
    return status


def run_full_pipeline(
    period: str,
    *,
    output_dir: str | Path,
    config_dir: str | Path,
    include_tdx: bool = False,
    strict: bool = False,
    collector_specs: Sequence[CollectorSpec] | None = None,
    period_partitioned: bool = False,
    resume: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Compatibility wrapper for a single local ROC month execution."""

    _validate_period(period)
    specs = tuple(DEFAULT_COLLECTOR_SPECS if collector_specs is None else collector_specs)
    if include_tdx and collector_specs is None:
        specs += TDX_COLLECTOR_SPECS

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "period": period,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "strict": strict,
        "resume": resume,
        "force": force,
        "datasets": {},
    }
    units: list[ExecutionUnit] = []
    unit_statuses: list[dict[str, Any]] = []
    total_units = len(specs)
    for index, spec in enumerate(specs, start=1):
        unit = ExecutionUnit(spec, source_period=period, output_key=period)
        _log_unit_start(index, total_units, unit)
        status = _run_execution_unit(
            unit,
            output_dir=output_dir,
            config_dir=config_dir,
            strict=strict,
            resume=resume,
            force=force,
            period_partitioned=period_partitioned,
        )
        _log_unit_result(index, total_units, spec.dataset, status)
        report["datasets"][spec.dataset] = status
        units.append(unit)
        unit_statuses.append(status)

    report["errors"] = {
        dataset: details["error"]
        for dataset, details in report["datasets"].items()
        if details["status"] == "error"
    }
    report["status"] = "error" if report["errors"] and strict else "ok"
    report["dataset_index_path"] = str(
        _write_authoritative_index(units, unit_statuses, output_dir=output_dir)
    )
    write_collection_report(
        report,
        output_dir=output_dir,
        period=period if period_partitioned else None,
    )
    _log_summary(unit_statuses)
    return report


def run_period_range(
    start_period: str,
    end_period: str,
    *,
    output_dir: str | Path,
    config_dir: str | Path,
    include_tdx: bool = False,
    strict: bool = False,
    collector_specs: Sequence[CollectorSpec] | None = None,
    resume: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Run each collector at the cadence supported by its source."""

    periods = list(_iter_periods(start_period, end_period))
    specs = tuple(DEFAULT_COLLECTOR_SPECS if collector_specs is None else collector_specs)
    if include_tdx and collector_specs is None:
        specs += TDX_COLLECTOR_SPECS
    units = build_execution_units(specs, start_period, end_period)
    unit_statuses: list[dict[str, Any]] = []
    total_units = len(units)
    for index, unit in enumerate(units, start=1):
        _log_unit_start(index, total_units, unit)
        status = run_execution_unit(
            unit,
            output_dir=output_dir,
            config_dir=config_dir,
            strict=strict,
            resume=resume,
            force=force,
        )
        _log_unit_result(index, total_units, unit.spec.dataset, status)
        unit_statuses.append(status)
    period_reports = [
        {
            "schema_version": SCHEMA_VERSION,
            "transform_version": TRANSFORM_VERSION,
            "period": period,
            "strict": strict,
            "datasets": {},
        }
        for period in periods
    ]
    reports_by_period = {report["period"]: report for report in period_reports}
    for unit, status in zip(units, unit_statuses, strict=True):
        period_report = reports_by_period.get(unit.output_key)
        if period_report is not None:
            period_report["datasets"][unit.spec.dataset] = status
    for period_report in period_reports:
        period_report["errors"] = {
            dataset: details["error"]
            for dataset, details in period_report["datasets"].items()
            if details["status"] == "error"
        }
        period_report["status"] = (
            "error" if period_report["errors"] and strict else "ok"
        )
    has_errors = any(status["status"] == "error" for status in unit_statuses)
    index_path = _write_authoritative_index(
        units, unit_statuses, output_dir=output_dir
    )
    range_report = {
        "schema_version": SCHEMA_VERSION,
        "transform_version": TRANSFORM_VERSION,
        "start_period": start_period,
        "end_period": end_period,
        "resume": resume,
        "force": force,
        "periods": periods,
        "period_reports": period_reports,
        "execution_units": [
            {
                "dataset": unit.spec.dataset,
                "source_period": unit.source_period,
                "output_key": unit.output_key,
                **status,
            }
            for unit, status in zip(units, unit_statuses, strict=True)
        ],
        "dataset_index_path": str(index_path),
        "status": "error" if has_errors and strict else "ok",
    }
    write_period_range_report(range_report, output_dir=output_dir)
    _log_summary(unit_statuses)
    return range_report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", help="Dataset name for local raw replay mode")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--input", help="Previously saved raw JSON file")
    mode.add_argument("--period", help="ROC month, for example 11507, in full pipeline mode")
    mode.add_argument("--start-period", help="First ROC month for inclusive range mode")
    parser.add_argument("--end-period", help="Last ROC month for inclusive range mode")
    parser.add_argument("--output-dir", default=str(Path(__file__).resolve().parents[1] / "data"))
    parser.add_argument("--config-dir", default=str(Path(__file__).resolve().parents[1] / "config"))
    parser.add_argument("--include-tdx", action="store_true", help="Also collect TDX transport datasets")
    parser.add_argument("--strict", action="store_true", help="Return non-zero if any collector fails")
    recovery = parser.add_mutually_exclusive_group()
    recovery.add_argument(
        "--resume", action="store_true", help="Reuse current outputs or matching raw data"
    )
    recovery.add_argument(
        "--force", action="store_true", help="Download every scheduled execution unit"
    )
    args = parser.parse_args(argv)
    _configure_terminal_logging()

    if args.input:
        if not args.dataset:
            parser.error("--dataset is required with --input")
        return _run_replay(
            dataset=args.dataset,
            input_path=Path(args.input),
            output_dir=args.output_dir,
            config_dir=args.config_dir,
        )
    if args.start_period and not args.end_period:
        parser.error("--end-period is required with --start-period")
    if args.end_period and not args.start_period:
        parser.error("--start-period is required with --end-period")
    if args.start_period:
        report = run_period_range(
            args.start_period,
            args.end_period,
            output_dir=args.output_dir,
            config_dir=args.config_dir,
            include_tdx=args.include_tdx,
            strict=args.strict,
            resume=args.resume,
            force=args.force,
        )
        return 1 if report["status"] == "error" else 0
    if not args.period:
        parser.error("choose either --input with --dataset or --period")

    report = run_full_pipeline(
        args.period,
        output_dir=args.output_dir,
        config_dir=args.config_dir,
        include_tdx=args.include_tdx,
        strict=args.strict,
        resume=args.resume,
        force=args.force,
    )
    return 1 if report["status"] == "error" else 0


def _run_replay(
    *, dataset: str, input_path: Path, output_dir: str | Path, config_dir: str | Path
) -> int:
    with input_path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    canonical_dataset = canonicalize_dataset(dataset)
    records, fetched_at = _payload_records(dataset, payload)
    resolver = (
        DistrictResolver.from_json(Path(config_dir) / "districts.json")
        if dataset_requires_resolver(canonical_dataset)
        else None
    )
    result = run_transform(canonical_dataset, records, resolver=resolver, fetched_at=fetched_at)
    write_curated(result, dataset=canonical_dataset, output_dir=output_dir)
    return 0


def _canonical_dataset_or_name(dataset: str) -> str:
    try:
        return canonicalize_dataset(dataset)
    except ValueError:
        return dataset


def _curated_output_path(
    output_dir: Path, dataset: str, output_key: str | None
) -> Path:
    if output_key is None:
        return output_dir / "curated" / f"{dataset}.json"
    return output_dir / "curated" / dataset / f"{output_key}.json"


def _load_previous_unit_status(
    output_dir: Path,
    unit: ExecutionUnit,
    *,
    period_partitioned: bool,
) -> dict[str, Any] | None:
    report_path = output_dir / "quality" / "collection.json"
    if period_partitioned:
        report_path = output_dir / "quality" / "collection_range.json"
    report = _read_json_mapping(report_path)
    if report is None:
        return None

    previous: Mapping[str, Any] | None = None
    if period_partitioned:
        execution_units = report.get("execution_units")
        if isinstance(execution_units, list):
            previous = next(
                (
                    entry
                    for entry in execution_units
                    if isinstance(entry, Mapping)
                    and entry.get("dataset") == unit.spec.dataset
                    and entry.get("output_key") == unit.output_key
                ),
                None,
            )
        if previous is None:
            previous = _legacy_period_status(report, unit)
    else:
        datasets = report.get("datasets")
        if isinstance(datasets, Mapping):
            candidate = datasets.get(unit.spec.dataset)
            if (
                isinstance(candidate, Mapping)
                and candidate.get("source_period") == unit.source_period
                and candidate.get("output_key") == unit.output_key
            ):
                previous = candidate

    if previous is None:
        return None
    merged = dict(previous)
    for key in ("schema_version", "transform_version"):
        if key not in merged and key in report:
            merged[key] = report[key]
    return merged


def _legacy_period_status(
    report: Mapping[str, Any], unit: ExecutionUnit
) -> Mapping[str, Any] | None:
    period_reports = report.get("period_reports")
    if not isinstance(period_reports, list):
        return None

    for period_report in reversed(period_reports):
        if not isinstance(period_report, Mapping):
            continue
        period = period_report.get("period")
        if unit.spec.period_strategy is PeriodStrategy.MONTHLY:
            matches = period == unit.output_key
        elif unit.spec.period_strategy is PeriodStrategy.ANNUAL:
            matches = isinstance(period, str) and period.startswith(unit.output_key)
        else:
            matches = True
        if not matches:
            continue
        datasets = period_report.get("datasets")
        if not isinstance(datasets, Mapping):
            continue
        candidate = datasets.get(unit.spec.dataset)
        if isinstance(candidate, Mapping):
            return candidate
    return None


def _read_json_mapping(path: Path) -> Mapping[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _copy_previous_status_fields(
    status: dict[str, Any], previous: Mapping[str, Any] | None
) -> None:
    if previous is None:
        return
    for key in (
        "raw_path",
        "quality_path",
        "quarantine_path",
        "rows_in",
        "rows_out",
        "rows_rejected",
        "source_message",
    ):
        if key in previous:
            status[key] = previous[key]


def _write_authoritative_index(
    units: Sequence[ExecutionUnit],
    statuses: Sequence[Mapping[str, Any]],
    *,
    output_dir: str | Path,
) -> Path:
    output_root = Path(output_dir)
    entries: list[dict[str, Any]] = []
    for unit, status in zip(units, statuses, strict=True):
        if status.get("status") != "ok":
            continue
        curated_value = status.get("curated_path")
        if not isinstance(curated_value, str):
            continue
        curated_path = Path(curated_value)
        if not curated_path.is_file():
            continue
        try:
            relative_path = curated_path.resolve().relative_to(output_root.resolve())
        except ValueError:
            continue
        entries.append(
            {
                "dataset": _canonical_dataset_or_name(unit.spec.dataset),
                "output_key": unit.output_key,
                "path": relative_path.as_posix(),
                "period_strategy": unit.spec.period_strategy.value,
                "source_period": unit.source_period,
                "transform_version": TRANSFORM_VERSION,
            }
        )
    return write_dataset_index(entries, output_dir=output_root)


def _raw_and_transform_payload(
    dataset: str, collected: Any, *, period: str, fetched_at: str
) -> tuple[dict[str, Any], Any]:
    if dataset == "college_majors":
        if not isinstance(collected, Mapping):
            raise TypeError("college_majors collector must return an envelope")
        overview = collected.get("overview_records", [])
        detail = collected.get("detail_records", [])
        payload = {
            "dataset": dataset,
            "period": period,
            "fetched_at": fetched_at,
            "overview_records": overview,
            "detail_records": detail,
        }
        return payload, {"overview_records": overview, "detail_records": detail}

    if dataset == "wages":
        if not isinstance(collected, Mapping):
            raise TypeError("wages collector must return an envelope")
        payload = dict(collected)
        metadata = dict(payload.get("metadata") or {})
        metadata.setdefault("fetched_at", fetched_at)
        payload["dataset"] = dataset
        payload["period"] = period
        payload["metadata"] = metadata
        return payload, payload

    records = collected.get("records") if isinstance(collected, Mapping) else collected
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError(f"{dataset} collector must return a records array")
    payload = {
        "dataset": dataset,
        "period": period,
        "fetched_at": fetched_at,
        "records": list(records),
    }
    return payload, payload["records"]


def _has_records(dataset: str, transform_input: Any) -> bool:
    if dataset == "college_majors":
        return bool(
            transform_input.get("overview_records")
            or transform_input.get("detail_records")
        )
    if dataset == "wages" and isinstance(transform_input, Mapping):
        return bool(transform_input.get("records"))
    return bool(transform_input)


def _record_count(dataset: str, transform_input: Any) -> int:
    if dataset == "college_majors":
        return len(transform_input.get("overview_records", [])) + len(transform_input.get("detail_records", []))
    if dataset == "wages" and isinstance(transform_input, Mapping):
        return len(transform_input.get("records", []))
    return len(transform_input)


def _log_unit_start(index: int, total: int, unit: ExecutionUnit) -> None:
    LOGGER.info(
        "[%d/%d] 正在處理 %s（期間 %s）",
        index,
        total,
        unit.spec.dataset,
        unit.source_period,
    )


def _log_unit_result(
    index: int,
    total: int,
    dataset: str,
    status: Mapping[str, Any],
) -> None:
    prefix = f"[{index}/{total}]"
    if status["status"] == "ok":
        rows_in = status.get("rows_in")
        rows_out = status.get("rows_out")
        if rows_in is not None and rows_out is not None:
            LOGGER.info(
                "%s ✓ %s 完成：%s → %s 筆",
                prefix,
                dataset,
                rows_in,
                rows_out,
            )
        else:
            LOGGER.info("%s ✓ %s 完成", prefix, dataset)
        return
    if status["status"] == "skipped":
        LOGGER.info("%s - %s 無資料，已跳過", prefix, dataset)
        return
    LOGGER.error("%s ✗ %s 失敗：%s", prefix, dataset, status.get("error", "未知錯誤"))


def _log_summary(statuses: Sequence[Mapping[str, Any]]) -> None:
    success_count = sum(status["status"] == "ok" for status in statuses)
    skipped_count = sum(status["status"] == "skipped" for status in statuses)
    error_count = sum(status["status"] == "error" for status in statuses)
    LOGGER.info(
        "全部完成：成功 %d、無資料 %d、失敗 %d",
        success_count,
        skipped_count,
        error_count,
    )


def _configure_terminal_logging() -> None:
    for handler in LOGGER.handlers[:]:
        LOGGER.removeHandler(handler)
        handler.close()
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    LOGGER.addHandler(handler)


def _load_resolver_if_needed(
    specs: Sequence[CollectorSpec], config_dir: str | Path
) -> DistrictResolver | None:
    for spec in specs:
        try:
            if dataset_requires_resolver(spec.dataset):
                return DistrictResolver.from_json(Path(config_dir) / "districts.json")
        except ValueError:
            continue
    return None


def _payload_records(dataset: str, payload: Any) -> tuple[Any, str | None]:
    if dataset in {"college_majors", "college_major", "wages", "wage"}:
        if not isinstance(payload, Mapping):
            raise TypeError(f"{dataset} input must be a JSON object envelope")
        metadata = payload.get("metadata")
        fetched_at = metadata.get("fetched_at") if isinstance(metadata, Mapping) else payload.get("fetched_at")
        return payload, fetched_at
    if isinstance(payload, list):
        return payload, None
    if not isinstance(payload, Mapping):
        raise TypeError("raw input must be a JSON array or object envelope")
    records = payload.get("records")
    if not isinstance(records, list):
        raise TypeError("raw input envelope must contain a records array")
    metadata = payload.get("metadata")
    fetched_at = metadata.get("fetched_at") if isinstance(metadata, Mapping) else payload.get("fetched_at")
    return records, fetched_at


def _snapshot_name(period: str, fetched_at: str) -> str:
    timestamp = fetched_at.replace("+00:00", "Z").replace("-", "").replace(":", "").replace(".", "")
    return f"{period}_{timestamp}"


def _validate_period(period: str) -> None:
    if not isinstance(period, str) or len(period) != 5 or not period.isdigit():
        raise ValueError("period must be a five-digit ROC month such as 11507")


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


if __name__ == "__main__":
    raise SystemExit(main())
