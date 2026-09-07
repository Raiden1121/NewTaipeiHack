"""Choose recovery actions and locate reusable raw pipeline inputs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .contracts import ExecutionUnit, PeriodStrategy


SCHEMA_VERSION = 2
TRANSFORM_VERSION = "2026-09-02.1"
_RAW_FETCH_TIMESTAMP = re.compile(
    r"^(?P<seconds>\d{8}T\d{6})(?P<microseconds>\d{6})?Z$"
)


class ResumeAction(str, Enum):
    REUSE_OUTPUT = "reuse_output"
    REUSE_RAW = "reuse_raw"
    DOWNLOAD = "download"
    KEEP_NO_DATA = "keep_no_data"


def choose_resume_action(
    *,
    report: Mapping[str, Any] | None,
    output_path: Path,
    raw_path: Path | None,
    resume: bool,
    force: bool,
) -> ResumeAction:
    """Choose the next action without mutating existing pipeline files."""

    if force or not resume:
        return ResumeAction.DOWNLOAD

    previous = report or {}
    if (
        previous.get("status") == "ok"
        and previous.get("schema_version") == SCHEMA_VERSION
        and previous.get("transform_version") == TRANSFORM_VERSION
        and output_path.is_file()
    ):
        return ResumeAction.REUSE_OUTPUT

    no_data = (
        previous.get("status") == "skipped"
        and previous.get("reason") == "no_data"
    )
    if not no_data and raw_path is not None and raw_path.is_file():
        return ResumeAction.REUSE_RAW
    if no_data:
        return ResumeAction.KEEP_NO_DATA
    return ResumeAction.DOWNLOAD


def find_latest_raw(
    output_dir: str | Path, dataset: str, unit: ExecutionUnit
) -> Path | None:
    """Return the newest reusable raw file matching an execution unit."""

    raw_dir = Path(output_dir) / "raw" / dataset
    if not raw_dir.is_dir():
        return None

    candidates = [path for path in raw_dir.glob("*.json") if path.is_file()]
    if unit.spec.period_strategy is PeriodStrategy.MONTHLY:
        period_pattern = re.compile(rf"^{re.escape(unit.source_period)}(?:_|$)")
        candidates = [path for path in candidates if period_pattern.match(path.stem)]
    elif unit.spec.period_strategy is PeriodStrategy.ANNUAL:
        year = unit.output_key
        period_pattern = re.compile(rf"^{re.escape(year)}\d{{2}}(?:_|$)")
        candidates = [path for path in candidates if period_pattern.match(path.stem)]

    if not candidates:
        return None
    return max(candidates, key=_raw_recency_key)


def _raw_recency_key(path: Path) -> tuple[int, str]:
    fetched_at_ns = _validated_fetch_timestamp_ns(path)
    return (
        fetched_at_ns if fetched_at_ns is not None else path.stat().st_mtime_ns,
        path.name,
    )


def _validated_fetch_timestamp_ns(path: Path) -> int | None:
    parts = path.stem.split("_", 1)
    if len(parts) != 2:
        return None
    match = _RAW_FETCH_TIMESTAMP.fullmatch(parts[1])
    if match is None:
        return None
    try:
        fetched_at = datetime.strptime(
            match.group("seconds"), "%Y%m%dT%H%M%S"
        ).replace(
            microsecond=int(match.group("microseconds") or 0),
            tzinfo=timezone.utc,
        )
    except ValueError:
        return None
    return int(fetched_at.timestamp()) * 1_000_000_000 + fetched_at.microsecond * 1_000
