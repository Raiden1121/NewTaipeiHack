"""Guards in lambda/handler.py that do not need AWS.

boto3/botocore ship with the Lambda runtime rather than the local venv, so they
are stubbed for import only.

    python -m unittest discover infrastructure/modules/analytics_lambda/tests
"""

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

LAMBDA_DIR = Path(__file__).resolve().parents[1] / "lambda"
PIPELINE_SRC = Path(__file__).resolve().parents[4] / "data-pipeline" / "src"
for path in (LAMBDA_DIR, PIPELINE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

if "boto3" not in sys.modules:
    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.client = lambda *args, **kwargs: None
    fake_boto3.resource = lambda *args, **kwargs: None
    sys.modules["boto3"] = fake_boto3
if "botocore.exceptions" not in sys.modules:
    fake_botocore = types.ModuleType("botocore")
    fake_exceptions = types.ModuleType("botocore.exceptions")
    fake_exceptions.ClientError = type("ClientError", (Exception,), {})
    sys.modules["botocore"] = fake_botocore
    sys.modules["botocore.exceptions"] = fake_exceptions

import handler  # noqa: E402


class TestRequireJieba(unittest.TestCase):
    def test_refuses_to_run_without_jieba(self):
        with mock.patch.object(handler.importlib.util, "find_spec", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "jieba"):
                handler._require_jieba()

    def test_refuses_before_touching_s3_or_dynamodb(self):
        with mock.patch.object(handler.importlib.util, "find_spec", return_value=None), mock.patch.object(
            handler, "_install_s3_backing"
        ) as install, mock.patch.object(handler, "_write_items") as write:
            with mock.patch.dict(
                "os.environ", {"TRANSFORMED_BUCKET": "bucket", "ANALYTICS_TABLE_NAME": "table"}
            ):
                with self.assertRaises(RuntimeError):
                    handler.handler({}, None)
        install.assert_not_called()
        write.assert_not_called()

    def test_passes_when_jieba_is_importable(self):
        with mock.patch.object(handler.importlib.util, "find_spec", return_value=object()):
            handler._require_jieba()


class TestInputFailures(unittest.TestCase):
    def test_groups_failures_by_dataset_and_ignores_malformed_quality(self):
        homepage_quality = {
            "inputs": {
                "population": {"source_periods": ["11412"], "row_count": 10},
                "national_population": {"failures": ["no available requested periods"]},
            }
        }
        analysis_quality = {"inputs": {"national_population": {"failures": ["no available requested periods"]}}}

        failures = handler._input_failures(homepage_quality, analysis_quality, None, {"inputs": "bad"})

        self.assertEqual(failures, {"national_population": ["no available requested periods"]})


if __name__ == "__main__":
    unittest.main()
