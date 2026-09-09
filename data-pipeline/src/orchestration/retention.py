"""Rolling retention policy and local JSON cleanup operations."""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .contracts import PeriodStrategy


_PERIOD_RE = re.compile(r"^(?P<year>\d{3})(?P<month>\d{2})$")
_ROC_YEAR_RE = re.compile(r"^(?P<year>\d{3})")


@dataclass(frozen=True)
class RetentionWindow:
    """The inclusive period bounds for a rolling retention window."""

    current_period: str
    years: int
    monthly_cutoff: str
    annual_cutoff: int


def build_retention_window(current_period: str, years: int = 5) -> RetentionWindow:
    """Build an inclusive rolling window from a ROC month."""

    year, month = _parse_month_period(current_period)
    if years <= 0:
        raise ValueError("retention years must be positive")
    current_index = year * 12 + month - 1
    cutoff_index = current_index - (years * 12) + 1
    cutoff_year, cutoff_month_index = divmod(cutoff_index, 12)
    return RetentionWindow(
        current_period=current_period,
        years=years,
        monthly_cutoff=f"{cutoff_year:03d}{cutoff_month_index + 1:02d}",
        annual_cutoff=year - years + 1,
    )


def period_is_retained(
    period: str,
    strategy: PeriodStrategy,
    window: RetentionWindow,
) -> bool:
    """Return whether a partition key is inside the retention window."""

    if strategy is PeriodStrategy.MONTHLY:
        _parse_month_period(period)
        return period >= window.monthly_cutoff
    if strategy is PeriodStrategy.ANNUAL:
        year = _parse_roc_year(period)
        return year >= window.annual_cutoff
    if strategy in (PeriodStrategy.SNAPSHOT, PeriodStrategy.ALL_AVAILABLE):
        return True
    raise ValueError(f"unsupported retention strategy: {strategy!r}")


def prune_local_data(
    output_dir: str | Path,
    *,
    current_period: str,
    period_strategies: Mapping[str, PeriodStrategy],
    retention_years: int = 5,
) -> dict[str, Any]:
    """Prune local pipeline outputs while preserving unknown-period data.

    The retention policy is deliberately independent from a storage provider.
    This function is the local JSON operation; a future S3 implementation can
    use the same :class:`RetentionWindow` and period helpers.
    """

    root = Path(output_dir)
    window = build_retention_window(current_period, years=retention_years)
    deleted_paths: list[str] = []
    rewritten_paths: list[str] = []
    deleted_artifact_candidates: set[Path] = set()

    for category in ("curated", "quality", "quarantine"):
        for dataset, strategy in period_strategies.items():
            if strategy not in (PeriodStrategy.MONTHLY, PeriodStrategy.ANNUAL):
                continue
            directory = root / category / dataset
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                if _partition_is_stale(path.stem, strategy, window):
                    _delete_file(path, root, deleted_paths)

    collection_directory = root / "quality" / "collection"
    if collection_directory.is_dir():
        for path in sorted(collection_directory.glob("*.json")):
            if _partition_is_stale(path.stem, PeriodStrategy.MONTHLY, window):
                _delete_file(path, root, deleted_paths)

    for dataset, strategy in period_strategies.items():
        raw_directory = root / "raw" / dataset
        if not raw_directory.is_dir():
            continue
        for path in sorted(raw_directory.glob("*.json")):
            payload = _read_json(path)
            if payload is None:
                continue
            artifact_paths = _artifact_paths(payload, root)
            if strategy in (PeriodStrategy.MONTHLY, PeriodStrategy.ANNUAL):
                source_period = payload.get("period")
                if isinstance(source_period, str) and _partition_is_stale(
                    source_period, strategy, window
                ):
                    deleted_artifact_candidates.update(artifact_paths)
                    _delete_file(path, root, deleted_paths)
                continue
            if _raw_snapshot_is_stale(payload, window):
                deleted_artifact_candidates.update(artifact_paths)
                _delete_file(path, root, deleted_paths)
                continue
            if strategy is PeriodStrategy.ALL_AVAILABLE:
                filtered, changed = _filter_all_available_payload(payload, window)
                if changed:
                    _atomic_json_write(path, filtered)
                    rewritten_paths.append(_relative_path(path, root))

    _prune_all_available_curated(
        root,
        period_strategies,
        window,
        rewritten_paths,
    )
    _prune_orphaned_artifacts(
        root,
        deleted_artifact_candidates,
        deleted_paths,
    )
    _prune_dataset_index(
        root,
        period_strategies,
        window,
        deleted_paths,
        rewritten_paths,
    )

    return {
        "status": "ok",
        "retention_years": retention_years,
        "current_period": current_period,
        "monthly_cutoff": window.monthly_cutoff,
        "annual_cutoff": str(window.annual_cutoff),
        "deleted_paths": sorted(set(deleted_paths)),
        "rewritten_paths": sorted(set(rewritten_paths)),
        "deleted_count": len(set(deleted_paths)),
        "rewritten_count": len(set(rewritten_paths)),
    }


