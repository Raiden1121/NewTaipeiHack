import json
import sys
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import mapping, box


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import load_homepage_analytics_config  # noqa: E402
from analytics.homepage import generate_homepage_data, write_homepage_data  # noqa: E402
from analytics.io import CuratedSlice  # noqa: E402


class FakeHomepageResolver:
    def __init__(self):
        self.districts = [
            {"district_id": f"65000{index:03d}0", "district_name": f"第{index}區"}
            for index in range(1, 30)
        ]

    def available_periods(self, dataset, periods):
        records = []
        for period in periods:
            records.extend(self._period_records(dataset, period))
        return CuratedSlice(
            dataset,
            "month" if len(periods[0]) == 5 else "annual",
            tuple(periods),
            tuple(records),
            tuple(f"curated/{dataset}/{period}.json" for period in periods),
        )

    def latest(self, dataset):
        records = self._latest_records(dataset)
        return CuratedSlice(
            dataset,
            "snapshot",
            ("11509",),
            tuple(records),
            (f"curated/{dataset}/latest.json",),
        )

    def all_available(self, dataset):
        records = self._all_records(dataset)
        return CuratedSlice(
            dataset,
            "mixed",
            ("all",),
            tuple(records),
            (f"curated/{dataset}/all.json",),
        )

    def _period_records(self, dataset, period):
        if dataset == "population":
            year = int(period[:3]) + 1911
            month = int(period[3:])
            rows = []
            for index, district in enumerate(self.districts, start=1):
                for metric, value in (
                    ("people_total", 100000 + index),
                    ("youth_18_35_total", 20000 + index),
                    ("youth_18_35_female", 10000 + index),
                ):
                    rows.append(
                        {
                            "metric_id": metric,
                            "district_id": district["district_id"],
                            "district_name": district["district_name"],
                            "period_start": f"{year:04d}-{month:02d}-01",
                            "period_end": f"{year:04d}-{month:02d}-28",
                            "value": value,
                        }
                    )
            return rows
        if dataset == "population_villages":
            year = int(period[:3]) + 1911
            month = int(period[3:])
            return [
                {
                    "village_code": "65000010001",
                    "village_name": "測試里",
                    "district_id": self.districts[0]["district_id"],
                    "district_name": self.districts[0]["district_name"],
                    "period_start": f"{year:04d}-{month:02d}-01",
                    "period_end": f"{year:04d}-{month:02d}-28",
                    "youth_18_35_total": 500,
                }
            ]
        if dataset == "births":
            year = int(period) + 1911
            return [
                {
                    "metric_id": "births_mother_age_18_35",
                    "district_id": district["district_id"],
                    "period_start": f"{year:04d}-01-01",
                    "value": 100 + index,
                }
                for index, district in enumerate(self.districts, start=1)
            ]
        if dataset == "wages":
            year = int(period) + 1911
            return [
                {
                    "period_start": f"{year:04d}-01-01",
                    "official_age_group": "25-29歲",
                    "statistic_method": "平均數",
                    "value": 600000,
                }
            ]
        if dataset == "college_majors":
            return [
                {
                    "district_id": district["district_id"] if index <= 3 else None,
                    "student_count": 1000 if index <= 3 else None,
                    "period_start": f"{int(period) + 1911}-08-01",
                }
                for index, district in enumerate(self.districts, start=1)
            ]
        raise AssertionError(f"unexpected period dataset: {dataset}")

    def _latest_records(self, dataset):
        if dataset == "job_vacancies":
            return [
                {
                    "district_id": district["district_id"],
                    "geo_level": "district",
                    "position_count": 100 + index,
                    "raw_record": {
                        "職務大類別名稱": "專業人員" if index % 2 else "技術員",
                        "EDGRDESC（最低學歷要求）": "大學" if index % 2 else "高中",
                    },
                }
                for index, district in enumerate(self.districts, start=1)
            ]
        if dataset == "job_vacancy_salaries":
            return [
                {
                    "district_id": district["district_id"],
                    "position_count": 10,
                    "salary_lower": 30000,
                    "salary_upper": 50000,
                    "salary_midpoint": 100000 if index == 1 else 40000 + index,
                }
                for index, district in enumerate(self.districts, start=1)
            ]
        if dataset == "rentals":
            return [
                {"district_id": self.districts[0]["district_id"], "rent_total": 15000}
            ]
        if dataset == "house_prices":
            return [
                {
                    "district_id": district["district_id"],
                    "price_per_ping": 300000 + index * 1000,
                    "transaction_type": "住宅用",
                }
                for index, district in enumerate(self.districts, start=1)
            ]
        if dataset == "bus_stops":
            return [{"district_id": district["district_id"]} for district in self.districts]
        if dataset == "railway_stops":
            return [{"district_id": self.districts[0]["district_id"]}]
        if dataset == "bike_stops":
            return [{"district_id": district["district_id"]} for district in self.districts]
        if dataset == "vt_courses":
            return [
                {"district_id": self.districts[0]["district_id"], "value": 32},
                {"district_id": self.districts[1]["district_id"], "value": 42},
            ]
        if dataset == "training_numbers":
            return [{"training_people": 10000}]
        if dataset == "village_boundaries":
            rows = []
            for index, district in enumerate(self.districts, start=1):
                polygon = box(100000 + index * 10000, 2700000, 100000 + index * 10000 + 9000, 2709000)
                rows.append(
                    {
                        "village_code": f"65000{index:03d}001",
                        "district_id": district["district_id"],
                        "geometry": mapping(polygon),
                        "geometry_crs": "EPSG:3826",
                    }
                )
            return rows
        if dataset == "youth_service_points":
            return [
                {
                    "point_type": "startup_base",
                    "district_id": self.districts[0]["district_id"],
                    "x_3826": 110000,
                    "y_3826": 2704500,
                    "geocode_status": "matched",
                },
                {"point_type": "startup_base", "geocode_status": "excluded_no_verified_coordinate"},
            ]
        raise AssertionError(f"unexpected latest dataset: {dataset}")

    def _all_records(self, dataset):
        if dataset == "youth_budgets":
            return [
                {
                    "budget_year_roc": str(year),
                    "row_type": "total",
                    "document_status": "legal_budget",
                    "budget_amount": 100000 + year,
                    "unit": "TWD_thousand",
                }
                for year in range(110, 115)
            ] + [
                {
                    "budget_year_roc": "113",
                    "row_type": "total",
                    "document_status": "final_settlement",
                    "realized_amount": 90000,
                    "settlement_amount": 90000,
                }
            ]
        if dataset == "elections":
            return [
                {
                    "source_code": "T1",
                    "election_type": "city_councilor",
                    "election_roc_year": "111",
                    "election_district_code": "01",
                    "election_district_name": "第一選區",
                    "election_date": "2022-11-26",
                    "birth_date": "1990-01-01",
                },
                {
                    "source_code": "V1",
                    "election_type": "borough_chief",
                    "election_roc_year": "111",
                    "district_id": self.districts[0]["district_id"],
                    "district_name": self.districts[0]["district_name"],
                    "election_date": "2022-11-26",
                    "birth_year_roc": "080",
                },
            ]
        if dataset == "talent_demand":
            return [
                {"period_start": "2024-01-01", "new_demand_count": 100},
                {"period_start": "2025-01-01", "new_demand_count": 120},
            ]
        raise AssertionError(f"unexpected all dataset: {dataset}")


