"""Read-side routing and reshaping in modules/api/lambda/handler.py.

DynamoDB is replaced by an in-memory table, so this runs without AWS:

    python -m unittest discover infrastructure/modules/api/tests

Lives outside lambda/ so it is not zipped into the deployed function.
"""

import json
import io
import os
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path

LAMBDA_DIR = Path(__file__).resolve().parents[1] / "lambda"
TABLE_NAME = "test-analytics"


class FakeDynamoDB:
    def __init__(self):
        self.items = {}

    def put(self, pk, sk, **fields):
        self.items[(pk, sk)] = {"pk": pk, "sk": sk, **fields}

    def batch_get_item(self, RequestItems):
        keys = RequestItems[TABLE_NAME]["Keys"]
        found = [self.items[(k["pk"], k["sk"])] for k in keys if (k["pk"], k["sk"]) in self.items]
        return {"Responses": {TABLE_NAME: found}}


class FakeLambda:
    def __init__(self):
        self.calls = []
        self.response = {
            "StatusCode": 200,
            "Payload": io.BytesIO(json.dumps({"statusCode": 200, "body": "{}"}).encode()),
        }
        self.error = None

    def invoke(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


FAKE_DYNAMODB = FakeDynamoDB()
FAKE_LAMBDA = FakeLambda()
os.environ["ANALYTICS_TABLE_NAME"] = TABLE_NAME
os.environ["AI_SERVICE_FUNCTION_NAME"] = "test-ai-service"
fake_boto3 = types.ModuleType("boto3")
fake_boto3.resource = lambda _service: FAKE_DYNAMODB
fake_boto3.client = lambda _service, **_kwargs: FAKE_LAMBDA
sys.modules["boto3"] = fake_boto3
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

import handler  # noqa: E402


def get(path):
    response = handler.handler(
        {"requestContext": {"http": {"method": "GET"}}, "rawPath": path},
        types.SimpleNamespace(aws_request_id="test-request"),
    )
    return response["statusCode"], json.loads(response["body"])


def post(path, body):
    response = handler.handler(
        {
            "requestContext": {"http": {"method": "POST"}},
            "rawPath": path,
            "body": json.dumps(body, ensure_ascii=False),
            "isBase64Encoded": False,
        },
        types.SimpleNamespace(aws_request_id="test-request"),
    )
    return response["statusCode"], json.loads(response["body"])


def options(path):
    return handler.handler(
        {
            "requestContext": {"http": {"method": "OPTIONS"}},
            "rawPath": path,
            "headers": {
                "origin": "https://d3ejcsgg9liiha.cloudfront.net",
                "access-control-request-method": "POST",
                "access-control-request-headers": "content-type",
            },
        },
        types.SimpleNamespace(aws_request_id="test-request"),
    )


class TestApiHandler(unittest.TestCase):
    def setUp(self):
        FAKE_DYNAMODB.items.clear()
        FAKE_LAMBDA.calls.clear()
        FAKE_LAMBDA.error = None
        FAKE_LAMBDA.response = {
            "StatusCode": 200,
            "Payload": io.BytesIO(
                json.dumps(
                    {
                        "statusCode": 200,
                        "headers": {"content-type": "application/json"},
                        "body": json.dumps(
                            {
                                "action": "qa",
                                "generatedBy": "mock(no network)",
                                "output": {"answer": "板橋區有 10 萬名青年"},
                                "basis": [],
                            }
                        ),
                    }
                ).encode()
            ),
        }
        FAKE_DYNAMODB.put("META", "MANIFEST", snapshot_id="test-snapshot", generated_at="2026-09-13T00:00:00Z")
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "POLICY",
            currentBudget=Decimal("196153"),
            budgetTrend=[],
            executionRate=Decimal("93.2"),
            executionRateYearRoc=Decimal("114"),
            executionFailure=None,
        )

    def test_ai_query_cors_preflight_is_handled_before_the_default_route(self):
        response = options("/api/v1/ai/query")

        self.assertEqual(response["statusCode"], 204)
        self.assertEqual(response["body"], "")
        self.assertEqual(response["headers"]["Access-Control-Allow-Origin"], "*")
        self.assertIn("POST", response["headers"]["Access-Control-Allow-Methods"])
        self.assertEqual(FAKE_LAMBDA.calls, [])

    def test_youth_topic_weight_alias_returns_the_canonical_keyword_item(self):
        FAKE_DYNAMODB.put(
            "ANALYSIS#youth-keyword-frequency",
            "DATA",
            analysis_id="youth-keyword-frequency",
            period_scope="all_available",
            keywords=[{"term": "就業", "weight": Decimal("5")}],
        )

        alias_status, alias_body = get("/api/v1/analyses/youth-topic-weight")
        canonical_status, canonical_body = get("/api/v1/analyses/youth-keyword-frequency")

        self.assertEqual(alias_status, 200)
        self.assertEqual(canonical_status, 200)
        self.assertEqual(alias_body["data"], canonical_body["data"])
        self.assertEqual(alias_body["data"]["analysis_id"], "youth-keyword-frequency")
        self.assertNotIn("topics", alias_body["data"])
        self.assertNotIn("year_roc", alias_body["data"])

    def test_politics_resource_io_carries_the_execution_rate_year(self):
        FAKE_DYNAMODB.put(
            "ANALYSIS#politics-resource-io", "DATA", analysis_id="politics-resource-io", budget_by_department=[]
        )

        status, body = get("/api/v1/analyses/politics-resource-io")

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["executionRate"], 93.2)
        self.assertEqual(body["data"]["executionRateYearRoc"], 114)

    def test_policy_outcomes_reads_the_pipeline_population_shape(self):
        FAKE_DYNAMODB.put("ANALYSIS#policy-outcomes", "DATA", analysis_id="policy-outcomes", wageTrend=[])
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "POPULATION_TREND",
            years=[
                {"year_roc": Decimal("113"), "city": {"youth_18_35_total": Decimal("862933"), "people_total": Decimal("4047001")}},
                {"year_roc": Decimal("114"), "city": {"youth_18_35_total": Decimal("845938"), "people_total": Decimal("4044831")}},
            ],
        )

        status, body = get("/api/v1/analyses/policy-outcomes")

        self.assertEqual(status, 200)
        self.assertEqual(
            body["data"]["populationTrend"],
            [
                {"year_roc": 113, "population": 862933, "yoy": None},
                {"year_roc": 114, "population": 845938, "yoy": -1.97},
            ],
        )

    def test_policy_outcomes_still_accepts_the_seed_data_shape_and_missing_values(self):
        FAKE_DYNAMODB.put("ANALYSIS#policy-outcomes", "DATA", analysis_id="policy-outcomes")
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "POPULATION_TREND",
            years=[
                {"year_roc": Decimal("112"), "city": {"youth_population": Decimal("100")}},
                {"year_roc": Decimal("113"), "city": {"youth_18_35_total": None}},
                {"year_roc": Decimal("114"), "city": {"youth_population": Decimal("110")}},
            ],
        )

        status, body = get("/api/v1/analyses/policy-outcomes")

        self.assertEqual(status, 200)
        self.assertEqual(
            [row["yoy"] for row in body["data"]["populationTrend"]],
            [None, None, None],
        )
        self.assertEqual(body["data"]["populationTrend"][0]["population"], 100)

    def test_unknown_analysis_is_still_404(self):
        status, body = get("/api/v1/analyses/not-a-real-analysis")

        self.assertEqual(status, 404)
        self.assertEqual(body["error"]["code"], "ANALYSIS_NOT_FOUND")

    def test_dashboard_overview_returns_the_projected_kpis_unchanged(self):
        FAKE_DYNAMODB.put(
            "DASHBOARD",
            "KPIS",
            kpis={"nationalYouthPopulation": Decimal("4979852"), "nationalYouthPopulationQuality": "observed"},
            availability={},
        )

        status, body = get("/api/v1/dashboard/overview")

        self.assertEqual(status, 200)
        self.assertEqual(body["data"]["kpis"]["nationalYouthPopulation"], 4979852)
        self.assertEqual(body["data"]["kpis"]["nationalYouthPopulationQuality"], "observed")
        self.assertEqual(body["data"]["policy"]["executionRateYearRoc"], 114)

    def test_ai_query_invokes_the_ai_lambda_with_a_public_request_body(self):
        request = {
            "action": "qa",
            "question": "板橋區有多少青年？",
            "focusDistrict": "板橋區",
            "focusArea": "population",
            "period": "114",
            "webSearch": {"enabled": False, "scope": "all", "contextSize": "low"},
        }

        status, body = post("/api/v1/ai/query", request)

        self.assertEqual(status, 200)
        self.assertEqual(body["action"], "qa")
        self.assertEqual(len(FAKE_LAMBDA.calls), 1)
        call = FAKE_LAMBDA.calls[0]
        self.assertEqual(call["FunctionName"], "test-ai-service")
        self.assertEqual(call["InvocationType"], "RequestResponse")
        forwarded = json.loads(json.loads(call["Payload"])["body"])
        self.assertEqual(forwarded, request)
        self.assertFalse(json.loads(call["Payload"])["isBase64Encoded"])

    def test_ai_query_rejects_internal_context_and_evidence_fields(self):
        for forbidden in ("context", "evidence", "webFindings"):
            status, body = post(
                "/api/v1/ai/query",
                {"action": "qa", "question": "測試", forbidden: {}},
            )
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "INVALID_AI_REQUEST")
        self.assertEqual(FAKE_LAMBDA.calls, [])

    def test_ai_query_maps_ai_validation_and_runtime_errors(self):
        FAKE_LAMBDA.response = {
            "StatusCode": 200,
            "Payload": io.BytesIO(
                json.dumps(
                    {
                        "statusCode": 400,
                        "body": json.dumps({"error": "bad request"}),
                    }
                ).encode()
            ),
        }
        status, body = post("/api/v1/ai/query", {"action": "qa", "question": "測試"})
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "bad request")

        FAKE_LAMBDA.response = {
            "StatusCode": 200,
            "FunctionError": "Unhandled",
            "Payload": io.BytesIO(json.dumps({"errorMessage": "boom"}).encode()),
        }
        status, body = post("/api/v1/ai/query", {"action": "qa", "question": "測試"})
        self.assertEqual(status, 502)
        self.assertEqual(body["error"]["code"], "AI_SERVICE_ERROR")

    def test_ai_query_maps_invoke_timeout_to_504(self):
        FAKE_LAMBDA.error = TimeoutError("read timeout")

        status, body = post("/api/v1/ai/query", {"action": "qa", "question": "測試"})

        self.assertEqual(status, 504)
        self.assertEqual(body["error"]["code"], "AI_SERVICE_TIMEOUT")

    def test_ai_query_maps_malformed_ai_payload_to_502(self):
        FAKE_LAMBDA.response = {
            "StatusCode": 200,
            "Payload": io.BytesIO(b"not-json"),
        }

        status, body = post("/api/v1/ai/query", {"action": "qa", "question": "測試"})

        self.assertEqual(status, 502)
        self.assertEqual(body["error"]["code"], "AI_SERVICE_ERROR")

    def test_ai_query_without_function_name_is_503(self):
        previous = os.environ.pop("AI_SERVICE_FUNCTION_NAME")
        try:
            status, body = post("/api/v1/ai/query", {"action": "qa", "question": "測試"})
        finally:
            os.environ["AI_SERVICE_FUNCTION_NAME"] = previous

        self.assertEqual(status, 503)
        self.assertEqual(body["error"]["code"], "AI_SERVICE_UNAVAILABLE")
        self.assertEqual(FAKE_LAMBDA.calls, [])

    def test_ai_query_rejects_invalid_public_request(self):
        cases = [
            {"action": "other", "question": "測試"},
            {"action": "qa"},
            {"action": "qa", "question": "x" * 401},
            {"action": "qa", "question": "測試", "period": "1140"},
            {"action": "qa", "question": "測試", "period": "11413"},
            {"action": "qa", "question": "測試", "webSearch": {"scope": "private"}},
        ]
        for request in cases:
            status, body = post("/api/v1/ai/query", request)
            self.assertEqual(status, 400)
            self.assertEqual(body["error"]["code"], "INVALID_AI_REQUEST")
        self.assertEqual(FAKE_LAMBDA.calls, [])


if __name__ == "__main__":
    unittest.main()
