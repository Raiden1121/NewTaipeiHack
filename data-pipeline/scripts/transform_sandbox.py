"""Re-run every transform against an isolated copy of data/raw.

Reads <sandbox>/raw and writes <sandbox>/curated, <sandbox>/quality and
<sandbox>/quarantine, leaving the working data/ tree untouched. Output
partitioning follows the real pipeline's period strategy, so the result is
directly comparable with data/curated.

    python scripts/transform_sandbox.py --sandbox sandbox
    python scripts/transform_sandbox.py --sandbox sandbox --datasets house_prices,rentals
    python scripts/transform_sandbox.py --sandbox sandbox --latest-only
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from orchestration.contracts import PeriodStrategy  # noqa: E402
from run_pipeline import DEFAULT_COLLECTOR_SPECS, _load_source_registry  # noqa: E402
from transform.geography import DistrictResolver  # noqa: E402
from transform.io import write_curated  # noqa: E402
from transform.pipeline import (  # noqa: E402
    canonicalize_dataset,
    dataset_requires_resolver,
    run_transform,
)
from transform.provenance import enrich_curated_records  # noqa: E402

STRATEGY = {spec.dataset: spec.period_strategy for spec in DEFAULT_COLLECTOR_SPECS}


def _output_key(dataset: str, source_period: str) -> str:
    strategy = STRATEGY.get(dataset, PeriodStrategy.MONTHLY)
    if strategy is PeriodStrategy.ANNUAL:
        return source_period[:3]
    if strategy is PeriodStrategy.SNAPSHOT:
        return "latest"
    if strategy is PeriodStrategy.ALL_AVAILABLE:
        return "all"
    return source_period


def _raw_files(directory: Path, dataset: str, latest_only: bool) -> list[Path]:
    files = sorted(p for p in directory.glob("*.json"))
    if not files:
        return []
    strategy = STRATEGY.get(dataset, PeriodStrategy.MONTHLY)
    # Snapshot/all datasets keep one partition, so only the newest raw matters —
    # newest by collection time, not by name: a raw file may carry a period that
    # sorts after the real latest (house_prices has an 11601 snapshot).
    if latest_only or strategy in (PeriodStrategy.SNAPSHOT, PeriodStrategy.ALL_AVAILABLE):
        return [max(files, key=lambda path: path.stat().st_mtime)]
    # One raw file per partition: later timestamps supersede earlier ones.
    newest: dict[str, Path] = {}
    for path in files:
        newest[_output_key(dataset, path.stem.split("_", 1)[0])] = path
    return sorted(newest.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sandbox", default="sandbox", help="sandbox directory holding raw/")
    parser.add_argument("--datasets", help="comma-separated subset")
    parser.add_argument("--latest-only", action="store_true", help="one newest partition per dataset")
    args = parser.parse_args()

    sandbox = (ROOT / args.sandbox).resolve() if not Path(args.sandbox).is_absolute() else Path(args.sandbox)
    raw_root = sandbox / "raw"
    if not raw_root.is_dir():
        raise SystemExit(f"no raw directory under {sandbox}")
    if sandbox.resolve() == (ROOT / "data").resolve():
        raise SystemExit("refusing to write into the live data/ tree")

    wanted = {d.strip() for d in args.datasets.split(",")} if args.datasets else None
    resolver = DistrictResolver.from_json(ROOT / "config/districts.json")
    registry = _load_source_registry(ROOT / "config")

    datasets = sorted(p.name for p in raw_root.iterdir() if p.is_dir() and p.name != "artifacts")
    started = time.time()
    ok = skipped = 0
    failures: list[tuple[str, str, str]] = []
    totals = {"rows_in": 0, "rows_out": 0, "rows_rejected": 0}

    for dataset in datasets:
        if wanted and dataset not in wanted:
            continue
        files = _raw_files(raw_root / dataset, dataset, args.latest_only)
        if not files:
            print(f"{dataset:24} 無 raw 檔，略過")
            skipped += 1
            continue
        canonical = canonicalize_dataset(dataset)
        t0 = time.time()
        rows_in = rows_out = rows_rejected = 0
        errors = 0
        for path in files:
            key = _output_key(dataset, path.stem.split("_", 1)[0])
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                records = (
                    payload["records"]
                    if isinstance(payload, dict) and "records" in payload
                    else payload
                )
                result = run_transform(
                    canonical,
                    records,
                    resolver=resolver if dataset_requires_resolver(canonical) else None,
                    fetched_at=payload.get("fetched_at") if isinstance(payload, dict) else None,
                    config_dir=ROOT / "config",
                )
                enriched, resolution = enrich_curated_records(
                    result.records,
                    dataset=canonical,
                    raw_payload=payload if isinstance(payload, dict) else {"records": payload},
                    registry=registry,
                )
                result.records = enriched
                result.quality["source_resolution"] = resolution
                write_curated(result, dataset=canonical, output_dir=sandbox, period=key)
                rows_in += int(result.quality.get("rows_in") or 0)
                rows_out += int(result.quality.get("rows_out") or 0)
                rows_rejected += int(result.quality.get("rows_rejected") or 0)
            except Exception as exc:  # noqa: BLE001 - report and continue the sweep
                errors += 1
                failures.append((dataset, key, f"{type(exc).__name__}: {exc}"))
        elapsed = time.time() - t0
        for field, value in (("rows_in", rows_in), ("rows_out", rows_out), ("rows_rejected", rows_rejected)):
            totals[field] += value
        flag = f"  ⚠ {errors} 個分區失敗" if errors else ""
        print(
            f"{dataset:24}{len(files):4} 分區{elapsed:7.1f}s  "
            f"in {rows_in:>9,}  out {rows_out:>9,}  rejected {rows_rejected:>7,}{flag}"
        )
        ok += 1

    print("-" * 88)
    print(
        f"{'合計':24}{'':9}{time.time() - started:7.1f}s  "
        f"in {totals['rows_in']:>9,}  out {totals['rows_out']:>9,}  "
        f"rejected {totals['rows_rejected']:>7,}"
    )
    print(f"\n完成 {ok} 個 dataset，略過 {skipped} 個，輸出於 {sandbox}")
    if failures:
        print(f"\n失敗 {len(failures)} 個分區:")
        for dataset, key, why in failures[:20]:
            print(f"  {dataset}/{key}: {why[:110]}")
        if len(failures) > 20:
            print(f"  ... 另有 {len(failures) - 20} 個")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
