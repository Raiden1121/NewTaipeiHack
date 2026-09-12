import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from analytics.data_gaps import (  # noqa: E402
    DEFAULT_FILENAME,
    explain_reason_codes,
    load_data_gaps,
)


class TestDataGaps(unittest.TestCase):
    def test_shipped_registry_documents_every_verified_gap(self):
        config_path = Path(__file__).resolve().parents[1] / "config" / DEFAULT_FILENAME
        gaps = load_data_gaps(config_path)

        self.assertIn("source_has_no_data_before_10701", gaps)
        self.assertIn("source_scope_is_two_training_centers", gaps)
        for code, entry in gaps.items():
            self.assertTrue(entry.get("summary"), code)
            self.assertTrue(entry.get("resolution"), code)
            self.assertIsInstance(entry.get("datasets"), list, code)

    def test_missing_registry_is_tolerated(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(load_data_gaps(Path(directory) / "absent.json"), {})

    def test_explains_known_codes_and_flags_undocumented_ones(self):
        with TemporaryDirectory() as directory:
            config_dir = Path(directory)
            (config_dir / DEFAULT_FILENAME).write_text(
                json.dumps(
                    {
                        "version": "1",
                        "gaps": {
                            "source_not_published": {
                                "summary": "來源尚未發布",
                                "datasets": ["wages"],
                                "resolution": "等待發布",
                            }
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            explained = explain_reason_codes(
                ["source_not_published", "brand_new_reason", "source_not_published"],
                config_dir=config_dir,
            )

        # Duplicates collapse and order is preserved.
        self.assertEqual(
            [item["reason_code"] for item in explained],
            ["source_not_published", "brand_new_reason"],
        )
        self.assertTrue(explained[0]["documented"])
        self.assertEqual(explained[0]["summary"], "來源尚未發布")
        # An undocumented code stays visible rather than being dropped.
        self.assertFalse(explained[1]["documented"])


if __name__ == "__main__":
    unittest.main()
