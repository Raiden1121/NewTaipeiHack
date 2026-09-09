from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from orchestration.refresh import (
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


if __name__ == "__main__":
    unittest.main()
