"""Attach canonical source URLs to curated records without mutating Raw."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from source_registry import SourceRegistry


def enrich_curated_records(
    records: Iterable[Mapping[str, Any]],
    *,
    dataset: str,
    raw_payload: Mapping[str, Any],
    registry: SourceRegistry,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return copied records with source provenance and a quality report."""

    raw_source = _payload_value(raw_payload, "source")
    raw_source_url = _payload_value(raw_payload, "source_url")
    output: list[dict[str, Any]] = []
    resolved_sources: set[str] = set()
    warnings: set[str] = set()
    unresolved_count = 0

    for record in records:
        copied = dict(record)
        record_source = _text(copied.get("source"))
        record_source_url = _text(copied.get("source_url"))
        if record_source and raw_source and record_source != raw_source:
            warnings.add("source_conflict")

        source = record_source or raw_source
        source_url = raw_source_url or record_source_url
        context = registry.resolve(
            dataset=dataset,
            source=source,
            source_url=source_url,
        )
        copied["source"] = context.source
        copied["source_url"] = context.source_url
        copied["source_url_type"] = context.url_type
        warnings.update(context.warnings)
        if context.source:
            resolved_sources.add(context.source)
        if any(
            warning in {"source_unresolved", "unknown_source_id"}
            for warning in context.warnings
        ):
            unresolved_count += 1
        output.append(copied)

    report = {
        "resolved_sources": sorted(resolved_sources),
        "unresolved_count": unresolved_count,
        "warnings": sorted(warnings),
    }
    return output, report


def _payload_value(payload: Mapping[str, Any], field: str) -> str | None:
    value = _text(payload.get(field))
    if value is not None:
        return value
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        return _text(metadata.get(field))
    return None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None
