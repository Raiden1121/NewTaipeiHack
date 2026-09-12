"""Rebuild config/reference/babysitting_places_locations.json from the raw roster.

Reads the newest raw babysitting snapshot, applies the curated address
corrections, matches every address against the official New Taipei door-plate
file, and writes the coordinate reference the transform consumes.

    python scripts/refresh_babysitting_locations.py [--zip path/to/address_points.zip]

Passing --zip reuses an already downloaded copy of the door-plate ZIP instead of
fetching it again; without it the file is downloaded from data.ntpc.gov.tw.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from collectors.ntpc_address_points import (  # noqa: E402
    NTPC_ADDRESS_POINTS_URL,
    match_ntpc_address_points,
)

RAW_DIR = ROOT / "data" / "raw" / "babysitting_places"
REFERENCE_DIR = ROOT / "config" / "reference"
CORRECTIONS_PATH = REFERENCE_DIR / "babysitting_places_address_corrections.json"
OUTPUT_PATH = REFERENCE_DIR / "babysitting_places_locations.json"


def _source_record_id(row: dict) -> str:
    return f"babysitting_places:{row['care_type']}:{row['source_dataset_id']}:{row['no']}"


def _full_address(row: dict) -> str:
    area = str(row.get("area") or row.get("town") or "").replace("新北市", "")
    address = str(row.get("address") or "").strip()
    return address if address.startswith("新北市") else f"新北市{area}{address}"


def _latest_raw() -> Path:
    snapshots = sorted(RAW_DIR.glob("*.json"))
    if not snapshots:
        raise SystemExit(f"no raw babysitting snapshot under {RAW_DIR}")
    return snapshots[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", dest="zip_path", default=None)
    args = parser.parse_args()

    raw_path = _latest_raw()
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    rows = raw["records"]

    corrections = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    by_id = {item["source_record_id"]: item for item in corrections["records"]}

    requests = []
    manual: list[dict] = []
    stale: list[str] = []
    seen_overrides: set[str] = set()
    for row in rows:
        record_id = _source_record_id(row)
        override = by_id.get(record_id)
        address = _full_address(row)
        if override is not None:
            seen_overrides.add(record_id)
            # The corrections are pinned to the address they were written for.
            # If the upstream roster fixes or edits one, the override must be
            # re-checked rather than silently masking the new value.
            if str(row.get("address") or "").strip() != override["source_address"]:
                stale.append(
                    f"{record_id}: expected {override['source_address']!r}, "
                    f"source now {str(row.get('address') or '').strip()!r}"
                )
                continue
            address = override["corrected_address"]
            if override.get("latitude") is not None:
                manual.append({**override, "address": address})
                continue
        requests.append({"point_id": record_id, "address": address, "areacode": row.get("areacode")})

    open_url = None
    if args.zip_path:
        payload = Path(args.zip_path).read_bytes()

        class _Cached:
            def read(self, _limit): return payload
            def close(self): pass

        def open_url(_request, timeout=None):  # noqa: ARG001
            return _Cached()

    result = (
        match_ntpc_address_points(requests, open_url=open_url)
        if open_url
        else match_ntpc_address_points(requests)
    )

    verified_at = datetime.now(timezone.utc).date().isoformat()
    records = []
    for match in result.matches:
        override = by_id.get(match["point_id"])
        records.append(
            {
                "source_record_id": match["point_id"],
                "address": match["address"],
                "geocode_query": match["address"],
                "x_3826": round(float(match["x_3826"]), 4),
                "y_3826": round(float(match["y_3826"]), 4),
                "geocode_provider": "ntpc_address_points",
                "geocode_crs": "EPSG:3826",
                "geocode_source_url": NTPC_ADDRESS_POINTS_URL,
                "geocode_source_period": "latest",
                "source_type": (
                    "official_address_point_corrected"
                    if override
                    else "official_address_point"
                ),
                "verified_at": verified_at,
                **({"correction_reason": override["reason"]} if override else {}),
            }
        )
    for item in manual:
        records.append(
            {
                "source_record_id": item["source_record_id"],
                "address": item["address"],
                "geocode_query": item["address"],
                "latitude": item["latitude"],
                "longitude": item["longitude"],
                "geocode_provider": item.get("source_id", "manual"),
                "geocode_crs": "EPSG:4326",
                "geocode_source_url": next(
                    (s["url"] for s in corrections["sources"] if s["id"] == item.get("source_id")),
                    "",
                ),
                "geocode_source_period": "latest",
                "source_type": "manual_reference",
                "verified_at": verified_at,
                "correction_reason": item["reason"],
            }
        )

    records.sort(key=lambda row: row["source_record_id"])
    payload = {
        "schema_version": 1,
        "description": (
            "托嬰機構地址與新北市官方門牌點座標固定參照。"
            "未匹配來源保留 curated，但不納入空間覆蓋率。"
        ),
        "source_url": NTPC_ADDRESS_POINTS_URL,
        "matching_policy": "district_scoped_tiered_address_components",
        "matched_count": len(records),
        "requested_count": len(rows),
        "records": records,
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    missing_overrides = sorted(set(by_id) - seen_overrides)
    unmatched = len(rows) - len(records)
    print(f"raw snapshot : {raw_path.name} ({len(rows)} rows)")
    print(f"matched      : {len(records)} ({len(records) / len(rows) * 100:.1f}%)")
    print(f"unmatched    : {unmatched}")
    print(f"written      : {OUTPUT_PATH.relative_to(ROOT)}")
    for line in stale:
        print(f"STALE OVERRIDE: {line}")
    for record_id in missing_overrides:
        print(f"UNUSED OVERRIDE: {record_id} is no longer in the raw snapshot")
    return 1 if (stale or missing_overrides) else 0


if __name__ == "__main__":
    raise SystemExit(main())
