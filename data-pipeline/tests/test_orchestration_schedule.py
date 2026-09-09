import sys
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_DIR / "data-pipeline" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from orchestration.contracts import CollectorSpec, PeriodStrategy  # noqa: E402
from orchestration.schedule import build_execution_units  # noqa: E402
from run_pipeline import DEFAULT_COLLECTOR_SPECS, TDX_COLLECTOR_SPECS  # noqa: E402


class TestExecutionSchedule(unittest.TestCase):
    def test_builds_one_execution_unit_per_source_period_strategy(self):
        specs = (
            CollectorSpec("monthly", lambda period: [], PeriodStrategy.MONTHLY),
            CollectorSpec("annual", lambda period: [], PeriodStrategy.ANNUAL),
            CollectorSpec("snapshot", lambda period: [], PeriodStrategy.SNAPSHOT),
            CollectorSpec("all_available", lambda period: [], PeriodStrategy.ALL_AVAILABLE),
        )

        units = build_execution_units(specs, "11411", "11502")
        units_by_dataset = {
            dataset: [unit for unit in units if unit.spec.dataset == dataset]
            for dataset in ("monthly", "annual", "snapshot", "all_available")
        }

        self.assertEqual(
            [unit.output_key for unit in units_by_dataset["monthly"]],
            ["11411", "11412", "11501", "11502"],
        )
        self.assertEqual(
            [unit.output_key for unit in units_by_dataset["annual"]],
            ["114", "115"],
        )
        self.assertEqual(
            [unit.output_key for unit in units_by_dataset["snapshot"]],
            ["latest"],
        )
        self.assertEqual(
            [unit.output_key for unit in units_by_dataset["all_available"]],
            ["all"],
        )
        self.assertEqual(
            [unit.source_period for unit in units_by_dataset["annual"]],
            ["11401", "11501"],
        )
        self.assertEqual(
            [unit.source_period for unit in units_by_dataset["snapshot"]],
            ["11502"],
        )
        self.assertEqual(
            [unit.source_period for unit in units_by_dataset["all_available"]],
            ["11502"],
        )

    def test_default_registry_assigns_each_dataset_its_source_strategy(self):
        expected_strategies = {
            "population": PeriodStrategy.MONTHLY,
            "movement": PeriodStrategy.MONTHLY,
            "births": PeriodStrategy.ANNUAL,
            "marriages": PeriodStrategy.ANNUAL,
            "wages": PeriodStrategy.ANNUAL,
            "college_majors": PeriodStrategy.ANNUAL,
            "graduate_majors": PeriodStrategy.ANNUAL,
            "house_prices": PeriodStrategy.SNAPSHOT,
            "rentals": PeriodStrategy.SNAPSHOT,
            "job_vacancies": PeriodStrategy.SNAPSHOT,
            "job_vacancy_salaries": PeriodStrategy.SNAPSHOT,
            "vt_courses": PeriodStrategy.SNAPSHOT,
            "training_numbers": PeriodStrategy.SNAPSHOT,
            "talent_demand": PeriodStrategy.ALL_AVAILABLE,
            "youth_budgets": PeriodStrategy.ALL_AVAILABLE,
        }

        self.assertEqual(
            {spec.dataset: spec.period_strategy for spec in DEFAULT_COLLECTOR_SPECS},
            expected_strategies,
        )
        self.assertTrue(
            all(spec.period_strategy is PeriodStrategy.SNAPSHOT for spec in TDX_COLLECTOR_SPECS)
        )


if __name__ == "__main__":
    unittest.main()
