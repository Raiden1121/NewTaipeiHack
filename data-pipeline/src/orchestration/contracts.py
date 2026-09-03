"""Contracts shared by pipeline orchestration helpers."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class PeriodStrategy(str, Enum):
    """How a collector maps a requested month range to source fetches."""

    MONTHLY = "monthly"
    ANNUAL = "annual"
    SNAPSHOT = "snapshot"
    ALL_AVAILABLE = "all_available"


@dataclass(frozen=True)
class CollectorSpec:
    """One named collector and the source period cadence it supports."""

    dataset: str
    collect: Callable[[str], Any]
    period_strategy: PeriodStrategy = PeriodStrategy.MONTHLY


@dataclass(frozen=True)
class ExecutionUnit:
    """One collect -> transform execution and its output partition key."""

    spec: CollectorSpec
    source_period: str
    output_key: str


@dataclass(frozen=True)
class RetryResult:
    value: Any
    attempts: int
