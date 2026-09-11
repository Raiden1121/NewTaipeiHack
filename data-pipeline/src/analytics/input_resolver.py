"""Explicit curated input selection for homepage analytics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import HomepageAnalyticsConfig, load_homepage_analytics_config
from .io import CuratedSlice, load_curated_dataset, load_curated_period, load_curated_periods, load_latest_snapshot


@dataclass(frozen=True, slots=True)
class HomepageInputResolver:
    """Resolve only known curated paths; never fetch or inspect raw artifacts."""

    output_dir: Path
    district_resolver: Any

    @classmethod
    def from_paths(cls, output_dir: str | Path, config_dir: str | Path) -> "HomepageInputResolver":
        from transform.geography import DistrictResolver

        config_path = Path(config_dir) / "districts.json"
        return cls(Path(output_dir), DistrictResolver.from_json(config_path))

    @property
    def districts(self) -> list[dict[str, Any]]:
        return self.district_resolver.districts

    def period(self, dataset: str, period: str) -> CuratedSlice:
        return load_curated_period(dataset, period, output_dir=self.output_dir)

    def periods(self, dataset: str, periods: list[str] | tuple[str, ...]) -> CuratedSlice:
        return load_curated_periods(dataset, periods, output_dir=self.output_dir)

    def available_periods(self, dataset: str, periods: list[str] | tuple[str, ...]) -> CuratedSlice:
        selected: list[CuratedSlice] = []
        for period in periods:
            try:
                selected.append(self.period(dataset, period))
            except ValueError:
                continue
        if not selected:
            raise ValueError(f"dataset {dataset!r} has no available requested periods")
        records: list[dict[str, Any]] = []
        source_periods: list[str] = []
        paths: list[str] = []
        period_type = selected[0].period_type
        for item in selected:
            records.extend(item.records)
            source_periods.extend(item.source_periods)
            paths.extend(item.paths)
            if item.period_type != period_type:
                period_type = "mixed"
        return CuratedSlice(dataset, period_type, tuple(source_periods), tuple(records), tuple(paths))

    def latest(self, dataset: str) -> CuratedSlice:
        try:
            return load_latest_snapshot(dataset, output_dir=self.output_dir)
        except ValueError:
            # Compatibility for curated snapshots created before the index was
            # authoritative, and for a range run that predates index merging.
            flat_path = next(
                (
                    path
                    for path in (
                        self.output_dir / "curated" / dataset / "latest.json",
                        self.output_dir / "curated" / f"{dataset}.json",
                    )
                    if path.is_file()
                ),
                None,
            )
            if flat_path is None:
                raise
            from .io import _load_curated_path

            return _load_curated_path(
                dataset,
                "legacy_flat_snapshot",
                flat_path.resolve(),
                output_root=self.output_dir.resolve(),
                period_type="snapshot",
            )

    def all_available(self, dataset: str) -> CuratedSlice:
        try:
            records = load_curated_dataset(dataset, output_dir=self.output_dir)
            return CuratedSlice(dataset, "mixed", ("all",), tuple(records), (f"curated/{dataset}/all.json",))
        except ValueError:
            path = next(
                (
                    candidate
                    for candidate in (
                        self.output_dir / "curated" / dataset / "all.json",
                        self.output_dir / "curated" / f"{dataset}.json",
                    )
                    if candidate.is_file()
                ),
                None,
            )
            if path is None:
                raise
            from .io import _load_curated_path

            return _load_curated_path(
                dataset,
                "all",
                path.resolve(),
                output_root=self.output_dir.resolve(),
                period_type="mixed",
            )


__all__ = ["HomepageAnalyticsConfig", "HomepageInputResolver", "load_homepage_analytics_config"]
