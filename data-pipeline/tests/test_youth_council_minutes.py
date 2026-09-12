import hashlib
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from collectors.youth_council_minutes import fetch_youth_council_minutes  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.headers = {"Content-Type": "application/pdf" if payload.startswith(b"%PDF-") else "text/html"}

    def read(self, limit=None):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class TestYouthCouncilMinutes(unittest.TestCase):
    def test_discovers_pdf_with_and_without_pdf_suffix_and_saves_artifact(self):
        first_pdf = b"%PDF-first"
        second_pdf = b"%PDF-second"
        pages = {
            "https://youth.test/list": """
                <a href='/meeting/one'>第六屆青年諮詢會 114年01月02日</a>
                <a href='/meeting/two'>第五屆青年諮詢會 113年12月20日</a>
            """.encode("utf-8"),
            "https://youth.test/meeting/one": first_pdf,
            "https://youth.test/meeting/two": b"<a href='/files/two.pdf'>PDF</a>",
            "https://youth.test/files/two.pdf": second_pdf,
        }

        with patch(
            "collectors.youth_council_minutes._extract_pdf_pages",
            side_effect=[["提案事項\n社宅\n決議：提請市議會"], ["青年創業"]],
        ):
            result = fetch_youth_council_minutes(
                listing_url="https://youth.test/list",
                open_url=lambda url, **_kwargs: FakeResponse(pages[url]),
            )

        self.assertEqual(len(result.records), 2)
        self.assertEqual(result.records[0]["year_roc"], "114")
        self.assertEqual(result.records[0]["page_texts"], ["提案事項\n社宅\n決議：提請市議會"])
        self.assertEqual(
            result.records[0]["source_pdf_sha256"],
            "sha256:" + hashlib.sha256(first_pdf).hexdigest(),
        )
        self.assertEqual(len(result.artifacts), 2)
        self.assertTrue(result.artifacts[0].filename.endswith(".pdf"))

    def test_derives_missing_meeting_date_from_pdf_text(self):
        pdf_bytes = b"%PDF-date-in-text"
        with patch(
            "collectors.youth_council_minutes._extract_pdf_pages",
            return_value=["114年03月04日\n提案事項\n一、社宅"],
        ):
            result = fetch_youth_council_minutes(
                listing_url="https://youth.test/list",
                open_url=lambda url, **_kwargs: FakeResponse(
                    "<a href='/meeting/one'>第六屆青年諮詢會</a>".encode("utf-8")
                    if url.endswith("/list")
                    else pdf_bytes
                ),
            )

        self.assertEqual(result.records[0]["meeting_date"], "114年03月04日")
        self.assertEqual(result.records[0]["year_roc"], "114")


if __name__ == "__main__":
    unittest.main()
