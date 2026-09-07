"""Quality counters and rejected-row capture for transforms."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping


class QualityCollector:
    def __init__(self, *, rows_in: int = 0) -> None:
        self.rows_in = rows_in
        self.rows_out = 0
        self.rows_rejected = 0
        self.duplicate_count = 0
        self.unmapped_district_count = 0
        self.numeric_parse_errors = 0
        self.missing_value_count = 0
        self._warnings: list[str] = []
        self._reject_reasons: Counter[str] = Counter()
        self.quarantine: list[dict[str, Any]] = []

    def accept(self, count: int = 1) -> None:
        self.rows_out += count

    def reject(self, input_index: int, raw_record: Mapping[str, Any], reason: str) -> None:
        self.rows_rejected += 1
        self._reject_reasons[reason] += 1
        self.quarantine.append(
            {
                "input_index": input_index,
                "raw_record": deepcopy(dict(raw_record)),
                "reason": reason,
            }
        )

    def record_duplicate(self, count: int = 1) -> None:
        self.duplicate_count += count

    def record_unmapped_district(self, count: int = 1) -> None:
        self.unmapped_district_count += count

    def record_numeric_error(self, field: str | None = None, count: int = 1) -> None:
        self.numeric_parse_errors += count

    def record_missing(self, field: str | None = None, count: int = 1) -> None:
        self.missing_value_count += count

    def warn(self, warning: str) -> None:
        if warning not in self._warnings:
            self._warnings.append(warning)

    def finish(self) -> dict[str, Any]:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "rows_rejected": self.rows_rejected,
            "duplicate_count": self.duplicate_count,
            "unmapped_district_count": self.unmapped_district_count,
            "numeric_parse_errors": self.numeric_parse_errors,
            "missing_value_count": self.missing_value_count,
            "warnings": list(self._warnings),
            "reject_reasons": dict(self._reject_reasons),
        }
