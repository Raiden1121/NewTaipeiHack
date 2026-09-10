"""Read authoritative curated outputs and write analytics artifacts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Mapping


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

