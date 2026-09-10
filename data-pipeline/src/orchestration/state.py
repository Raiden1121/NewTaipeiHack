"""Choose recovery actions and locate reusable raw pipeline inputs."""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from .contracts import ExecutionUnit, PeriodStrategy


SCHEMA_VERSION = 2
TRANSFORM_VERSION = "2026-09-10.1"
REFRESH_STATE_SCHEMA_VERSION = 1
_REFRESH_PROFILE_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(days=7),
}
_RAW_FETCH_TIMESTAMP = re.compile(
    r"^(?P<seconds>\d{8}T\d{6})(?P<microseconds>\d{6})?Z$"
)


class ResumeAction(str, Enum):
    REUSE_OUTPUT = "reuse_output"
    REUSE_RAW = "reuse_raw"
    DOWNLOAD = "download"
    KEEP_NO_DATA = "keep_no_data"


def load_refresh_state(output_dir: str | Path) -> dict[str, Any]:
    """Load refresh state, returning an empty versioned state when absent."""

    path = _refresh_state_path(output_dir)
    if not path.is_file():
        return _empty_refresh_state()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid refresh state JSON: {exc}") from exc
    _validate_refresh_state(payload)
    return payload


def write_refresh_state(
    state: Mapping[str, Any], output_dir: str | Path
) -> Path:
    """Atomically persist versioned refresh state under the quality directory."""

    payload = dict(state)
    payload.setdefault("schema_version", REFRESH_STATE_SCHEMA_VERSION)
    _validate_refresh_state(payload)
    path = _refresh_state_path(output_dir)
    _atomic_json_write(path, payload)
    return path


def refresh_state_key(unit: ExecutionUnit) -> str:
    """Return the stable state key for a dataset and output partition."""

    return f"{unit.spec.dataset}:{unit.output_key}"


def is_refresh_due(
    entry: Mapping[str, Any] | None,
    *,
    now: datetime,
    profile: str,
    failed_only: bool = False,
) -> bool:
    """Return whether a refresh state entry should be collected now."""

    if profile not in (*_REFRESH_PROFILE_INTERVALS, "monthly"):
        raise ValueError(f"unknown refresh profile: {profile}")

    if failed_only:
        return entry is not None and entry.get("status") == "error"
    if entry is None:
        return True

    checked_at = _entry_datetime(entry)
    if checked_at is None:
        return True

    current = _as_utc(now)
    if profile == "monthly":
        return (checked_at.year, checked_at.month) != (
            current.year,
            current.month,
        )
    return current - checked_at >= _REFRESH_PROFILE_INTERVALS[profile]


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


def _refresh_state_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / "quality" / "refresh_state.json"


def _empty_refresh_state() -> dict[str, Any]:
    return {
        "schema_version": REFRESH_STATE_SCHEMA_VERSION,
        "units": {},
    }


def _validate_refresh_state(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise ValueError("refresh state must be a JSON object")
    if payload.get("schema_version") != REFRESH_STATE_SCHEMA_VERSION:
        raise ValueError(
            "refresh state must contain schema_version 1"
        )
    if not isinstance(payload.get("units"), dict):
        raise ValueError("refresh state must contain a units object")


def _entry_datetime(entry: Mapping[str, Any]) -> datetime | None:
    for field in ("last_checked_at", "last_success_at", "last_started_at"):
        value = entry.get(field)
        if not isinstance(value, str):
            continue
        try:
            return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
