import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.national_population import transform_national_population  # noqa: E402
from transform.pipeline import dataset_requires_resolver, run_transform  # noqa: E402


def village_row(code, site_id, *, total="100", male_18="1", female_35="1", period="11412"):
    row = {
        "statistic_yyymm": period,
        "district_code": code,
        "site_id": site_id,
        "village": "測試里",
        "people_total": total,
    }
    for age in range(0, 101):
        row[f"people_age_{age:03d}_m"] = "0"
        row[f"people_age_{age:03d}_f"] = "0"
    row["people_age_017_m"] = "50"
    row["people_age_036_f"] = "50"
    row["people_age_018_m"] = male_18
    row["people_age_035_f"] = female_35
    return row


class TestTransformNationalPopulation(unittest.TestCase):
    def test_sums_villages_across_counties_into_one_national_month(self):
        rows = [
            village_row("65000010001", "新北市板橋區", total="1,000", male_18="2", female_35="3"),
            village_row("63000010001", "臺北市松山區", total="500", male_18="4", female_35="5"),
            village_row("10002010001", "宜蘭縣宜蘭市", total="200", male_18="1", female_35="0"),
        ]

        result = transform_national_population(rows, fetched_at="2026-09-13T00:00:00+00:00")

        metrics = {row["metric_id"]: row for row in result.records}
        self.assertEqual(metrics["people_total"]["value"], 1700)
        self.assertEqual(metrics["youth_18_35_male"]["value"], 7)
        self.assertEqual(metrics["youth_18_35_female"]["value"], 8)
        # 17- and 36-year-olds are excluded.
        self.assertEqual(metrics["youth_18_35_total"]["value"], 15)
        total = metrics["youth_18_35_total"]
        self.assertEqual(total["geo_level"], "national")
        self.assertIsNone(total["district_id"])
        self.assertEqual(total["age_scope"], "derived_18_35")
        self.assertEqual(total["youth_eligibility"], "eligible")
        self.assertEqual(total["period_start"], "2025-12-01")
        self.assertEqual(total["period_end"], "2025-12-31")
        self.assertEqual(total["village_count"], 3)
        self.assertEqual(total["quality_flags"], [])
        self.assertNotIn("raw_records", total)
        self.assertEqual(result.quality["rows_in"], 3)
        self.assertEqual(result.quality["rows_out"], 4)
        self.assertEqual(result.quarantine, [])

    def test_duplicate_village_rows_are_counted_once(self):
        row = village_row("65000010001", "新北市板橋區", male_18="2", female_35="3")

        result = transform_national_population([row, dict(row)])

        metrics = {item["metric_id"]: item for item in result.records}
        self.assertEqual(metrics["youth_18_35_total"]["value"], 5)
        self.assertEqual(metrics["youth_18_35_total"]["village_count"], 1)
        self.assertEqual(result.quality["duplicate_count"], 1)
        self.assertEqual(metrics["youth_18_35_total"]["quality_flags"], [])

    def test_rejected_village_flags_every_output_as_incomplete(self):
        good = village_row("65000010001", "新北市板橋區", male_18="2", female_35="3")
        bad = village_row("63000010001", "臺北市松山區", male_18="not-a-number")

        result = transform_national_population([good, bad])

        self.assertEqual(len(result.quarantine), 1)
        self.assertIn("incomplete_national_coverage", result.quality["warnings"])
        self.assertTrue(result.records)
        for record in result.records:
            self.assertEqual(record["quality_flags"], ["incomplete_coverage"])

    def test_registered_as_plain_transform_without_district_resolver(self):
        self.assertFalse(dataset_requires_resolver("national_population"))

        result = run_transform(
            "national_population",
            {"records": [village_row("65000010001", "新北市板橋區")], "fetched_at": "2026-09-13T00:00:00+00:00"},
        )

        self.assertEqual([row["metric_id"] for row in result.records][-1], "youth_18_35_total")
        self.assertEqual(result.records[0]["fetched_at"], "2026-09-13T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
