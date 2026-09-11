import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.village_boundaries import fetch_village_boundaries  # noqa: E402
from transform.village_boundaries import transform_village_boundaries  # noqa: E402


class _Response:
    def __init__(self, content):
        self.content = content

    def read(self, _limit):
        return self.content

    def close(self):
        pass


class TestVillageBoundaries(unittest.TestCase):
    def test_transform_keeps_new_taipei_polygon_and_crs(self):
        polygon = {
            "type": "Polygon",
            "coordinates": [[[300000, 2750000], [300100, 2750000], [300100, 2750100], [300000, 2750000]]],
        }
        result = transform_village_boundaries(
            [
                {
                    "properties": {
                        "COUNTYCODE": "65",
                        "ADMIV_ID": "65000010001",
                        "ADMIT_ID": "65000010",
                        "ADMIV_NA": "甲里",
                        "ADMIT_NA": "板橋區",
                    },
                    "geometry": polygon,
                },
                {
                    "properties": {
                        "COUNTYCODE": "63",
                        "ADMIV_ID": "63000010001",
                        "ADMIT_ID": "63000010",
                        "ADMIV_NA": "其他里",
                        "ADMIT_NA": "臺北市",
                    },
                    "geometry": polygon,
                },
            ],
            fetched_at="2026-09-11T00:00:00+00:00",
        )

        self.assertEqual(len(result.records), 1)
        row = result.records[0]
        self.assertEqual(row["village_code"], "65000010001")
        self.assertEqual(row["district_id"], "65000010")
        self.assertEqual(row["crs"], "EPSG:3826")
        self.assertEqual(row["geometry"]["type"], "Polygon")
        self.assertEqual(result.quality["reject_reasons"], {"outside_new_taipei": 1})

    def test_invalid_geometry_and_duplicate_are_quarantined(self):
        base = {
            "properties": {
                "COUNTYCODE": "65",
                "ADMIV_ID": "65000010001",
                "ADMIT_ID": "65000010",
                "ADMIV_NA": "甲里",
            },
            "geometry": {"type": "Polygon", "coordinates": [[[1, 1], [2, 1], [1, 1]]]},
        }
        result = transform_village_boundaries([base, base, {"properties": base["properties"]}])

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.quality["reject_reasons"]["duplicate_village_code"], 1)
        self.assertEqual(result.quality["reject_reasons"]["missing_geometry_or_properties"], 1)

    def test_collector_preserves_downloaded_zip_as_source_artifact(self):
        content = b"fake zip bytes"
        records = [{"properties": {"ADMIV_ID": "65000010001"}, "geometry": {"type": "Polygon", "coordinates": []}}]
        with patch(
            "collectors.village_boundaries._parse_shapefile",
            return_value=(records, ["village.shp", "village.dbf"]),
        ) as parse:
            result = fetch_village_boundaries(open_url=lambda request, timeout: _Response(content))

        parse.assert_called_once_with(content)
        self.assertEqual(result.metadata["source_crs"], "EPSG:3826")
        self.assertEqual(result.records, records)
        self.assertEqual(result.artifacts[0].media_type, "application/zip")
        self.assertEqual(result.artifacts[0].sha256, "sha256:" + hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    unittest.main()
