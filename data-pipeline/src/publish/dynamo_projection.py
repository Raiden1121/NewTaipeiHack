"""Build DynamoDB serving items from one published snapshot without AWS calls."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Mapping


def project_metric_source(
    metric: Mapping[str, Any],
    source_catalog: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Add public source display fields to one metric mapping."""

    projected = dict(metric)
    source = projected.get("source")
    source = source if isinstance(source, str) and source else None
    refs = _source_refs(projected.get("sourceRefs", projected.get("source_refs", ())))
    catalog = _catalog_by_id(source_catalog)
    definition = catalog.get(source) if source is not None else None
    projected["source"] = source
    projected["sourceName"] = (
        projected.get("sourceName")
        if projected.get("sourceName") is not None
        else (definition or {}).get("sourceName")
    )
    projected["sourceUrl"] = (
        projected.get("sourceUrl")
        if projected.get("sourceUrl") is not None
        else (definition or {}).get("sourceUrl")
    )
    projected["sourceRefs"] = refs
    projected.pop("source_url", None)
    projected.pop("source_url_type", None)
    return projected


def project_budget_allocation(
    allocation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Convert published TWD budget allocations to the API's thousand-TWD shape."""

    if not isinstance(allocation, Mapping):
        raise ValueError("budget_allocation must be an object")
    if allocation.get("unit") != "TWD":
        raise ValueError("budget_allocation.unit must be TWD")

    rows = allocation.get("items")
    if not isinstance(rows, list):
        raise ValueError("budget_allocation.items must be an array")

    projected: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"budget_allocation.items[{index}] must be an object")

        label = row.get("name")
        if not isinstance(label, str) or not label:
            raise ValueError(f"budget_allocation.items[{index}].name must be non-empty")

        amount = row.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError(f"budget_allocation.items[{index}].amount must be numeric")

        share_percent = row.get("share_percent")
        if isinstance(share_percent, bool) or not isinstance(share_percent, (int, float)):
            raise ValueError(
                f"budget_allocation.items[{index}].share_percent must be numeric"
            )

        amount_thousand = amount / 1000
        if isinstance(amount, int) and amount % 1000 == 0:
            amount_thousand = amount // 1000
        projected.append(
            {
                "label": label,
                "amount_thousand": amount_thousand,
                "share_percent": share_percent,
            }
        )
    return projected


