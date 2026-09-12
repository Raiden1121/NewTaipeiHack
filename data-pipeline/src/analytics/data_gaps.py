"""Explain why an analytics value is missing, using a verified gap registry.

Every entry in ``config/data_gaps.json`` records a limitation that was checked
against the live source, so a ``null`` can be presented as a known source
boundary rather than an unexplained hole.  Reason codes with no registry entry
are passed through unchanged; the registry annotates, it never filters.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping


DEFAULT_FILENAME = "data_gaps.json"


def load_data_gaps(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load the registry, returning an empty mapping when it is absent."""

    config_path = Path(path)
    if not config_path.is_file():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid data gap registry: {config_path}") from exc
    gaps = payload.get("gaps") if isinstance(payload, Mapping) else None
    if not isinstance(gaps, Mapping):
        return {}
    return {
        str(code): dict(entry)
        for code, entry in gaps.items()
        if isinstance(entry, Mapping)
    }


@lru_cache(maxsize=8)
def _cached_gaps(config_dir: str) -> tuple[tuple[str, str], ...]:
    """Cache a hashable view so repeated metric runs re-read nothing."""

    gaps = load_data_gaps(Path(config_dir) / DEFAULT_FILENAME)
    return tuple((code, json.dumps(entry, ensure_ascii=False)) for code, entry in gaps.items())


def explain_reason_codes(
    reason_codes: Iterable[str], *, config_dir: str | Path
) -> list[dict[str, Any]]:
    """Expand reason codes into the registry's verified explanations.

    Unknown codes still appear so a new blocking reason is visible rather than
    silently dropped while its registry entry is being written.
    """

    registry = {code: json.loads(entry) for code, entry in _cached_gaps(str(config_dir))}
    explained: list[dict[str, Any]] = []
    for code in dict.fromkeys(str(item) for item in reason_codes if item):
        entry = registry.get(code)
        if entry is None:
            explained.append({"reason_code": code, "documented": False})
            continue
        explained.append({"reason_code": code, "documented": True, **entry})
    return explained


__all__ = ["DEFAULT_FILENAME", "explain_reason_codes", "load_data_gaps"]