class TestHomepageAnalytics(unittest.TestCase):
    def test_high_salary_ratio_uses_all_vacancy_positions_as_denominator(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)

        result = generate_homepage_data(resolver=FakeHomepageResolver(), config=config)

        first = result["current_yoi"]["districts"][0]
        self.assertAlmostEqual(first["high_salary_ratio"], 10 / 101)

    def test_generates_homepage_contract_and_writes_finite_json(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)

        result = generate_homepage_data(resolver=FakeHomepageResolver(), config=config)

        self.assertEqual(len(result["current_yoi"]["districts"]), 29)
        self.assertEqual([row["year_roc"] for row in result["annual"]["population"]["years"]], [110, 111, 112, 113, 114])
        self.assertEqual([row["year_roc"] for row in result["annual"]["fertility"]["years"]], [110, 111, 112, 113, 114])
        self.assertEqual([row["year_roc"] for row in result["annual"]["budget_trend"]], [110, 111, 112, 113, 114])
        self.assertIsNone(result["elections"]["city_councilor_t1"][0]["district_id"])
        self.assertEqual(result["elections"]["borough_chief_v1"][0]["district_id"], "650000010")
        self.assertEqual(result["service_coverage"]["status"], "partial")
        self.assertGreater(result["service_coverage"]["excluded_point_count"], 0)

        def assert_finite(value):
            if isinstance(value, dict):
                for item in value.values():
                    assert_finite(item)
            elif isinstance(value, list):
                for item in value:
                    assert_finite(item)
            elif isinstance(value, float):
                self.assertTrue(value == value)
                self.assertNotEqual(value, float("inf"))
                self.assertNotEqual(value, float("-inf"))

        assert_finite(result)
        with tempfile.TemporaryDirectory() as tempdir:
            output_path, quality_path = write_homepage_data(result, output_dir=tempdir)
            self.assertTrue(output_path.is_file())
            self.assertTrue(quality_path.is_file())
            json.loads(output_path.read_text(encoding="utf-8"))
            json.loads(quality_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
