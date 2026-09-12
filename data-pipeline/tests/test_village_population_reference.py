import sys
import unittest
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.config import load_homepage_analytics_config  # noqa: E402
from analytics.fertility import generate_fertility_data  # noqa: E402
from analytics.homepage import generate_homepage_data  # noqa: E402
from analytics.io import CuratedSlice  # noqa: E402
from analytics.youth_participation import generate_youth_participation_data  # noqa: E402


class EmptyRecordingResolver:
    districts = []

    def __init__(self):
        self.requests = []

    def available_periods(self, dataset, periods):
        periods = tuple(periods)
        self.requests.append((dataset, periods))
        period_type = "month" if periods and len(periods[0]) == 5 else "annual"
        return CuratedSlice(
            dataset,
            period_type,
            periods,
            (),
            tuple(f"curated/{dataset}/{period}.json" for period in periods),
        )

    def latest(self, dataset):
        self.requests.append((dataset, ("latest",)))
        return CuratedSlice(
            dataset,
            "snapshot",
            ("latest",),
            (),
            (f"curated/{dataset}/latest.json",),
        )

    def all_available(self, dataset):
        self.requests.append((dataset, ("all",)))
        return CuratedSlice(
            dataset,
            "mixed",
            ("all",),
            (),
            (f"curated/{dataset}/all.json",),
        )

    def requested_village_periods(self):
        return [periods for dataset, periods in self.requests if dataset == "population_villages"]

    def requested_population_periods(self):
        return [
            period
            for dataset, periods in self.requests
            if dataset == "population"
            for period in periods
        ]


class BudgetAllocationResolver(EmptyRecordingResolver):
    def all_available(self, dataset):
        if dataset != "youth_budgets":
            return super().all_available(dataset)
        rows = [
            {
                "budget_year_roc": "116",
                "document_status": "proposed_budget",
                "row_type": "allocation",
                "metric_id": "budget_allocation_amount",
                "value": amount,
                "unit": "TWD",
                "allocation_code": code,
                "allocation_name": name,
                "work_plan": name,
                "business_plan": "青年發展業務",
                "budget_section": section,
                "account_category": "設備及投資" if code == "04" else None,
                "source_pdf_sha256": "sha256:test",
            }
            for code, name, amount, section in (
                ("01", "綜合規劃業務", 38_960_000, "經常門"),
                ("02", "職涯發展業務", 37_730_000, "經常門"),
                ("03", "創業資源業務", 70_979_000, "經常門"),
                ("04", "青年業務設施", 11_852_000, "資本門"),
            )
        ]
        rows.append(
            {
                "budget_year_roc": "116",
                "document_status": "proposed_budget",
                "row_type": "detail",
                "metric_id": "budget_amount",
                "budget_amount": 159_521,
                "value": 159_521,
                "unit": "TWD_thousand",
                "business_plan": "青年發展業務",
                "work_plan": "青年發展業務",
            }
        )
        return CuratedSlice(
            dataset,
            "mixed",
            ("all",),
            tuple(rows),
            ("curated/youth_budgets/all.json",),
        )


class TestVillagePopulationReference(unittest.TestCase):
    def test_fertility_uses_explicit_village_population_reference_period(self):
        config = load_homepage_analytics_config(CONFIG_DIR / "homepage_analytics.json")
        resolver = EmptyRecordingResolver()

        generate_fertility_data(resolver=resolver, config=config)

        self.assertEqual(resolver.requested_village_periods(), [("11507",)])
        self.assertIn("11401", resolver.requested_population_periods())

    def test_youth_participation_uses_explicit_village_population_reference_period(self):
        config = load_homepage_analytics_config(CONFIG_DIR / "homepage_analytics.json")
        resolver = EmptyRecordingResolver()

        generate_youth_participation_data(
            resolver=resolver,
            config=config,
            config_dir=CONFIG_DIR,
        )

        self.assertEqual(resolver.requested_village_periods(), [("11507",)])
        self.assertIn("11401", resolver.requested_population_periods())

    def test_youth_participation_publishes_budget_allocation_without_changing_trend(self):
        config = load_homepage_analytics_config(CONFIG_DIR / "homepage_analytics.json")
        result = generate_youth_participation_data(
            resolver=BudgetAllocationResolver(),
            config=config,
            config_dir=CONFIG_DIR,
        )

        allocation = result["budget_allocation"]
        self.assertEqual(allocation["status"], "observed")
        self.assertEqual(allocation["total_amount"], 159_521_000)
        self.assertEqual(
            [item["share_percent"] for item in allocation["items"]],
            [24.42, 23.65, 44.5, 7.43],
        )
        self.assertEqual(
            [row["year_roc"] for row in result["budget"]["trend"]],
            [110, 111, 112, 113, 114],
        )
        self.assertEqual(
            result["time_policy"]["budget_allocation_reference_year_roc"], 116
        )
        self.assertNotIn("raw_record", str(result["budget_allocation"]))


if __name__ == "__main__":
    unittest.main()
