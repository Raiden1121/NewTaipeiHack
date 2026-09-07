import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
CONFIG_PATH = PROJECT_DIR / "data-pipeline" / "config" / "districts.json"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.geography import DistrictResolver  # noqa: E402
from transform.transport import transform_bike_stops, transform_bus_stops, transform_railway_stops  # noqa: E402


class TestTransformTransport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resolver = DistrictResolver.from_json(CONFIG_PATH)

    def test_bus_stop_normalizes_nested_fields_and_assigns_district(self):
        raw = {
            "StopUID": "NWT1001",
            "StopID": "1001",
            "StopName": {"Zh_tw": "板橋站", "En": "Banqiao Stop"},
            "StopPosition": {"PositionLat": 25.0114, "PositionLon": 121.4618},
            "Operators": [{"OperatorID": "1", "OperatorName": {"Zh_tw": "測試客運"}}],
        }

        result = transform_bus_stops([raw], resolver=self.resolver)

        record = result.records[0]
        self.assertEqual(record["station_id"], "NWT1001")
        self.assertEqual(record["name_zh"], "板橋站")
        self.assertEqual(record["name_en"], "Banqiao Stop")
        self.assertEqual(record["latitude"], 25.0114)
        self.assertEqual(record["longitude"], 121.4618)
        self.assertEqual(record["district_id"], "65000010")
        self.assertIsInstance(record["operators"], list)
        self.assertEqual(record["age_scope"], "not_age_specific")

    def test_invalid_coordinate_is_quarantined(self):
        raw = {
            "StopUID": "NWT-BAD",
            "StopPosition": {"PositionLat": True, "PositionLon": 121.5},
        }

        result = transform_bus_stops([raw], resolver=self.resolver)

        self.assertEqual(result.records, [])
        self.assertEqual(result.quarantine[0]["reason"], "invalid_coordinates")
        self.assertEqual(result.quality["rows_rejected"], 1)

    def test_outside_point_is_retained_unmapped_without_nearest_fallback(self):
        raw = {
            "StationUID": "TRA1001",
            "StationName": {"Zh_tw": "區外站"},
            "StationPosition": {"PositionLat": 24.0, "PositionLon": 120.0},
            "rail_system": "TRA",
            "transport_type": "rail",
            "line_ids": ["WL"],
            "line_nos": ["1"],
        }

        result = transform_railway_stops([raw], resolver=self.resolver)

        record = result.records[0]
        self.assertIsNone(record["district_id"])
        self.assertIsNone(record["district_name"])
        self.assertEqual(record["line_ids"], ["WL"])
        self.assertEqual(record["line_nos"], ["1"])
        self.assertIn("unmapped_district", record["quality_flags"])
        self.assertEqual(result.quality["unmapped_district_count"], 1)

    def test_bike_stop_preserves_static_and_live_availability_separately(self):
        availability = {
            "StationUID": "NWT-B-1",
            "AvailableRentBikes": 3,
            "AvailableReturnBikes": 5,
            "UpdateTime": "2026-09-01T10:00:00+08:00",
        }
        raw = {
            "StationUID": "NWT-B-1",
            "StationName": {"Zh_tw": "測試YouBike"},
            "StationPosition": {"PositionLat": 25.0114, "PositionLon": 121.4618},
            "BikesCapacity": 20,
            "Availability": availability,
        }

        result = transform_bike_stops([raw], resolver=self.resolver)

        record = result.records[0]
        self.assertEqual(record["capacity"], 20)
        self.assertEqual(record["availability"], availability)
        self.assertNotIn("Availability", record["static_data"])
        self.assertEqual(record["available_rent_bikes"], 3)
        self.assertEqual(record["available_return_bikes"], 5)

    def test_invalid_bike_numeric_field_is_quarantined_without_aborting_batch(self):
        valid = {
            "StationUID": "NWT-B-GOOD",
            "StationPosition": {"PositionLat": 25.0114, "PositionLon": 121.4618},
            "BikesCapacity": 20,
        }
        malformed = {
            "StationUID": "NWT-B-BAD",
            "StationPosition": {"PositionLat": 25.0114, "PositionLon": 121.4618},
            "BikesCapacity": "unknown",
        }

        result = transform_bike_stops([valid, malformed], resolver=self.resolver)

        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["station_id"], "NWT-B-GOOD")
        self.assertEqual(result.quality["rows_rejected"], 1)
        self.assertIn("invalid_value", result.quarantine[0]["reason"])


if __name__ == "__main__":
    unittest.main()
