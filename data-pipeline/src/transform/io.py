"""Atomic local JSON outputs for raw and curated pipeline stages."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from orchestration.state import SCHEMA_VERSION

from .contracts import TransformResult


def write_raw(
    payload: Mapping[str, Any],
    *,
    dataset: str,
    snapshot: str,
    output_dir: str | Path,
) -> Path:
    path = Path(output_dir) / "raw" / dataset / f"{snapshot}.json"
    _atomic_json_write(path, dict(payload))
    return path


def write_curated(
    result: TransformResult,
    *,
    dataset: str,
    output_dir: str | Path,
    period: str | None = None,
) -> tuple[Path, Path, Path]:
    root = Path(output_dir)
    if period is None:
        curated_path = root / "curated" / f"{dataset}.json"
        quality_path = root / "quality" / f"{dataset}.json"
        quarantine_path = root / "quarantine" / f"{dataset}.json"
    else:
        curated_path = root / "curated" / dataset / f"{period}.json"
        quality_path = root / "quality" / dataset / f"{period}.json"
        quarantine_path = root / "quarantine" / dataset / f"{period}.json"
    generated_at = datetime.now(timezone.utc).isoformat()
    curated_payload = {
        "dataset": dataset,
        "generated_at": generated_at,
        "records": result.records,
    }
    quality_payload = dict(result.quality)
    if period is not None:
        curated_payload["period"] = period
        quality_payload["dataset"] = dataset
        quality_payload["period"] = period
    _atomic_json_write(
        curated_path,
        curated_payload,
    )
    _atomic_json_write(quality_path, quality_payload)
    _atomic_json_write(quarantine_path, result.quarantine)
    return curated_path, quality_path, quarantine_path


def write_collection_report(
    report: Mapping[str, Any], *, output_dir: str | Path, period: str | None = None
) -> Path:
    """Persist the per-dataset collection status under the quality directory."""

    path = Path(output_dir) / "quality" / "collection.json"
    if period is not None:
        path = Path(output_dir) / "quality" / "collection" / f"{period}.json"
    _atomic_json_write(path, dict(report))
    return path


def write_period_range_report(
    report: Mapping[str, Any], *, output_dir: str | Path
) -> Path:
    """Persist the summary for an inclusive historical-period run."""

    path = Path(output_dir) / "quality" / "collection_range.json"
    _atomic_json_write(path, dict(report))
    return path


def write_dataset_index(
    entries: list[Mapping[str, Any]], *, output_dir: str | Path
) -> Path:
    """Atomically write the curated outputs authoritative for the current run."""

    datasets: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        dataset = entry.get("dataset")
        if not isinstance(dataset, str) or not dataset:
            raise ValueError("dataset index entries require a non-empty dataset")
        datasets.setdefault(dataset, []).append(
            {key: value for key, value in entry.items() if key != "dataset"}
        )

    path = Path(output_dir) / "quality" / "dataset_index.json"
    _atomic_json_write(
        path,
        {
            "schema_version": SCHEMA_VERSION,
            "datasets": datasets,
        },
    )
    return path


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
