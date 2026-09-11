import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from transform.common import (  # noqa: E402
    TransformValueError,
    build_common_metadata,
    build_source_record_id,
    clean_text,
    parse_decimal,
    parse_int,
    parse_roc_date,
    parse_roc_month,
    parse_roc_year,
)


class TestTransformCommon(unittest.TestCase):
    def test_clean_text_normalizes_unicode_and_whitespace(self):
        self.assertEqual(clean_text("　板橋區  "), "板橋區")
        self.assertEqual(clean_text("ＡＢＣ"), "ABC")
        for token in (None, "", "-", "—", "－", "NA", "N/A", "無", "面議"):
            with self.subTest(token=token):
                self.assertIsNone(clean_text(token))

    def test_numeric_parsers_accept_commas_and_preserve_missing_as_none(self):
        self.assertEqual(parse_int("1,234", field="people"), 1234)
        self.assertEqual(parse_decimal("1,234.5", field="price"), 1234.5)
        self.assertIsNone(parse_int("面議", field="salary"))
        self.assertIsNone(parse_decimal("N/A", field="price"))

    def test_numeric_parsers_reject_invalid_or_negative_values(self):
        for value in (True, "12.5", "abc", -1):
            with self.subTest(value=value):
                with self.assertRaises(TransformValueError):
                    parse_int(value, field="people")
        with self.assertRaises(TransformValueError):
            parse_decimal("-0.1", field="price")
        with self.assertRaises(TransformValueError):
            parse_int(None, field="people", allow_none=False)

    def test_roc_period_parsers_return_iso_values(self):
        self.assertEqual(parse_roc_year("114", field="year"), "2025")
        self.assertEqual(parse_roc_month("11405", field="month"), "2025-05")
        self.assertEqual(parse_roc_date("1140521", field="date"), "2025-05-21")
        self.assertIsNone(parse_roc_date("額滿為止", field="date"))
        with self.assertRaises(TransformValueError):
            parse_roc_month("11413", field="month")

    def test_common_metadata_contains_complete_validated_contract(self):
        metadata = build_common_metadata(
            dataset="population",
            source="moi",
            source_record_id="row-1",
            geo_level="district",
            district_id="65000010",
            district_name="板橋區",
            period_start="2025-05-01",
            period_end="2025-05-31",
            period_type="month",
            metric_id="youth_18_35_total",
            value=10,
            unit="people",
            age_scope="derived_18_35",
            age_min=18,
            age_max=35,
            youth_eligibility="eligible",
            fetched_at="2026-09-01T00:00:00+00:00",
        )
        self.assertEqual(metadata["dataset"], "population")
        self.assertEqual(metadata["quality_flags"], [])
        self.assertEqual(metadata["age_min"], 18)
        self.assertEqual(metadata["age_max"], 35)
        self.assertEqual(len(metadata), 18)

    def test_common_metadata_rejects_inconsistent_contract_values(self):
        required = dict(
            dataset="population",
            source="moi",
            source_record_id=None,
            geo_level="district",
            district_id=None,
            district_name=None,
            period_start=None,
            period_end=None,
            period_type=None,
            metric_id=None,
            value=None,
            unit=None,
            age_scope="all_ages",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=None,
        )
        village_metadata = build_common_metadata(**(required | {"geo_level": "village"}))
        self.assertEqual(village_metadata["geo_level"], "village")
        with self.assertRaises(TransformValueError):
            build_common_metadata(**(required | {"youth_eligibility": "eligible"}))

    def test_common_metadata_accepts_organization_without_district(self):
        metadata = build_common_metadata(
            dataset="youth_budgets",
            source="ntpc_youth_bureau_budget",
            source_record_id="budget-row-1",
            geo_level="organization",
            district_id=None,
            district_name=None,
            period_start="2026-01-01",
            period_end="2026-12-31",
            period_type="year",
            metric_id="budget_amount",
            value=213022,
            unit="TWD_thousand",
            age_scope="not_age_specific",
            age_min=None,
            age_max=None,
            youth_eligibility="context_only",
            fetched_at=None,
        )
        self.assertEqual(metadata["geo_level"], "organization")
        self.assertIsNone(metadata["district_id"])

    def test_fallback_source_id_is_stable_when_input_order_changes(self):
        raw = {"district": "板橋區", "value": "10"}

        first = build_source_record_id("example", 0, raw)
        reordered = build_source_record_id("example", 99, raw)

        self.assertEqual(first, reordered)


if __name__ == "__main__":
    unittest.main()
