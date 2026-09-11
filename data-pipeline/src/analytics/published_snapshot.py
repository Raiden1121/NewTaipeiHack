"""Publish analytics output as a versioned, Backend-readable snapshot."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .io import atomic_json_write


_SAFE_SNAPSHOT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_VALID_STATUSES = {"available", "partial", "unavailable"}
_PUBLIC_FORBIDDEN_KEYS = {"raw_record", "raw_records"}


@dataclass(frozen=True, slots=True)
class PublishedSnapshot:
    """Paths written for one published analytics snapshot."""

    snapshot_id: str
    snapshot_dir: Path
    manifest_path: Path
    current_path: Path


def publish_homepage_snapshot(
    homepage_payload: Mapping[str, Any],
    quality_payload: Mapping[str, Any] | None = None,
    *,
    output_dir: str | Path,
    snapshot_id: str | None = None,
    analyses: Mapping[str, Mapping[str, Any]] | None = None,
    analysis_quality: Mapping[str, Mapping[str, Any]] | None = None,
) -> PublishedSnapshot:
    """Write a homepage payload as an atomic, versioned published snapshot.

    Snapshot artifacts are written before ``current.json``.  A failed write
    therefore leaves the previous current pointer unchanged.
    """

    _validate_public_payload(homepage_payload)
    generated_at = _required_text(homepage_payload.get("generated_at"), "generated_at")
    resolved_snapshot_id = snapshot_id or _snapshot_id_from_generated_at(generated_at)
    _validate_snapshot_id(resolved_snapshot_id)

    quality = quality_payload if quality_payload is not None else {}
    if not isinstance(quality, Mapping):
        raise ValueError("quality_payload must be a mapping")
    if analyses is not None and not isinstance(analyses, Mapping):
        raise ValueError("analyses must be a mapping")
    if analysis_quality is not None and not isinstance(analysis_quality, Mapping):
        raise ValueError("analysis_quality must be a mapping")

    named_analyses: dict[str, Mapping[str, Any]] = {}
    for name, payload in (analyses or {}).items():
        _validate_analysis_name(name)
        if not isinstance(payload, Mapping):
            raise ValueError(f"analysis {name!r} must be a mapping")
        _validate_public_payload(payload, path=f"analyses.{name}")
        named_analyses[name] = payload
    named_quality: dict[str, Mapping[str, Any]] = {}
    for name, payload in (analysis_quality or {}).items():
        _validate_analysis_name(name)
        if not isinstance(payload, Mapping):
            raise ValueError(f"analysis_quality {name!r} must be a mapping")
        _validate_public_payload(payload, path=f"analysis_quality.{name}")
        named_quality[name] = payload

    districts = homepage_payload.get("districts")
    if not isinstance(districts, list):
        raise ValueError("homepage payload districts must be a list")

    published_root = Path(output_dir) / "analytics" / "published"
    snapshot_dir = published_root / resolved_snapshot_id
    overview = _build_dashboard_overview(homepage_payload, quality, districts)
    district_details = _build_district_details(homepage_payload, districts)
    manifest = _build_manifest(
        homepage_payload,
        quality,
        resolved_snapshot_id,
        districts,
        named_analyses,
        named_quality,
    )

    atomic_json_write(snapshot_dir / "dashboard_overview.json", overview)
    atomic_json_write(snapshot_dir / "district_details.json", district_details)
    for name, payload in named_analyses.items():
        atomic_json_write(snapshot_dir / "analyses" / f"{name}.json", payload)
    manifest_path = atomic_json_write(snapshot_dir / "manifest.json", manifest)
    current_path = atomic_json_write(
        published_root / "current.json", {"snapshot_id": resolved_snapshot_id}
    )
    return PublishedSnapshot(
        snapshot_id=resolved_snapshot_id,
        snapshot_dir=snapshot_dir,
        manifest_path=manifest_path,
        current_path=current_path,
    )


def _build_dashboard_overview(
    homepage: Mapping[str, Any], quality: Mapping[str, Any], districts: list[Any]
) -> dict[str, Any]:
    return {
        "metric_id": homepage.get("metric_id", "homepage"),
        "calculation_version": homepage.get("calculation_version"),
        "generated_at": homepage.get("generated_at"),
        "time_policy": homepage.get("time_policy", {}),
        "kpis": homepage.get("kpi", {}),
        "districts": districts,
        "availability": _availability(homepage, districts),
        "policy": homepage.get("policy", {}),
        "annual": homepage.get("annual", {}),
        "elections": homepage.get("elections", {}),
        "service_coverage": homepage.get("service_coverage", {}),
        "warnings": _quality_flags(quality),
    }


def _build_district_details(
    homepage: Mapping[str, Any], districts: list[Any]
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    for index, row in enumerate(districts):
        if not isinstance(row, Mapping):
            raise ValueError(f"homepage districts[{index}] must be an object")
        district_id = _required_text(row.get("district_id"), f"districts[{index}].district_id")
        district_name = _required_text(
            row.get("district_name"), f"districts[{index}].district_name"
        )
        metrics = {
            key: value
            for key, value in row.items()
            if key not in {"district_id", "district_name"}
        }
        details.append(
            {
                "district_id": district_id,
                "district_name": district_name,
                "metrics": metrics,
            }
        )
    return {
        "metric_id": homepage.get("metric_id", "homepage"),
        "calculation_version": homepage.get("calculation_version"),
        "generated_at": homepage.get("generated_at"),
        "districts": details,
    }


def _build_manifest(
    homepage: Mapping[str, Any],
    quality: Mapping[str, Any],
    snapshot_id: str,
    districts: list[Any],
    analyses: Mapping[str, Mapping[str, Any]] | None = None,
    analysis_quality: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    flags = _quality_flags(quality)
    time_policy = homepage.get("time_policy", {})
    analysis_artifacts = {
        name: f"analyses/{name}.json" for name in (analyses or {})
    }
    analysis_datasets = [
        _build_analysis_dataset_entry(
            name,
            payload,
            (analysis_quality or {}).get(name, {}),
        )
        for name, payload in (analyses or {}).items()
    ]
    return {
        "schema_version": 1,
        "snapshot_id": snapshot_id,
        "generated_at": homepage.get("generated_at"),
        "as_of": None,
        "artifacts": {
            "dashboard_overview": "dashboard_overview.json",
            "district_details": "district_details.json",
            "analyses": analysis_artifacts,
        },
        "datasets": [
            {
                "dataset": "homepage",
                "path": "dashboard_overview.json",
                "period_strategy": "mixed",
                "source_period": quality.get("source_periods", {}),
                "geo_level": "district",
                "coverage": {
                    "district_count": len(districts),
                    "expected_district_count": 29,
                    "annual_years_roc": time_policy.get("annual_years_roc", []),
                },
                "quality_flags": flags,
            }
        ] + analysis_datasets,
        "warnings": flags,
    }


def _availability(homepage: Mapping[str, Any], districts: list[Any]) -> dict[str, str]:
    rows = [row for row in districts if isinstance(row, Mapping)]
    annual = homepage.get("annual")
    fertility_years = annual.get("fertility", {}).get("years", []) if isinstance(annual, Mapping) else []
    fertility_status = None
    if fertility_years and isinstance(fertility_years[-1], Mapping):
        city = fertility_years[-1].get("city", {})
        if isinstance(city, Mapping):
            fertility_status = city.get("quality_status")

    budget_rows = annual.get("budget_trend", []) if isinstance(annual, Mapping) else []
    return {
        "opportunityIndex": _values_status(rows, "opportunityIndex"),
        "fertility": fertility_status if fertility_status in _VALID_STATUSES else _values_status(rows, "fertilityRate"),
        "youthParticipationIndex": _values_status(rows, "youthParticipationIndex"),
        "serviceCoverage": _explicit_status(homepage.get("service_coverage"), rows, "serviceCoverageRate"),
        "budget": _budget_status(budget_rows),
    }


def _values_status(rows: list[Mapping[str, Any]], key: str) -> str:
    if not rows or not any(row.get(key) is not None for row in rows):
        return "unavailable"
    if any(row.get(key) is None for row in rows):
        return "partial"
    return "available"


def _explicit_status(value: Any, rows: list[Mapping[str, Any]], key: str) -> str:
    if isinstance(value, Mapping) and value.get("status") in _VALID_STATUSES:
        return str(value["status"])
    return _values_status(rows, key)


def _budget_status(rows: Any) -> str:
    if not isinstance(rows, list) or not rows:
        return "unavailable"
    values = [row.get("legal_budget_amount") for row in rows if isinstance(row, Mapping)]
    if not any(value is not None for value in values):
        return "unavailable"
    if any(value is None for value in values):
        return "partial"
    return "available"


def _quality_flags(quality: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("warnings", "blocking_reasons"):
        items = quality.get(key, [])
        if isinstance(items, list):
            values.extend(str(item) for item in items if item)
    return list(dict.fromkeys(values))


def _validate_public_payload(value: Any, *, path: str = "homepage") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in _PUBLIC_FORBIDDEN_KEYS:
                raise ValueError(f"published payload cannot contain {path}.{key}")
            _validate_public_payload(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_public_payload(child, path=f"{path}[{index}]")


def _build_analysis_dataset_entry(
    name: str,
    payload: Mapping[str, Any],
    quality: Mapping[str, Any],
) -> dict[str, Any]:
    districts = payload.get("districts")
    coverage = quality.get("coverage")
    if not isinstance(coverage, Mapping):
        coverage = {
            "district_count": len(districts) if isinstance(districts, list) else 0,
        }
    return {
        "dataset": name,
        "path": f"analyses/{name}.json",
        "period_strategy": "latest_snapshot",
        "source_period": quality.get("source_periods", {}),
        "geo_level": "district",
        "coverage": dict(coverage),
        "quality_flags": _quality_flags(quality),
    }


def _validate_analysis_name(value: Any) -> None:
    if not isinstance(value, str) or _SAFE_SNAPSHOT_ID.fullmatch(value) is None:
        raise ValueError("analysis name must be a safe path component")


def _snapshot_id_from_generated_at(generated_at: str) -> str:
    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("generated_at must be a valid ISO timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _validate_snapshot_id(value: str) -> None:
    if not isinstance(value, str) or _SAFE_SNAPSHOT_ID.fullmatch(value) is None:
        raise ValueError("snapshot_id must be a safe path component")


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


__all__ = ["PublishedSnapshot", "publish_homepage_snapshot"]
