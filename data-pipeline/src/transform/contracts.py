"""Shared result contracts for dataset transforms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TransformResult:
    """Records and diagnostics produced by one transform invocation."""

    records: list[dict[str, Any]]
    quality: dict[str, Any]
    quarantine: list[dict[str, Any]]
