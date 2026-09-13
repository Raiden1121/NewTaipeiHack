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
from analytics.homepage import (  # noqa: E402
    _shrink_to_city,
    generate_homepage_data,
    write_homepage_data,
)
from analytics.io import CuratedSlice  # noqa: E402
from analytics.homepage_math import normalize_minmax  # noqa: E402


class FakeHomepageResolver:
    def __init__(self):
        self.districts = [
            {"district_id": f"65000{index:03d}0", "district_name": f"第{index}區"}
            for index in range(1, 30)
        ]
        # period -> (youth_18_35_total, quality_flags); empty means no national data.
        self.national_youth_by_period = {}

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
        if dataset == "national_population":
            if period not in self.national_youth_by_period:
                return []
            value, flags = self.national_youth_by_period[period]
            year = int(period[:3]) + 1911
            month = int(period[3:])
            return [
                {
                    "metric_id": "youth_18_35_total",
                    "geo_level": "national",
                    "district_id": None,
                    "period_start": f"{year:04d}-{month:02d}-01",
                    "value": value,
                    "quality_flags": list(flags),
                }
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


class RecordingHomepageResolver(FakeHomepageResolver):
    """Records requested periods and can withhold a year the source lacks."""

    def __init__(self, unavailable_years=()):
        super().__init__()
        self.requested_population_periods = []
        self.requested_village_population_periods = []
        self.requested_college_periods = []
        self._unavailable_years = {f"{year:03d}" for year in unavailable_years}

    def available_periods(self, dataset, periods):
        if dataset == "population":
            self.requested_population_periods.extend(periods)
            periods = [
                period for period in periods if period[:3] not in self._unavailable_years
            ]
            if not periods:
                raise ValueError("dataset 'population' has no available requested periods")
        if dataset == "population_villages":
            self.requested_village_population_periods.extend(periods)
        if dataset == "college_majors":
            self.requested_college_periods.extend(periods)
        return super().available_periods(dataset, periods)

    def _all_records(self, dataset):
        records = super()._all_records(dataset)
        if dataset != "elections":
            return records
        # The shared fixture only covers ROC 111; earlier elections are what
        # make the out-of-window denominator observable.
        return records + [
            {
                "source_code": "T1",
                "election_type": "city_councilor",
                "election_roc_year": str(year),
                "election_district_code": "01",
                "election_district_name": "第一選區",
                "election_date": f"{year + 1911}-11-29",
                "birth_date": f"{year + 1911 - 30}-01-01",
            }
            for year in (103, 107)
        ]


class TestHomepageAnalytics(unittest.TestCase):
    def test_uses_refactored_yoi_weights(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"

        config = load_homepage_analytics_config(config_path)

        self.assertEqual(
            config.yoi_weights,
            {
                "job": 0.25,
                "salary": 0.25,
                "talent": 0.15,
                "housing": 0.20,
                "transport": 0.15,
            },
        )
        self.assertEqual(config.salary_shrinkage_k, 30.0)

    def test_salary_median_uses_city_prior_for_small_samples_and_zero_rows(self):
        self.assertAlmostEqual(
            _shrink_to_city(
                district_value=38000,
                sample_size=4,
                city_value=35000,
                strength=30,
            ),
            (4 * 38000 + 30 * 35000) / 34,
        )
        self.assertEqual(
            _shrink_to_city(
                district_value=None,
                sample_size=0,
                city_value=35000,
                strength=30,
            ),
            35000,
        )

    def test_refactored_yoi_uses_area_salary_and_population_components(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)
        resolver = RecordingHomepageResolver()

        result = generate_homepage_data(resolver=resolver, config=config)
        first = result["current_yoi"]["districts"][0]
        normalized = first["normalizedInputs"]

        self.assertEqual(resolver.requested_college_periods, ["114"])
        self.assertIn("vacancies_per_km2", normalized)
        self.assertIn("youth_ratio", normalized)
        self.assertIn("youth_yoy", normalized)
        self.assertEqual(result["time_policy"]["yoi_normalization"], "min_max")
        self.assertEqual(result["time_policy"]["salary_shrinkage_k"], 30.0)

        expected_job = (
            0.60 * normalized["vacancies_per_km2"]
            + 0.40 * normalized["occupation_shannon_index"]
        )
        expected_salary = (
            0.60 * normalized["salary_median_shrunk"]
            + 0.40 * normalized["high_salary_ratio"]
        )
        expected_talent = (
            0.40 * normalized["youth_ratio"]
            + 0.40 * normalized["youth_yoy"]
            + 0.20 * normalized["college_student_density"]
        )
        self.assertAlmostEqual(first["yoiComponents"]["job"], expected_job)
        self.assertAlmostEqual(first["yoiComponents"]["salary"], expected_salary)
        self.assertAlmostEqual(first["yoiComponents"]["talent"], expected_talent)

        self.assertEqual(first["salary_sample_size"], 1)
        self.assertAlmostEqual(first["salary_median"], 100000)
        expected_smoothed = (1 * 100000 + 30 * 40016) / 31
        self.assertAlmostEqual(first["salary_median_shrunk"], expected_smoothed)

        salary_values = {
            row["district_id"]: row["salary_median_shrunk"]
            for row in result["current_yoi"]["districts"]
        }
        expected_salary_norm = normalize_minmax(salary_values)
        for row in result["current_yoi"]["districts"]:
            self.assertAlmostEqual(
                row["normalizedInputs"]["salary_median_shrunk"],
                expected_salary_norm[row["district_id"]],
            )

    def test_opportunity_index_is_normalized_from_yoi_raw(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)

        result = generate_homepage_data(resolver=FakeHomepageResolver(), config=config)
        rows = result["current_yoi"]["districts"]
        self.assertTrue(all("yoiRaw" in row for row in rows))
        first = rows[0]
        components = first["yoiComponents"]
        expected_raw = (
            0.25 * components["job"]
            + 0.25 * components["salary"]
            + 0.15 * components["talent"]
            + 0.20 * components["housing"]
            + 0.15 * components["transport"]
        )
        self.assertAlmostEqual(first["yoiRaw"], expected_raw)

        self.assertAlmostEqual(
            min(row["opportunityIndex"] for row in rows),
            0.0,
            places=6,
        )
        self.assertAlmostEqual(
            max(row["opportunityIndex"] for row in rows),
            100.0,
            places=6,
        )

    def test_uses_explicit_village_population_reference_period(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)
        resolver = RecordingHomepageResolver()

        generate_homepage_data(resolver=resolver, config=config)

        self.assertEqual(resolver.requested_village_population_periods, ["11507"])
        self.assertIn("11401", resolver.requested_population_periods)
        self.assertEqual(config.population_reference_year_roc, 114)

    def test_loads_population_for_election_years_outside_the_annual_window(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)
        resolver = RecordingHomepageResolver()

        result = generate_homepage_data(resolver=resolver, config=config)

        requested = set(resolver.requested_population_periods)
        # 103 and 107 are election years well outside annual_years_roc 110-114.
        for year in config.election_years_roc:
            self.assertIn(f"{year:03d}01", requested)
        by_year = {
            row["election_year_roc"]: row
            for row in result["elections"]["city_councilor_t1_citywide"]
        }
        for year in config.election_years_roc:
            self.assertIsNotNone(by_year[year]["youth_population_18_35"], year)

    def test_election_year_without_published_population_stays_unavailable(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)
        # ODRP014 publishes nothing before ROC 107, so 103 must degrade rather
        # than fail the run.
        resolver = RecordingHomepageResolver(unavailable_years=(103,))

        result = generate_homepage_data(resolver=resolver, config=config)

        by_year = {
            row["election_year_roc"]: row
            for row in result["elections"]["city_councilor_t1_citywide"]
        }
        # 103 keeps the counts it can prove and reports the missing denominator
        # instead of disappearing or borrowing another year's population.
        self.assertEqual(by_year[103]["quality_status"], "unavailable")
        self.assertIsNone(by_year[103]["youth_population_18_35"])
        self.assertIsNone(by_year[103]["youth_candidacy_rate"])
        self.assertEqual(by_year[103]["youth_candidate_count"], 1)
        # 107 is published, so it must be fully observed.
        self.assertEqual(by_year[107]["quality_status"], "observed")
        self.assertIsNotNone(by_year[107]["youth_population_18_35"])
        self.assertIsNotNone(by_year[107]["youth_candidacy_rate"])

    def test_high_salary_ratio_uses_all_vacancy_positions_as_denominator(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)

        result = generate_homepage_data(resolver=FakeHomepageResolver(), config=config)

        first = result["current_yoi"]["districts"][0]
        self.assertAlmostEqual(first["high_salary_ratio"], 10 / 101)

    def test_national_youth_population_uses_national_dataset_for_city_month(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)
        resolver = FakeHomepageResolver()
        # The fake city population covers every month, so the city KPI month is 11412.
        resolver.national_youth_by_period = {"11406": (5_100_000, []), "11412": (5_000_000, [])}

        result = generate_homepage_data(resolver=resolver, config=config)

        self.assertEqual(result["kpi"]["nationalYouthPopulation"], 5_000_000)
        self.assertEqual(result["kpi"]["nationalYouthPopulationQuality"], "observed")
        self.assertNotIn(
            "national_youth_population",
            [row["metric"] for row in result["_quality"]["proxy_usage"]],
        )

    def test_national_youth_population_falls_back_to_proxy_without_complete_data(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / "homepage_analytics.json"
        config = load_homepage_analytics_config(config_path)
        for national in ({}, {"11412": (5_000_000, ["incomplete_coverage"])}):
            resolver = FakeHomepageResolver()
            resolver.national_youth_by_period = national

            result = generate_homepage_data(resolver=resolver, config=config)

            self.assertEqual(result["kpi"]["nationalYouthPopulation"], 4_820_000)
            self.assertEqual(result["kpi"]["nationalYouthPopulationQuality"], "proxy")
            self.assertIn(
                {
                    "metric": "national_youth_population",
                    "reason": "homepage_fallback_constant",
                    "value": 4_820_000,
                },
                result["_quality"]["proxy_usage"],
            )

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
