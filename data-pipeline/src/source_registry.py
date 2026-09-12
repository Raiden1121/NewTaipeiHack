"""Versioned source definitions and legacy provenance resolution."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


_SCHEMA_VERSION = 1
_URL_TYPES = frozenset({"api", "dataset", "detail", "listing", "resource"})
_HTTP_SCHEMES = frozenset({"http", "https"})


class SourceRegistryError(ValueError):
    """Raised when the versioned source registry is invalid."""


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """One stable source ID and its user-facing verification metadata."""

    source: str
    name_zh: str
    source_url: str | None
    url_type: str | None


@dataclass(frozen=True, slots=True)
class SourceContext:
    """Resolved source metadata for a raw, curated, or public record."""

    source: str | None
    source_name: str | None
    source_url: str | None
    url_type: str | None
    warnings: tuple[str, ...] = ()


class SourceRegistry:
    """Load and resolve the pipeline's stable source definitions."""

    def __init__(
        self,
        sources: Mapping[str, SourceDefinition],
        dataset_defaults: Mapping[str, str],
    ) -> None:
        self._sources = dict(sources)
        self._dataset_defaults = dict(dataset_defaults)

    @classmethod
    def from_json(cls, path: str | Path) -> "SourceRegistry":
        registry_path = Path(path)
        try:
            with registry_path.open(encoding="utf-8") as handle:
                payload = json.load(handle, object_pairs_hook=_reject_duplicate_keys)
        except OSError as exc:
            raise SourceRegistryError(
                f"source registry cannot be read: {registry_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise SourceRegistryError(
                f"source registry is not valid JSON: {registry_path}"
            ) from exc

        if not isinstance(payload, Mapping):
            raise SourceRegistryError("source registry root must be an object")
        if payload.get("schema_version") != _SCHEMA_VERSION:
            raise SourceRegistryError(
                f"source registry schema_version must be {_SCHEMA_VERSION}"
            )

        raw_sources = payload.get("sources")
        if not isinstance(raw_sources, Mapping):
            raise SourceRegistryError("source registry sources must be an object")
        sources: dict[str, SourceDefinition] = {}
        for source_id, raw_definition in raw_sources.items():
            if not isinstance(source_id, str) or not source_id.strip():
                raise SourceRegistryError("source IDs must be non-empty strings")
            if not isinstance(raw_definition, Mapping):
                raise SourceRegistryError(
                    f"source definition must be an object: {source_id}"
                )
            name_zh = raw_definition.get("name_zh")
            if not isinstance(name_zh, str) or not name_zh.strip():
                raise SourceRegistryError(
                    f"source definition requires name_zh: {source_id}"
                )
            source_url = raw_definition.get("source_url")
            if source_url is not None:
                _validate_url(source_url, field=f"{source_id}.source_url")
            url_type = raw_definition.get("url_type")
            if url_type is not None:
                if not isinstance(url_type, str) or url_type not in _URL_TYPES:
                    raise SourceRegistryError(
                        f"{source_id}.url_type must be one of {sorted(_URL_TYPES)}"
                    )
            sources[source_id] = SourceDefinition(
                source=source_id,
                name_zh=name_zh.strip(),
                source_url=source_url,
                url_type=url_type,
            )

        raw_defaults = payload.get("dataset_defaults")
        if not isinstance(raw_defaults, Mapping):
            raise SourceRegistryError("source registry dataset_defaults must be an object")
        dataset_defaults: dict[str, str] = {}
        for dataset, source_id in raw_defaults.items():
            if not isinstance(dataset, str) or not dataset.strip():
                raise SourceRegistryError("dataset default keys must be non-empty strings")
            if not isinstance(source_id, str) or not source_id.strip():
                raise SourceRegistryError(
                    f"dataset default source must be a non-empty string: {dataset}"
                )
            if source_id not in sources:
                raise SourceRegistryError(
                    f"dataset default references unknown source: {dataset} -> {source_id}"
                )
            dataset_defaults[dataset] = source_id

        return cls(sources, dataset_defaults)

    def dataset_source(self, dataset: str) -> str | None:
        """Return the configured fallback source ID for one canonical dataset."""

        return self._dataset_defaults.get(dataset)

    def resolve(
        self,
        *,
        dataset: str,
        source: str | None = None,
        source_url: str | None = None,
    ) -> SourceContext:
        """Resolve explicit or dataset-default source metadata."""

        resolved_source = source or self.dataset_source(dataset)
        warnings: list[str] = []
        if resolved_source is None:
            warnings.append("source_unresolved")
            return SourceContext(
                source=None,
                source_name=None,
                source_url=source_url,
                url_type=None,
                warnings=tuple(warnings),
            )

        definition = self._sources.get(resolved_source)
        if definition is None:
            warnings.append("unknown_source_id")
            if source_url is None:
                warnings.append("source_unresolved")
            return SourceContext(
                source=resolved_source,
                source_name=None,
                source_url=source_url,
                url_type=None,
                warnings=tuple(warnings),
            )

        if source_url is not None:
            _validate_url(source_url, field="source_url")
        return SourceContext(
            source=resolved_source,
            source_name=definition.name_zh,
            source_url=source_url or definition.source_url,
            url_type=definition.url_type,
            warnings=tuple(warnings),
        )

    def public_catalog(self) -> list[dict[str, Any]]:
        """Return deterministic API/DynamoDB source metadata."""

        return [
            {
                "source": definition.source,
                "sourceName": definition.name_zh,
                "sourceUrl": definition.source_url,
                "urlType": definition.url_type,
            }
            for definition in sorted(self._sources.values(), key=lambda item: item.source)
        ]


def _validate_url(value: Any, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SourceRegistryError(f"{field} must be a non-empty URL")
    parsed = urlparse(value)
    if parsed.scheme not in _HTTP_SCHEMES or not parsed.netloc:
        raise SourceRegistryError(f"{field} must be an HTTP(S) URL")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, value in pairs:
        if key in values:
            raise SourceRegistryError(f"duplicate JSON key: {key}")
        values[key] = value
    return values
