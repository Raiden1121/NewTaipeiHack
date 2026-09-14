"""Single Lambda serving the read endpoints in api_contract.md and AI query.

Reads pre-computed analytics from the DynamoDB table named by the
`ANALYTICS_TABLE_NAME` env var, per the item shapes in
infrastructure/dynamodb_schema.md. No metric calculation happens here — every
item already holds its final value; this file only fetches items by pk/sk
and reshapes them into the response shapes api_contract.md defines. The one
exception is `analyses/policy-outcomes`' `populationTrend[].yoy`, a genuine
per-year calculation kept in `_handle_analysis` rather than the loader; see
the note there.

The table is maintained by a separate program (whatever loads
data-pipeline's published snapshot into DynamoDB); this Lambda only reads.
If the table has no `META/MANIFEST` item yet, the read endpoints return 503
`SNAPSHOT_UNAVAILABLE`; the AI route delegates evidence availability to the
private AI Service and returns its mapped response.

`POST /api/v1/ai/query` is the public AI boundary. It validates only the public
query contract, invokes the private AI Service synchronously, and never accepts
caller-supplied evidence/context.
"""

import base64
import json
import os
import re
from decimal import Decimal

import boto3

API_VERSION = "v1"

_dynamodb = boto3.resource("dynamodb")
_TABLE_NAME = os.environ["ANALYTICS_TABLE_NAME"]
_lambda_client = None

AI_QUERY_MAX_BODY_BYTES = 16 * 1024
AI_QUERY_MAX_QUESTION_CHARS = 400
AI_QUERY_ALLOWED_KEYS = {
    "action",
    "question",
    "focusDistrict",
    "focusArea",
    "period",
    "webSearch",
}
AI_QUERY_ACTIONS = {"explain", "policyCopilot", "qa"}
AI_QUERY_WEB_SEARCH_KEYS = {"enabled", "scope", "contextSize"}
AI_QUERY_WEB_SEARCH_SCOPES = {"all", "trusted"}
AI_QUERY_WEB_SEARCH_CONTEXT_SIZES = {"low", "medium", "high"}
AI_QUERY_ROC_PERIOD_PATTERN = re.compile(r"\d{3}(?:0[1-9]|1[0-2])?")

# analysis_id -> extra (pk, sk) this analysis reuses instead of duplicating
# in its own item (see dynamodb_schema.md's no-duplication note for each).
_ANALYSIS_EXTRA_KEYS = {
    "politics-resource-io": ("DASHBOARD", "POLICY"),
    "policy-outcomes": ("DASHBOARD", "POPULATION_TREND"),
}

# Legacy URL -> canonical analysis_id. Aliases resolve to the same item and
# return the canonical payload; the table never holds a copy under the old id
# (api_contract.md §6.4).
_ANALYSIS_ALIASES = {
    "youth-topic-weight": "youth-keyword-frequency",
}


class _DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o == o.to_integral_value() else float(o)
        return super().default(o)


def _get_items(keys):
    """BatchGetItem for a list of (pk, sk) tuples. Returns {(pk, sk): item}."""
    if not keys:
        return {}
    resp = _dynamodb.batch_get_item(
        RequestItems={_TABLE_NAME: {"Keys": [{"pk": pk, "sk": sk} for pk, sk in keys]}}
    )
    items = resp["Responses"].get(_TABLE_NAME, [])
    return {(i["pk"], i["sk"]): i for i in items}


def _strip_keys(item):
    return {k: v for k, v in item.items() if k not in ("pk", "sk")}


def _manifest_or_503(fetch, request_id):
    manifest = fetch.get(("META", "MANIFEST"))
    if manifest is None:
        return None, _error(503, "SNAPSHOT_UNAVAILABLE", "no published snapshot available", request_id)
    return manifest, None


# --- envelope helpers -------------------------------------------------------

def _envelope(manifest, data, warnings=None):
    return {
        "data": data,
        "meta": {
            "api_version": API_VERSION,
            "snapshot_id": manifest.get("snapshot_id"),
            "generated_at": manifest.get("generated_at"),
            "as_of": None,
            "warnings": warnings if warnings is not None else list(manifest.get("warnings", [])),
        },
    }


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False, cls=_DecimalEncoder),
    }


def _cors_preflight_response():
    """Answer browser preflight requests before the HTTP API $default route."""
    return {
        "statusCode": 204,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
        "body": "",
    }


