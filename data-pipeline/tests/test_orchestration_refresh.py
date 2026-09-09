from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from datetime import datetime, timezone

from orchestration.contracts import CollectorSpec, PeriodStrategy
from orchestration.refresh import (
    build_refresh_units,
    datasets_for_profile,
    load_refresh_profiles,
    validate_refresh_profiles,
)


class RefreshProfileTests(unittest.TestCase):
    def test_loads_profiles_and_filters_selected_datasets(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "refresh_profiles.json"
            path.write_text(json.dumps({
                "version": 1,
                "profiles": {
                    "daily": ["job_vacancies", "job_vacancy_salaries"],
                    "weekly": ["house_prices"],
                    "monthly": ["population"],
                },
            }), encoding="utf-8")
            profiles = load_refresh_profiles(path)

        self.assertEqual(
            datasets_for_profile(
                profiles,
                "daily",
                selected=("job_vacancies",),
            ),
            ("job_vacancies",),
        )

    def test_rejects_unknown_or_duplicate_dataset(self):
        profiles = {
            "daily": ("job_vacancies", "population"),
            "weekly": ("population",),
            "monthly": (),
        }
        with self.assertRaises(ValueError):
            validate_refresh_profiles(profiles, {"job_vacancies", "population"})

    def test_rejects_unknown_profile(self):
        with self.assertRaises(ValueError):
            datasets_for_profile(
                {"daily": ("job_vacancies",), "weekly": (), "monthly": ()},
                "annual",
            )

    def test_build_refresh_units_filters_profile_selection_and_due_state(self):
        specs = (
            CollectorSpec("job_vacancies", lambda _period: [], PeriodStrategy.SNAPSHOT),
            CollectorSpec("job_vacancy_salaries", lambda _period: [], PeriodStrategy.SNAPSHOT),
            CollectorSpec("population", lambda _period: [], PeriodStrategy.MONTHLY),
        )
        profiles = {
            "daily": ("job_vacancies", "job_vacancy_salaries"),
            "weekly": (),
            "monthly": ("population",),
        }
        state = {
            "schema_version": 1,
            "units": {
                "job_vacancies:latest": {
                    "status": "ok",
                    "last_checked_at": "2026-09-09T00:00:00+00:00",
                }
            },
        }
        now = datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc)

        units = build_refresh_units(
            specs,
            profile="daily",
            profiles=profiles,
            state=state,
            selected=("job_vacancy_salaries",),
            now=now,
        )

        self.assertEqual(
            [(unit.spec.dataset, unit.output_key) for unit in units],
            [("job_vacancy_salaries", "latest")],
        )

    def test_build_refresh_units_returns_empty_when_no_unit_is_due(self):
        specs = (CollectorSpec("population", lambda _period: [], PeriodStrategy.MONTHLY),)
        profiles = {"daily": (), "weekly": (), "monthly": ("population",)}
        state = {
            "schema_version": 1,
            "units": {
                "population:11509": {
                    "status": "ok",
                    "last_checked_at": "2026-09-09T00:00:00+00:00",
                }
            },
        }

        self.assertEqual(
            build_refresh_units(
                specs,
                profile="monthly",
                profiles=profiles,
                state=state,
                now=datetime(2026, 9, 9, 1, 0, tzinfo=timezone.utc),
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
