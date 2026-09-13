"""Writer-side projection into the table infrastructure/dynamodb_schema.md defines.

Covers the fields the projection has to map or aggregate because the published
snapshot does not carry them in the shape api_contract.md serves.

    python -m unittest discover infrastructure/modules/analytics_lambda/tests

Lives outside lambda/ so it is not copied into the container image.
"""

import gzip
import json
import sys
import unittest
from decimal import Decimal
from pathlib import Path

LAMBDA_DIR = Path(__file__).resolve().parents[1] / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

from dynamodb_projection import (  # noqa: E402
    AI_CONTEXT_PK,
    MANIFEST_KEY,
    build_items,
    to_dynamodb_types,
)


def _borough_district(district_id, *, seats, youth_seats, ratio, yrr, youth_pop, total_pop):
    return {
        "district_id": district_id,
        "elected_seat_count": seats,
        "youth_elected_count": youth_seats,
        "youth_borough_chief_ratio": ratio,
        "yrr": yrr,
        "youth_population_18_35": youth_pop,
        "population_total": total_pop,
        "denominator_type": "population_proxy",
        "proxy": True,
    }


MANIFEST = {
    "schema_version": 1,
    "snapshot_id": "test-snapshot",
    "generated_at": "2026-01-01T00:00:00Z",
    "warnings": [],
}

DASHBOARD = {
    "calculation_version": "2",
    "time_policy": {"annual_years_roc": [114], "election_years_roc": [103, 107, 111]},
    "kpis": {"cityYouthPopulation": 845938.0},
    "availability": {"opportunityIndex": "available"},
    "policy": {"currentBudget": 196153.0, "budgetTrend": [], "executionRate": None},
    "service_coverage": {
        "value": 49.3,
        "status": "observed",
        "villages": [{"village_code": "65000010001"}],
        "districts": [{"district_id": "65000010"}],
    },
    "elections": {
        "city_councilor_t1": [{"district_id": None}],
        "city_councilor_t1_citywide": [{"election_year_roc": 111}],
        "borough_chief_v1": [{"election_year_roc": 103}],
    },
    "annual": {
        "population": {"years": [{"year_roc": 114}]},
        "fertility": {"years": [{"year_roc": 114}]},
    },
    "districts": [
        {"district_id": "65000010", "district_name": "板橋區", "opportunityIndex": 64.02},
        {"district_id": "65000020", "district_name": "三重區", "opportunityIndex": 51.5},
        {"district_id": "65000030", "district_name": "中和區", "opportunityIndex": 40.0},
    ],
}

PARTICIPATION = {
    "elections": {
        "v1_borough_chief": {
            "years": [
                {"year_roc": 103, "districts": [_borough_district(
                    "65000010", seats=125, youth_seats=1, ratio=0.8, yrr=0.04,
                    youth_pop=152817.0, total_pop=550000.0)]},
                {
                    "year_roc": 111,
                    "districts": [
                        _borough_district(
                            "65000010", seats=126, youth_seats=3, ratio=2.380952,
                            yrr=0.112823, youth_pop=115979.0, total_pop=549572.0),
                        _borough_district(
                            "65000020", seats=100, youth_seats=7, ratio=7.0,
                            yrr=0.35, youth_pop=80000.0, total_pop=400000.0),
                    ],
                },
            ]
        }
    },
    "budget_allocation": {
        "items": [{"name": "綜合規劃業務", "amount": 38960000, "share_percent": 24.42}]
    },
    "topics": {
        "keyword_frequency": {
            "metric_id": "youth_keyword_frequency",
            "analysis_id": "youth-keyword-frequency",
            "calculation_version": "5",
            "config_version": "3",
            "source_datasets": ["join_proposals"],
            "period_scope": "all_available",
            "source_periods": {"join_proposals": ["114"]},
            "normalization": "yearly_max",
            "weight_normalization": "rank",
            "candidate_mode": "policy_relevant",
            "generated_at": "2026-01-01T00:00:00Z",
            "keywords": [{"term": "心理健康", "weight": 5}],
        }
    },
}

ANALYSES = {
    "employment": {
        "scatter": {
            "knowledge_job_vs_estimated_wage": {"title": "a", "points": [], "regression": {}},
            "monthly_wage_vs_house_price": {"title": "b", "points": [], "regression": {}},
        }
    },
    "fertility": {
        "scatter": {"points": [{"x": 1.0}], "regression": {"slope": 0.1}, "title": "drop me"},
        "fafi": {
            "districts": {
                "65000010": {"fafiScore": 54.8, "fafiLevel": "high"},
                "65000020": {"fafiScore": 41.2, "fafiLevel": "low"},
            }
        },
    },
    "participation": PARTICIPATION,
    "policy_support": {
        "policyOutcomes": {
            "wageTrend": [{"year_roc": 113, "wage": 59.9}],
            "populationTrend": [{"year_roc": 113, "population": 873702}],
            "currentWageGrowth": 4.54,
            "currentPopGrowth": -2.26,
        }
    },
}


