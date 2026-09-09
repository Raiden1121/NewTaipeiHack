"""Typed contracts shared by collectors and pipeline persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceArtifact:
    """One binary source file returned alongside JSON-serializable records."""

    filename: str
    content: bytes
    media_type: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CollectedPayload:
    """Collector output containing records, source metadata, and binary artifacts."""

    records: list[dict[str, Any]]
    metadata: dict[str, Any]
    artifacts: tuple[SourceArtifact, ...] = ()