def _error(status, code, message, request_id, details=None):
    return _response(status, {
        "error": {"code": code, "message": message, "details": details or []},
        "request_id": request_id,
    })


# --- route handlers ----------------------------------------------------------

def _handle_health(match, qs, request_id):
    fetch = _get_items([("META", "MANIFEST")])
    manifest = fetch.get(("META", "MANIFEST"))
    body = {"status": "ok" if manifest else "degraded", "manifest_readable": manifest is not None}
    return _response(200, _envelope(manifest or {}, body))


def _handle_catalog(match, qs, request_id):
    fetch = _get_items([("META", "MANIFEST")])
    manifest, err = _manifest_or_503(fetch, request_id)
    if err:
        return err
    data = {
        "snapshot_id": manifest.get("snapshot_id"),
        "generated_at": manifest.get("generated_at"),
        "calculation_version": manifest.get("calculation_version"),
        "districts_count": manifest.get("districts_count"),
        "time_policy": manifest.get("time_policy"),
        "quality": manifest.get("quality"),
    }
    return _response(200, _envelope(manifest, data))


def _handle_dashboard_overview(match, qs, request_id):
    fetch = _get_items([
        ("META", "MANIFEST"),
        ("DASHBOARD", "KPIS"),
        ("DASHBOARD", "POLICY"),
        ("DASHBOARD", "SERVICE_COVERAGE"),
        ("DASHBOARD", "ELECTIONS"),
        ("DASHBOARD", "POPULATION_TREND"),
        ("DASHBOARD", "FERTILITY_TREND"),
        ("DASHBOARD", "DISTRICTS"),
    ])
    manifest, err = _manifest_or_503(fetch, request_id)
    if err:
        return err

    kpis_item = fetch.get(("DASHBOARD", "KPIS"), {})
    data = {
        "kpis": kpis_item.get("kpis"),
        "districts": fetch.get(("DASHBOARD", "DISTRICTS"), {}).get("districts"),
        "annual": {
            "population": {"years": fetch.get(("DASHBOARD", "POPULATION_TREND"), {}).get("years")},
            "fertility": {"years": fetch.get(("DASHBOARD", "FERTILITY_TREND"), {}).get("years")},
        },
        "elections": _strip_keys(fetch.get(("DASHBOARD", "ELECTIONS"), {})),
        "service_coverage": _strip_keys(fetch.get(("DASHBOARD", "SERVICE_COVERAGE"), {})),
        "policy": _strip_keys(fetch.get(("DASHBOARD", "POLICY"), {})),
        "availability": kpis_item.get("availability"),
    }
    return _response(200, _envelope(manifest, data))


def _handle_district(match, qs, request_id):
    district_id = match.group(1)
    fetch = _get_items([("META", "MANIFEST"), (f"DISTRICT#{district_id}", "SUMMARY")])
    manifest, err = _manifest_or_503(fetch, request_id)
    if err:
        return err

    d = fetch.get((f"DISTRICT#{district_id}", "SUMMARY"))
    if not d:
        return _error(404, "DISTRICT_NOT_FOUND", f"unknown district_id {district_id}", request_id)

    metrics = {k: v for k, v in d.items() if k not in ("pk", "sk", "district_id", "district_name")}
    return _response(200, _envelope(manifest, {
        "district_id": d["district_id"],
        "district_name": d["district_name"],
        "metrics": metrics,
    }))


def _handle_analysis(match, qs, request_id):
    analysis_id = _ANALYSIS_ALIASES.get(match.group(1), match.group(1))
    keys = [("META", "MANIFEST"), (f"ANALYSIS#{analysis_id}", "DATA")]
    extra_key = _ANALYSIS_EXTRA_KEYS.get(analysis_id)
    if extra_key:
        keys.append(extra_key)

    fetch = _get_items(keys)
    manifest, err = _manifest_or_503(fetch, request_id)
    if err:
        return err

    item = fetch.get((f"ANALYSIS#{analysis_id}", "DATA"))
    if not item:
        return _error(404, "ANALYSIS_NOT_FOUND", f"unknown analysis_id {analysis_id}", request_id)

    data = _strip_keys(item)
    if analysis_id == "politics-resource-io":
        policy = fetch.get(("DASHBOARD", "POLICY"), {})
        data["budgetTrend"] = policy.get("budgetTrend")
        data["executionRate"] = policy.get("executionRate")
        data["executionRateYearRoc"] = policy.get("executionRateYearRoc")
    elif analysis_id == "policy-outcomes":
        # populationTrend[] isn't stored on the analysis item (see
        # dynamodb_schema.md) — reshaped here from DASHBOARD/POPULATION_TREND.
        # yoy is a genuine per-year calculation, not just a reshape, so this
        # is a deliberate, documented exception to "Lambda doesn't compute".
        pop_years = fetch.get(("DASHBOARD", "POPULATION_TREND"), {}).get("years") or []
        population_trend = []
        prev = None
        for y in pop_years:
            city = y.get("city") or {}
            # The pipeline's annual.population city row carries youth_18_35_total;
            # seed_test_data.py writes youth_population. Accept both so neither 500s.
            pop = city.get("youth_18_35_total", city.get("youth_population"))
            yoy = round((pop - prev) / prev * 100, 2) if pop is not None and prev else None
            population_trend.append({"year_roc": y.get("year_roc"), "population": pop, "yoy": yoy})
            prev = pop
        data["populationTrend"] = population_trend

    return _response(200, _envelope(manifest, data))


