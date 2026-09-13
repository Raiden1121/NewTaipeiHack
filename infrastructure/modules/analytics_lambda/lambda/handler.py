"""AWS Lambda: curated data in S3 -> analytics -> DynamoDB.

Runs the same analytics as `data-pipeline/src/run_analytics.py --metric all`,
minus the keyword-frequency *metric* recomputation -- the published
`participation` analysis already carries `topics.keyword_frequency`, which is
what `ANALYSIS#youth-keyword-frequency` is projected from. The snapshot is
built in `/tmp` by the same `publish_homepage_snapshot()` the local run uses,
then projected into DynamoDB items by `dynamodb_projection`.

Curated inputs are pulled from S3 on demand rather than synced up front: the
analytics asks for specific dataset periods, and only those objects are
downloaded (see `_install_s3_backing`). The bucket holds tens of GB; a full
sync would not fit in Lambda.

Environment:
    TRANSFORMED_BUCKET      bucket holding `curated/` and `quality/`
    ANALYTICS_TABLE_NAME    DynamoDB table to write
    TRANSFORMED_PREFIX      optional key prefix inside the bucket (default "")
    ANNUAL_END_ROC          optional; defaults to the latest completed ROC year
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import boto3
from botocore.exceptions import ClientError

from analytics.config import load_homepage_analytics_config
from analytics.employment import generate_employment_data
from analytics.fertility import generate_fertility_data
from analytics.homepage import generate_homepage_data
from analytics.input_resolver import HomepageInputResolver
from analytics.policy_support import generate_policy_support_data
from analytics.provenance import build_public_source_catalog, source_refs_for_datasets
from analytics.published_snapshot import publish_homepage_snapshot
from analytics.youth_participation import generate_youth_participation_data
from source_registry import SourceRegistry

from dynamodb_projection import MANIFEST_KEY, build_items, to_dynamodb_types

DATA_ROOT = Path("/tmp/data")
# The package mirrors the repo layout (see build.py) so that config paths
# pointing outside config/ -- districts.json's boundary_file -- still resolve.
CONFIG_DIR = Path(__file__).resolve().parent / "data-pipeline" / "config"
ANNUAL_WINDOW_YEARS = 5

_s3 = boto3.client("s3")
_s3_backing_installed = False


def _latest_completed_year_roc() -> int:
    """This year in ROC terms, minus one: the current year's annual stats are
    not final yet, so the pipeline's window ends on the year before."""

    return date.today().year - 1911 - 1


def _install_s3_backing(root: Path, bucket: str, prefix: str) -> None:
    """Back `root` with S3, fetching objects the first time they are read.

    The analytics reads curated data through `pathlib`, so intercepting
    `read_text`/`is_file` for paths under `root` keeps data-pipeline's own code
    untouched while letting it run against a bucket.
    """

    global _s3_backing_installed
    if _s3_backing_installed:
        # A warm container keeps the previous patch; wrapping it again would
        # stack a new layer on every invocation.
        return
    _s3_backing_installed = True

    original_read_text = Path.read_text
    original_is_file = Path.is_file
    root = root.resolve()

    def fetch(path: Path) -> bool:
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            return False
        if original_is_file(path):
            return True
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _s3.download_file(bucket, f"{prefix}{relative.as_posix()}", str(path))
        except ClientError:
            return False
        return True

    def read_text(self, *args, **kwargs):
        fetch(self)
        return original_read_text(self, *args, **kwargs)

    def is_file(self):
        return original_is_file(self) or fetch(self)

    Path.read_text = read_text
    Path.is_file = is_file


def _public_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in result.items() if key != "_quality"}


def _quality_dataset_names(quality: Any) -> list[str]:
    if not isinstance(quality, Mapping):
        return []
    source_periods = quality.get("source_periods")
    if not isinstance(source_periods, Mapping):
        return []
    return [str(dataset) for dataset in source_periods]