def _parse_month_period(period: str) -> tuple[int, int]:
    if not isinstance(period, str):
        raise ValueError("ROC month must be a five-digit string")
    match = _PERIOD_RE.fullmatch(period)
    if match is None:
        raise ValueError("ROC month must be a five-digit string")
    month = int(match.group("month"))
    if not 1 <= month <= 12:
        raise ValueError("ROC month must be between 01 and 12")
    return int(match.group("year")), month


def _parse_roc_year(value: str | int) -> int:
    text = str(value).strip()
    match = _ROC_YEAR_RE.match(text)
    if match is None:
        raise ValueError(f"invalid ROC year: {value!r}")
    return int(match.group("year"))


def _partition_is_stale(
    partition: str,
    strategy: PeriodStrategy,
    window: RetentionWindow,
) -> bool:
    try:
        return not period_is_retained(partition, strategy, window)
    except ValueError:
        return False


def _read_json(path: Path) -> Mapping[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _delete_file(path: Path, root: Path, deleted_paths: list[str]) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    deleted_paths.append(_relative_path(path, root))


def _relative_path(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _raw_snapshot_is_stale(payload: Mapping[str, Any], window: RetentionWindow) -> bool:
    fetched_at = payload.get("fetched_at")
    if not isinstance(fetched_at, str):
        return False
    try:
        fetched = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        cutoff_year, cutoff_month = _parse_month_period(window.monthly_cutoff)
        cutoff = datetime(cutoff_year + 1911, cutoff_month, 1, tzinfo=fetched.tzinfo)
    except (TypeError, ValueError):
        return False
    return fetched < cutoff


def _artifact_paths(payload: Mapping[str, Any], root: Path) -> set[Path]:
    values = payload.get("source_artifacts")
    if not isinstance(values, list):
        return set()
    paths: set[Path] = set()
    for value in values:
        if not isinstance(value, Mapping) or not isinstance(value.get("path"), str):
            continue
        candidate = root / value["path"]
        try:
            candidate.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        paths.add(candidate)
    return paths


def _filter_all_available_payload(
    payload: Mapping[str, Any], window: RetentionWindow
) -> tuple[dict[str, Any], bool]:
    filtered = dict(payload)
    changed = False
    for field in ("records", "documents"):
        values = payload.get(field)
        if not isinstance(values, list):
            continue
        kept = [value for value in values if _record_is_retained(value, window)]
        if len(kept) != len(values):
            filtered[field] = kept
            changed = True
    return filtered, changed


def _record_is_retained(value: Any, window: RetentionWindow) -> bool:
    if not isinstance(value, Mapping):
        return True
    parsed = _record_period(value)
    if parsed is None:
        return True
    period, strategy = parsed
    return period_is_retained(period, strategy, window)


def _record_period(value: Mapping[str, Any]) -> tuple[str, PeriodStrategy] | None:
    period_type = value.get("period_type")
    for key in ("budget_year_roc", "roc_year", "academic_year", "統計期", "學年度"):
        if key in value:
            try:
                return str(_parse_roc_year(value[key])), PeriodStrategy.ANNUAL
            except ValueError:
                pass

    period = value.get("period") or value.get("source_period")
    if isinstance(period, str):
        if _PERIOD_RE.fullmatch(period):
            return period, PeriodStrategy.MONTHLY
        if _ROC_YEAR_RE.match(period):
            try:
                return str(_parse_roc_year(period)), PeriodStrategy.ANNUAL
            except ValueError:
                pass

    period_start = value.get("period_start")
    if isinstance(period_start, str):
        try:
            parsed_date = datetime.fromisoformat(period_start[:10])
            period = f"{parsed_date.year - 1911:03d}{parsed_date.month:02d}"
            strategy = (
                PeriodStrategy.ANNUAL
                if period_type == "year"
                else PeriodStrategy.MONTHLY
            )
            return (
                str(parsed_date.year - 1911) if strategy is PeriodStrategy.ANNUAL else period,
                strategy,
            )
        except ValueError:
            pass

    nested = value.get("raw_record")
    if isinstance(nested, Mapping) and nested is not value:
        return _record_period(nested)
    return None


def _prune_all_available_curated(
    root: Path,
    period_strategies: Mapping[str, PeriodStrategy],
    window: RetentionWindow,
    rewritten_paths: list[str],
) -> None:
    for dataset, strategy in period_strategies.items():
        if strategy is not PeriodStrategy.ALL_AVAILABLE:
            continue
        path = root / "curated" / dataset / "all.json"
        payload = _read_json(path)
        if payload is None:
            continue
        filtered, changed = _filter_all_available_payload(payload, window)
        if changed:
            _atomic_json_write(path, filtered)
            rewritten_paths.append(_relative_path(path, root))


def _prune_orphaned_artifacts(
    root: Path,
    candidates: set[Path],
    deleted_paths: list[str],
) -> None:
    if not candidates:
        return
    referenced: set[Path] = set()
    for path in (root / "raw").glob("*/*.json"):
        payload = _read_json(path)
        if payload is not None:
            referenced.update(_artifact_paths(payload, root))
    for path in candidates:
        if path not in referenced and path.is_file():
            _delete_file(path, root, deleted_paths)


def _prune_dataset_index(
    root: Path,
    period_strategies: Mapping[str, PeriodStrategy],
    window: RetentionWindow,
    deleted_paths: list[str],
    rewritten_paths: list[str],
) -> None:
    path = root / "quality" / "dataset_index.json"
    payload = _read_json(path)
    if payload is None or not isinstance(payload.get("datasets"), Mapping):
        return
    datasets = payload["datasets"]
    changed = False
    kept_datasets: dict[str, list[dict[str, Any]]] = {}
    for dataset, entries in datasets.items():
        if not isinstance(dataset, str) or not isinstance(entries, list):
            continue
        strategy = period_strategies.get(dataset)
        kept_entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                changed = True
                continue
            output_key = entry.get("output_key")
            entry_path = entry.get("path")
            stale = (
                strategy in (PeriodStrategy.MONTHLY, PeriodStrategy.ANNUAL)
                and isinstance(output_key, str)
                and _partition_is_stale(output_key, strategy, window)
            )
            if stale:
                changed = True
                continue
            kept_entries.append(dict(entry))
        if kept_entries:
            kept_datasets[dataset] = kept_entries
        elif entries:
            changed = True
    if not changed:
        return
    _atomic_json_write(
        path,
        {
            "schema_version": payload.get("schema_version", 1),
            "datasets": kept_datasets,
        },
    )
    rewritten_paths.append(_relative_path(path, root))


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