def _handle_ai_query(match, qs, request_id, event):
    public_request, validation_error = _parse_ai_query_request(event, request_id)
    if validation_error is not None:
        return validation_error

    function_name = (os.environ.get("AI_SERVICE_FUNCTION_NAME") or "").strip()
    if not function_name:
        return _error(
            503,
            "AI_SERVICE_UNAVAILABLE",
            "AI_SERVICE_FUNCTION_NAME is not configured",
            request_id,
        )

    invocation_event = {
        "body": json.dumps(public_request, ensure_ascii=False),
        "isBase64Encoded": False,
    }
    try:
        response = _get_lambda_client().invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(invocation_event, ensure_ascii=False).encode("utf-8"),
        )
    except Exception as exc:  # boto3 is intentionally lazy; classify SDK timeout errors here.
        if _is_lambda_timeout(exc):
            return _error(
                504,
                "AI_SERVICE_TIMEOUT",
                "AI Service did not respond before the synchronous request deadline",
                request_id,
            )
        return _error(502, "AI_SERVICE_ERROR", str(exc), request_id)

    if response.get("FunctionError"):
        return _error(
            502,
            "AI_SERVICE_ERROR",
            "AI Service Lambda returned a function error",
            request_id,
            [response.get("FunctionError")],
        )

    try:
        payload = response.get("Payload")
        raw_payload = payload.read() if hasattr(payload, "read") else payload
        if isinstance(raw_payload, bytes):
            raw_payload = raw_payload.decode("utf-8")
        invoked = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
        if not isinstance(invoked, dict):
            raise ValueError("invoked payload must be an object")
        ai_status = invoked.get("statusCode")
        ai_body = invoked.get("body")
        if not isinstance(ai_status, int) or not isinstance(ai_body, str):
            raise ValueError("invoked payload is missing statusCode/body")
        body = json.loads(ai_body)
        if not isinstance(body, dict):
            raise ValueError("AI response body must be an object")
    except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _error(502, "AI_SERVICE_ERROR", f"malformed AI Service response: {exc}", request_id)

    if ai_status == 200:
        return _response(200, body)
    if ai_status == 400:
        return _response(400, body)
    if ai_status == 503:
        return _response(503, body)
    if ai_status == 504:
        return _response(504, body)
    if ai_status >= 500:
        return _response(502, body)
    return _error(
        502,
        "AI_SERVICE_ERROR",
        f"unexpected AI Service status {ai_status}",
        request_id,
    )