def _snapshot_id(generated_at: str) -> str:
    parsed = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return f"lambda-{parsed.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def _run_analytics(
    end_roc: int,
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    """Every analysis the DynamoDB item catalog needs, in dependency order."""

    config = load_homepage_analytics_config(CONFIG_DIR / "homepage_analytics.json")
    annual_years = tuple(range(end_roc - ANNUAL_WINDOW_YEARS + 1, end_roc + 1))
    config = replace(
        config,
        annual_years_roc=annual_years,
        population_reference_year_roc=end_roc,
    )
    resolver = HomepageInputResolver.from_paths(DATA_ROOT, CONFIG_DIR)

    homepage = generate_homepage_data(resolver=resolver, config=config)
    results = {
        "employment": generate_employment_data(
            resolver=resolver, config=config, homepage_result=homepage
        ),
        "fertility": generate_fertility_data(
            resolver=resolver, config=config, homepage_result=homepage
        ),
        "participation": generate_youth_participation_data(
            resolver=resolver, config=config, config_dir=CONFIG_DIR
        ),
        "policy_support": generate_policy_support_data(resolver=resolver),
    }
    analyses = {name: _public_payload(result) for name, result in results.items()}
    quality = {name: dict(result.get("_quality") or {}) for name, result in results.items()}
    return homepage, analyses, quality


def _publish(
    homepage: Mapping[str, Any],
    analyses: Mapping[str, Mapping[str, Any]],
    analysis_quality: Mapping[str, Mapping[str, Any]],
) -> Path:
    registry = SourceRegistry.from_json(CONFIG_DIR / "sources.json")
    source_refs = {
        "homepage": source_refs_for_datasets(
            _quality_dataset_names(homepage.get("_quality")), registry
        )
    }
    source_refs.update(
        {
            name: source_refs_for_datasets(_quality_dataset_names(quality), registry)
            for name, quality in analysis_quality.items()
        }
    )
    published = publish_homepage_snapshot(
        homepage,
        homepage.get("_quality"),
        output_dir=DATA_ROOT,
        snapshot_id=_snapshot_id(str(homepage["generated_at"])),
        analyses=analyses,
        analysis_quality=analysis_quality,
        source_catalog=build_public_source_catalog(registry),
        source_refs_by_dataset=source_refs,
        update_current=False,
    )
    return Path(published.snapshot_dir)


def _read_snapshot(snapshot_dir: Path) -> tuple[dict, dict, dict[str, dict]]:
    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    dashboard = json.loads(
        (snapshot_dir / manifest["artifacts"]["dashboard_overview"]).read_text(encoding="utf-8")
    )
    analyses = {
        name: json.loads((snapshot_dir / relative).read_text(encoding="utf-8"))
        for name, relative in (manifest["artifacts"].get("analyses") or {}).items()
    }
    return manifest, dashboard, analyses


def _write_items(table_name: str, items: list[dict[str, Any]]) -> int:
    table = boto3.resource("dynamodb").Table(table_name)
    manifest_item = next(item for item in items if (item["pk"], item["sk"]) == MANIFEST_KEY)
    with table.batch_writer() as batch:
        for item in items:
            if (item["pk"], item["sk"]) != MANIFEST_KEY:
                batch.put_item(Item=to_dynamodb_types(item))

    # META/MANIFEST last: readers use it to judge whether the snapshot is
    # complete, so it must not point at a half-written table.
    table.put_item(Item=to_dynamodb_types(manifest_item))
    return len(items)


def handler(event, context):
    started = time.monotonic()
    bucket = os.environ["TRANSFORMED_BUCKET"]
    table_name = os.environ["ANALYTICS_TABLE_NAME"]
    prefix = os.environ.get("TRANSFORMED_PREFIX", "")
    end_roc = int(
        (event or {}).get("annual_end_roc")
        or os.environ.get("ANNUAL_END_ROC")
        or _latest_completed_year_roc()
    )

    # A warm container still holds the previous run's downloads; keeping them
    # would silently serve stale curated data after the bucket is updated.
    shutil.rmtree(DATA_ROOT, ignore_errors=True)
    _install_s3_backing(DATA_ROOT, bucket, prefix)

    homepage, analyses, analysis_quality = _run_analytics(end_roc)
    snapshot_dir = _publish(homepage, analyses, analysis_quality)
    manifest, dashboard, published_analyses = _read_snapshot(snapshot_dir)
    items = build_items(manifest=manifest, dashboard=dashboard, analyses=published_analyses)
    written = _write_items(table_name, items)

    return {
        "snapshot_id": manifest.get("snapshot_id"),
        "generated_at": manifest.get("generated_at"),
        "annual_end_roc": end_roc,
        "items_written": written,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