class TestProjection(unittest.TestCase):
    def setUp(self):
        self.items = build_items(manifest=MANIFEST, dashboard=DASHBOARD, analyses=ANALYSES)
        self.by_key = {(item["pk"], item["sk"]): item for item in self.items}

    def test_writes_manifest_last_with_schema_version(self):
        last = self.items[-1]
        self.assertEqual((last["pk"], last["sk"]), MANIFEST_KEY)
        self.assertEqual(last["schema_version"], 1)
        self.assertEqual(last["districts_count"], 3)

    def test_maps_district_scalars_from_the_111_participation_rows(self):
        districts = self.by_key[("DASHBOARD", "DISTRICTS")]["districts"]
        by_id = {row["district_id"]: row for row in districts}
        # Mapped straight through, not recomputed (api_contract.md §6.2).
        self.assertEqual(by_id["65000010"]["youthBoroughChiefRatioPercent"], 2.380952)
        self.assertEqual(by_id["65000010"]["yrr"], 0.112823)
        # Absent from the 111 term -> null, never 0 (§1.3).
        self.assertIsNone(by_id["65000030"]["youthBoroughChiefRatioPercent"])
        self.assertIsNone(by_id["65000030"]["yrr"])

    def test_citywide_totals_first_then_one_formula(self):
        citywide = self.by_key[("DASHBOARD", "ELECTIONS")]["borough_chief_v1_citywide"]
        self.assertEqual(citywide["year_roc"], 111)
        self.assertEqual(citywide["elected_count"], 226)
        self.assertEqual(citywide["youth_elected_count"], 10)

        seat_share = 10 / 226
        youth_share = (115979.0 + 80000.0) / (549572.0 + 400000.0)
        self.assertAlmostEqual(citywide["ratio_percent"], seat_share * 100)
        self.assertAlmostEqual(citywide["yrr"], seat_share / youth_share)
        # §6.2 forbids averaging the districts' own yrr values.
        self.assertNotAlmostEqual(citywide["yrr"], (0.112823 + 0.35) / 2, places=3)
        self.assertEqual(citywide["denominator_type"], "population_proxy")
        self.assertIs(citywide["proxy"], True)

    def test_district_items_carry_the_same_object_as_the_dashboard_array(self):
        summary = self.by_key[("DISTRICT#65000010", "SUMMARY")]
        dashboard_row = next(
            row
            for row in self.by_key[("DASHBOARD", "DISTRICTS")]["districts"]
            if row["district_id"] == "65000010"
        )
        self.assertEqual({k: v for k, v in summary.items() if k not in ("pk", "sk")}, dashboard_row)

    def test_policy_keeps_execution_rate_year_key_even_before_the_pipeline_fills_it(self):
        policy = self.by_key[("DASHBOARD", "POLICY")]
        self.assertIn("executionRateYearRoc", policy)
        self.assertIsNone(policy["executionRateYearRoc"])

    def test_passes_through_pipeline_selected_execution_year_and_national_kpi(self):
        dashboard = {
            **DASHBOARD,
            "kpis": {
                **DASHBOARD["kpis"],
                "nationalYouthPopulation": 4979852.0,
                "nationalYouthPopulationQuality": "observed",
            },
            "policy": {
                **DASHBOARD["policy"],
                "executionRate": 93.2,
                "executionRateYearRoc": 114,
                "executionFailure": None,
            },
        }

        items = build_items(manifest=MANIFEST, dashboard=dashboard, analyses=ANALYSES)
        by_key = {(item["pk"], item["sk"]): item for item in items}

        policy = by_key[("DASHBOARD", "POLICY")]
        self.assertEqual(policy["executionRate"], 93.2)
        self.assertEqual(policy["executionRateYearRoc"], 114)
        kpis = by_key[("DASHBOARD", "KPIS")]["kpis"]
        self.assertEqual(kpis["nationalYouthPopulation"], 4979852.0)
        self.assertEqual(kpis["nationalYouthPopulationQuality"], "observed")

    def test_drops_the_payloads_the_schema_excludes(self):
        coverage = self.by_key[("DASHBOARD", "SERVICE_COVERAGE")]
        self.assertNotIn("villages", coverage)
        self.assertNotIn("districts", coverage)
        self.assertNotIn("city_councilor_t1", self.by_key[("DASHBOARD", "ELECTIONS")])

    def test_keyword_frequency_is_canonical_and_has_no_legacy_topic_item(self):
        self.assertNotIn(("ANALYSIS#youth-topic-weight", "DATA"), self.by_key)
        item = self.by_key[("ANALYSIS#youth-keyword-frequency", "DATA")]
        self.assertEqual(item["analysis_id"], "youth-keyword-frequency")
        self.assertEqual(item["keywords"][0]["term"], "心理健康")
        self.assertEqual(item["candidate_mode"], "policy_relevant")
        # §6.4: no year pinned onto the full-period shape, no topics[] copy.
        self.assertNotIn("year_roc", item)
        self.assertNotIn("topics", item)

    def test_reshapes_employment_scatter_into_the_contract_plot_ids(self):
        plots = self.by_key[("ANALYSIS#employment-scatter", "DATA")]["plots"]
        self.assertEqual([plot["id"] for plot in plots], ["knowledge-wage", "wage-housing"])

    def test_reshapes_fafi_object_into_a_list_with_contract_field_names(self):
        rows = self.by_key[("ANALYSIS#fertility-family-friendliness", "DATA")]["districts"]
        self.assertEqual(
            rows[0],
            {
                "district_id": "65000010",
                "district_name": "板橋區",
                "fafi_score": 54.8,
                "fafi_level": "high",
            },
        )

    def test_converts_budget_allocation_amounts_to_thousands(self):
        rows = self.by_key[("ANALYSIS#politics-resource-io", "DATA")]["budget_by_department"]
        self.assertEqual(
            rows, [{"label": "綜合規劃業務", "amount_thousand": 38960.0, "share_percent": 24.42}]
        )

    def test_policy_outcomes_adds_direction_and_leaves_population_trend_to_the_reader(self):
        outcomes = self.by_key[("ANALYSIS#policy-outcomes", "DATA")]
        self.assertEqual(outcomes["desiredDirection"], {"wageGrowth": "up", "populationChange": "up"})
        self.assertNotIn("populationTrend", outcomes)

    def test_fertility_overlay_keeps_only_points_and_regression(self):
        overlay = self.by_key[("ANALYSIS#fertility-overlay", "DATA")]
        self.assertEqual(overlay["regression"], {"slope": 0.1})
        self.assertNotIn("title", overlay)

    def test_every_float_becomes_decimal_for_boto3(self):
        def has_float(value):
            if isinstance(value, float):
                return True
            if isinstance(value, dict):
                return any(has_float(item) for item in value.values())
            if isinstance(value, list):
                return any(has_float(item) for item in value)
            return False

        converted = [to_dynamodb_types(item) for item in self.items]
        self.assertFalse(any(has_float(item) for item in converted))
        self.assertEqual(converted[0]["kpis"]["cityYouthPopulation"], Decimal("845938.0"))

    def test_ai_context_carries_every_artifact_untrimmed_before_the_manifest(self):
        keys = [(item["pk"], item["sk"]) for item in self.items]
        manifest_index = keys.index(MANIFEST_KEY)
        for artifact_key, content in {"dashboard_overview": DASHBOARD, **ANALYSES}.items():
            key = (AI_CONTEXT_PK, f"ARTIFACT#{artifact_key}")
            self.assertLess(keys.index(key), manifest_index)
            item = self.by_key[key]
            self.assertEqual(item["snapshot_id"], "test-snapshot")
            self.assertEqual(item["encoding"], "gzip+json")
            # Not trimmed like the dashboard items: villages stay, ai-service drops them.
            self.assertEqual(json.loads(gzip.decompress(item["payload"])), content)

    def test_ai_context_manifest_is_the_whole_published_manifest(self):
        item = self.by_key[(AI_CONTEXT_PK, "MANIFEST")]
        self.assertEqual(item["snapshot_id"], "test-snapshot")
        self.assertEqual(json.loads(gzip.decompress(item["payload"])), MANIFEST)

    def test_ai_context_keeps_key_order(self):
        # ai-service's truncation keeps the first N evidence per dataset, so the
        # artifact's key order has to survive the round trip.
        item = self.by_key[(AI_CONTEXT_PK, "ARTIFACT#dashboard_overview")]
        self.assertEqual(list(json.loads(gzip.decompress(item["payload"]))), list(DASHBOARD))

    def test_ai_context_skips_district_details_like_ai_service(self):
        items = build_items(
            manifest=MANIFEST,
            dashboard=DASHBOARD,
            analyses={**ANALYSES, "district_details": {"districts": []}},
        )
        keys = {(item["pk"], item["sk"]) for item in items}
        self.assertNotIn((AI_CONTEXT_PK, "ARTIFACT#district_details"), keys)


if __name__ == "__main__":
    unittest.main()