def project_snapshot_items(
    snapshot_dir: str | Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project dashboard, district, and analysis artifacts into table items."""

    snapshot_path = Path(snapshot_dir)
    snapshot_id = _required_text(manifest.get("snapshot_id"), "snapshot_id")
    source_catalog = manifest.get("sources", ())
    if not isinstance(source_catalog, Sequence) or isinstance(source_catalog, (str, bytes)):
        raise ValueError("manifest.sources must be an array")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("manifest.artifacts must be an object")
    datasets = manifest.get("datasets", ())
    if not isinstance(datasets, Sequence) or isinstance(datasets, (str, bytes)):
        raise ValueError("manifest.datasets must be an array")

    items: list[dict[str, Any]] = []
    dashboard_path = artifacts.get("dashboard_overview")
    if isinstance(dashboard_path, str):
        items.extend(
            _project_district_resource(
                snapshot_path,
                snapshot_id=snapshot_id,
                resource="dashboard_overview",
                relative_path=dashboard_path,
                source_catalog=source_catalog,
                default_sources=_dataset_sources(datasets, "homepage"),
            )
        )
    district_path = artifacts.get("district_details")
    if isinstance(district_path, str):
        items.extend(
            _project_district_resource(
                snapshot_path,
                snapshot_id=snapshot_id,
                resource="district_details",
                relative_path=district_path,
                source_catalog=source_catalog,
                default_sources=_dataset_sources(datasets, "homepage"),
            )
        )

    analyses = artifacts.get("analyses", {})
    if not isinstance(analyses, Mapping):
        raise ValueError("manifest.artifacts.analyses must be an object")
    for analysis_id, relative_path in analyses.items():
        if not isinstance(analysis_id, str) or not isinstance(relative_path, str):
            raise ValueError("analysis artifact names and paths must be strings")
        default_sources = _dataset_sources(datasets, analysis_id)
        if analysis_id == "participation" and not default_sources:
            default_sources = _dataset_sources(datasets, "homepage")
        items.extend(
            _project_analysis(
                snapshot_path,
                snapshot_id=snapshot_id,
                analysis_id=analysis_id,
                relative_path=relative_path,
                source_catalog=source_catalog,
                default_sources=default_sources,
            )
        )
    return items


def _project_district_resource(
    snapshot_dir: Path,
    *,
    snapshot_id: str,
    resource: str,
    relative_path: str,
    source_catalog: Sequence[Mapping[str, Any]],
    default_sources: Sequence[str],
) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(snapshot_dir / relative_path)
    if payload is None:
        return []
    rows = payload.get("districts")
    if not isinstance(rows, list):
        raise ValueError(f"{relative_path}.districts must be an array")
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{relative_path}.districts[{index}] must be an object")
        district_id = _required_text(row.get("district_id"), "district_id")
        metrics = row.get("metrics", {})
        if not isinstance(metrics, Mapping):
            raise ValueError(f"{relative_path}.districts[{index}].metrics must be an object")
        projected_metrics = {
            str(metric_id): _project_metric_value(
                value,
                source_catalog=source_catalog,
                default_sources=default_sources,
            )
            for metric_id, value in metrics.items()
        }
        items.append(
            {
                "PK": f"SNAPSHOT#{snapshot_id}#RESOURCE#{resource}",
                "SK": f"DISTRICT#{district_id}",
                "snapshot_id": snapshot_id,
                "resource": resource,
                "district_id": district_id,
                "district_name": row.get("district_name"),
                "metrics": projected_metrics,
                "sourceRefs": list(default_sources),
            }
        )
    return items


def _project_analysis(
    snapshot_dir: Path,
    *,
    snapshot_id: str,
    analysis_id: str,
    relative_path: str,
    source_catalog: Sequence[Mapping[str, Any]],
    default_sources: Sequence[str],
) -> list[dict[str, Any]]:
    payload = _read_json_if_exists(snapshot_dir / relative_path)
    if payload is None:
        return []
    if analysis_id == "participation":
        return _project_budget_analysis(
            payload,
            snapshot_id=snapshot_id,
            source_refs=default_sources,
        )
    rows = payload.get("data")
    if not isinstance(rows, list):
        rows = payload.get("districts", [])
    if not isinstance(rows, list):
        raise ValueError(f"{relative_path} data/districts must be an array")
    items: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"{relative_path}[{index}] must be an object")
        row_id = row.get("row_id") or row.get("district_id") or str(index)
        items.append(
            {
                "PK": f"SNAPSHOT#{snapshot_id}#ANALYSIS#{analysis_id}",
                "SK": f"ROW#{row_id}",
                "snapshot_id": snapshot_id,
                "analysis_id": analysis_id,
                "row": _project_nested_row(
                    row,
                    source_catalog=source_catalog,
                    default_sources=default_sources,
                ),
                "sourceRefs": list(default_sources),
            }
        )
    return items


def _project_budget_analysis(
    payload: Mapping[str, Any],
    *,
    snapshot_id: str,
    source_refs: Sequence[str],
) -> list[dict[str, Any]]:
    allocation = payload.get("budget_allocation")
    budget_by_department = (
        project_budget_allocation(allocation)
        if isinstance(allocation, Mapping)
        else []
    )
    return [
        {
            "PK": f"SNAPSHOT#{snapshot_id}#ANALYSIS#politics-resource-io",
            "SK": "DATA",
            "snapshot_id": snapshot_id,
            "analysis_id": "politics-resource-io",
            "budget_by_department": budget_by_department,
            "budget_year_roc": allocation.get("budget_year_roc") if isinstance(allocation, Mapping) else None,
            "document_status": allocation.get("document_status") if isinstance(allocation, Mapping) else None,
            "sourceRefs": list(source_refs),
        }
    ]


def _project_nested_row(
    row: Mapping[str, Any],
    *,
    source_catalog: Sequence[Mapping[str, Any]],
    default_sources: Sequence[str],
) -> dict[str, Any]:
    projected = dict(row)
    metrics = projected.get("metrics")
    if isinstance(metrics, Mapping):
        projected["metrics"] = {
            str(metric_id): _project_metric_value(
                value,
                source_catalog=source_catalog,
                default_sources=default_sources,
            )
            for metric_id, value in metrics.items()
        }
    return projected


def _project_metric_value(
    value: Any,
    *,
    source_catalog: Sequence[Mapping[str, Any]],
    default_sources: Sequence[str],
) -> dict[str, Any]:
    if isinstance(value, Mapping):
        metric = dict(value)
    else:
        metric = {"value": value}
    if not metric.get("source") and not metric.get("sourceRefs") and not metric.get("source_refs"):
        if len(default_sources) == 1:
            metric["source"] = default_sources[0]
        elif len(default_sources) > 1:
            metric["sourceRefs"] = list(default_sources)
    return project_metric_source(metric, source_catalog)


def _dataset_sources(datasets: Sequence[Any], dataset_name: str) -> list[str]:
    for entry in datasets:
        if isinstance(entry, Mapping) and entry.get("dataset") == dataset_name:
            values = entry.get("sources", ())
            return _source_refs(values)
    return []


def _catalog_by_id(values: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise ValueError(f"source catalog entry {index} must be an object")
        source = value.get("source")
        if not isinstance(source, str) or not source:
            raise ValueError(f"source catalog entry {index} has no source ID")
        if source in catalog:
            raise ValueError(f"duplicate source catalog ID: {source}")
        catalog[source] = dict(value)
    return catalog


def _source_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("sourceRefs must be an array of source IDs")
    return sorted({item for item in value if isinstance(item, str) and item})


def _read_json_if_exists(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, Mapping):
        raise ValueError(f"published artifact must be an object: {path}")
    return payload


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value