def _parse_ai_query_request(event, request_id):
    raw_body = event.get("body")
    if raw_body is None or raw_body == "":
        return None, _error(400, "INVALID_AI_REQUEST", "request body is required", request_id)
    if not isinstance(raw_body, str):
        return None, _error(400, "INVALID_AI_REQUEST", "request body must be text", request_id)

    try:
        if event.get("isBase64Encoded") is True:
            decoded = base64.b64decode(raw_body, validate=True)
        else:
            decoded = raw_body.encode("utf-8")
    except (ValueError, base64.binascii.Error) as exc:
        return None, _error(400, "INVALID_AI_REQUEST", f"invalid request body encoding: {exc}", request_id)
    if len(decoded) > AI_QUERY_MAX_BODY_BYTES:
        return None, _error(
            400,
            "INVALID_AI_REQUEST",
            f"request body must be at most {AI_QUERY_MAX_BODY_BYTES} bytes",
            request_id,
        )

    try:
        request = json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, _error(400, "INVALID_AI_REQUEST", f"request body is not valid JSON: {exc}", request_id)
    if not isinstance(request, dict):
        return None, _error(400, "INVALID_AI_REQUEST", "request body must be a JSON object", request_id)

    issues = []
    unknown = sorted(set(request) - AI_QUERY_ALLOWED_KEYS)
    if unknown:
        issues.append(f"unsupported fields: {', '.join(unknown)}")

    action = request.get("action")
    if action not in AI_QUERY_ACTIONS:
        issues.append("action must be one of explain, policyCopilot, qa")

    question = request.get("question")
    if question is not None and not isinstance(question, str):
        issues.append("question must be a string or null")
    elif isinstance(question, str) and len(question) > AI_QUERY_MAX_QUESTION_CHARS:
        issues.append(f"question must be at most {AI_QUERY_MAX_QUESTION_CHARS} characters")
    if action == "qa" and (not isinstance(question, str) or not question.strip()):
        issues.append("question is required for action=qa")

    for field in ("focusDistrict", "focusArea"):
        value = request.get(field)
        if value is not None and not isinstance(value, str):
            issues.append(f"{field} must be a string or null")
        elif isinstance(value, str) and len(value) > 100:
            issues.append(f"{field} must be at most 100 characters")

    period = request.get("period")
    if period is not None and (
        not isinstance(period, str) or AI_QUERY_ROC_PERIOD_PATTERN.fullmatch(period) is None
    ):
        issues.append("period must be a three-digit ROC year or five-digit ROC month")

    web_search = request.get("webSearch")
    if web_search is not None:
        if not isinstance(web_search, dict):
            issues.append("webSearch must be an object")
        else:
            unknown_web_search = sorted(set(web_search) - AI_QUERY_WEB_SEARCH_KEYS)
            if unknown_web_search:
                issues.append(f"unsupported webSearch fields: {', '.join(unknown_web_search)}")
            if "enabled" in web_search and not isinstance(web_search["enabled"], bool):
                issues.append("webSearch.enabled must be a boolean")
            if "scope" in web_search and web_search["scope"] not in AI_QUERY_WEB_SEARCH_SCOPES:
                issues.append("webSearch.scope must be all or trusted")
            if "contextSize" in web_search and web_search["contextSize"] not in AI_QUERY_WEB_SEARCH_CONTEXT_SIZES:
                issues.append("webSearch.contextSize must be low, medium, or high")

    if issues:
        return None, _error(400, "INVALID_AI_REQUEST", "invalid public AI query request", request_id, issues)
    return request, None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        client_options = {}
        try:
            from botocore.config import Config

            client_options["config"] = Config(
                connect_timeout=2,
                read_timeout=25,
                retries={"max_attempts": 0},
            )
        except ImportError:
            # Local unit tests intentionally provide a tiny boto3 fake. AWS Lambda
            # always includes botocore, so the production client still gets the
            # explicit timeout above.
            pass
        _lambda_client = boto3.client("lambda", **client_options)
    return _lambda_client


def _is_lambda_timeout(error):
    if isinstance(error, TimeoutError):
        return True
    return error.__class__.__name__ in {
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "EndpointConnectionError",
    }


ROUTES = [
    ("POST", re.compile(r"^/api/v1/ai/query$"), _handle_ai_query),
    ("GET", re.compile(r"^/api/v1/health$"), _handle_health),
    ("GET", re.compile(r"^/api/v1/catalog$"), _handle_catalog),
    ("GET", re.compile(r"^/api/v1/dashboard/overview$"), _handle_dashboard_overview),
    ("GET", re.compile(r"^/api/v1/districts/([^/]+)$"), _handle_district),
    ("GET", re.compile(r"^/api/v1/analyses/([^/]+)$"), _handle_analysis),
]


def handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "unknown"
    try:
        http = event.get("requestContext", {}).get("http", {})
        method = http.get("method", "GET")
        path = event.get("rawPath", "/")
        qs = event.get("queryStringParameters") or {}
        if method == "OPTIONS":
            return _cors_preflight_response()
        for route_method, pattern, fn in ROUTES:
            if method != route_method:
                continue
            m = pattern.match(path)
            if m:
                if fn is _handle_ai_query:
                    return fn(m, qs, request_id, event)
                return fn(m, qs, request_id)
        return _error(404, "NOT_FOUND", f"no route for {method} {path}", request_id)
    except Exception as exc:  # pragma: no cover - defensive
        return _error(500, "INTERNAL_ERROR", str(exc), request_id)
