"""Read authoritative curated outputs and write analytics artifacts."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class CuratedSlice:
    """Curated records selected for explicit source periods."""

    dataset: str
    period_type: str
    source_periods: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    paths: tuple[str, ...]


def load_curated_dataset(dataset: str, *, output_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(output_dir).resolve()
    index_path = root / "quality" / "dataset_index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"dataset index is missing: {index_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"dataset index is invalid: {index_path}") from exc
    datasets = index.get("datasets") if isinstance(index, Mapping) else None
    entries = datasets.get(dataset) if isinstance(datasets, Mapping) else None
    if not isinstance(entries, list):
        raise ValueError(f"dataset {dataset!r} is not present in dataset index")

    paths: list[Path] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            continue
        relative = entry.get("path")
        output_key = entry.get("output_key")
        if not isinstance(relative, str):
            continue
        if output_key not in (None, "all") and not relative.endswith("/all.json"):
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"dataset index path escapes output directory: {relative}") from exc
        if candidate not in paths:
            paths.append(candidate)
    if not paths:
        raise ValueError(f"dataset {dataset!r} has no all-available curated output")

    records: list[dict[str, Any]] = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"curated dataset cannot be read: {path}") from exc
        values = payload.get("records") if isinstance(payload, Mapping) else payload
        if not isinstance(values, list) or any(not isinstance(value, Mapping) for value in values):
            raise ValueError(f"curated dataset records must be an array: {path}")
        records.extend(dict(value) for value in values)
    return records


def load_curated_period(
    dataset: str, period: str, *, output_dir: str | Path
) -> CuratedSlice:
    """Load one exact curated period without scanning raw artifacts."""

    _validate_component(dataset, field="dataset")
    _validate_component(period, field="period")
    root = Path(output_dir).resolve()
    path = (root / "curated" / dataset / f"{period}.json").resolve()
    _ensure_inside(path, root, relative=f"curated/{dataset}/{period}.json")
    return _load_curated_path(
        dataset,
        period,
        path,
        output_root=root,
        period_type="annual" if len(period) == 3 else "month",
    )


def load_curated_periods(
    dataset: str, periods: list[str] | tuple[str, ...], *, output_dir: str | Path
) -> CuratedSlice:
    """Load a caller-ordered collection of exact curated periods."""

    if not periods:
        raise ValueError("periods must contain at least one period")
    slices = [load_curated_period(dataset, period, output_dir=output_dir) for period in periods]
    records: list[dict[str, Any]] = []
    paths: list[str] = []
    period_type = slices[0].period_type
    for item in slices:
        if item.period_type != period_type:
            period_type = "mixed"
        records.extend(item.records)
        paths.extend(item.paths)
    return CuratedSlice(
        dataset=dataset,
        period_type=period_type,
        source_periods=tuple(period for period in periods),
        records=tuple(records),
        paths=tuple(paths),
    )


def load_latest_snapshot(dataset: str, *, output_dir: str | Path) -> CuratedSlice:
    """Load the latest snapshot path declared by the authoritative index."""

    root = Path(output_dir).resolve()
    index_path = root / "quality" / "dataset_index.json"
    index = _read_index(index_path)
    entries = index.get("datasets", {}).get(dataset)
    if not isinstance(entries, list):
        raise ValueError(f"dataset {dataset!r} is not present in dataset index")
    selected = next(
        (entry for entry in entries if isinstance(entry, Mapping) and entry.get("output_key") == "latest"),
        None,
    )
    if selected is None:
        raise ValueError(f"dataset {dataset!r} has no latest snapshot in dataset index")
    relative = selected.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"dataset {dataset!r} latest snapshot has no valid path")
    path = (root / relative).resolve()
    _ensure_inside(path, root, relative=relative)
    source_period = str(selected.get("source_period") or selected.get("output_key"))
    return _load_curated_path(
        dataset,
        source_period,
        path,
        output_root=root,
        period_type="snapshot",
    )


def _load_curated_path(
    dataset: str,
    source_period: str,
    path: Path,
    *,
    output_root: Path,
    period_type: str,
) -> CuratedSlice:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(
            f"curated dataset period is missing: dataset={dataset!r} period={source_period!r} path={path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"curated dataset is invalid: {path}") from exc
    values = payload.get("records") if isinstance(payload, Mapping) else payload
    if not isinstance(values, list) or any(not isinstance(value, Mapping) for value in values):
        raise ValueError(f"curated dataset records must be an array: {path}")
    relative = path.relative_to(output_root).as_posix()
    return CuratedSlice(
        dataset=dataset,
        period_type=period_type,
        source_periods=(source_period,),
        records=tuple(dict(value) for value in values),
        paths=(relative,),
    )


def _read_index(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"dataset index is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"dataset index is invalid: {path}") from exc
    if not isinstance(payload, Mapping) or not isinstance(payload.get("datasets"), Mapping):
        raise ValueError(f"dataset index must contain datasets: {path}")
    return payload


def _validate_component(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise ValueError(f"{field} must be a safe path component")


def _ensure_inside(path: Path, root: Path, *, relative: str) -> None:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"curated path escapes output directory: {relative}") from exc


def atomic_json_write(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.replace(target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return target
