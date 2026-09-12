"""Source metadata helpers for published analytics contracts."""

from __future__ import annotations

from collections.abc import Iterable

from source_registry import SourceRegistry


def build_public_source_catalog(registry: SourceRegistry) -> list[dict]:
    """Return the registry catalog in the public camelCase contract."""

    return registry.public_catalog()


def source_refs_for_datasets(
    dataset_names: Iterable[str], registry: SourceRegistry
) -> list[str]:
    """Resolve dataset names to sorted, unique source IDs."""

    source_ids = {
        source_id
        for dataset in dataset_names
        if (source_id := registry.dataset_source(str(dataset))) is not None
    }
    return sorted(source_ids)
