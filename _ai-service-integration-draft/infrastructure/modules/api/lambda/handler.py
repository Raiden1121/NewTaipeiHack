"""Single Lambda serving the 5 read endpoints in api_contract.md, plus the
AI Service bridge (POST /api/v1/ai/{action}).

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
If the table has no `META/MANIFEST` item yet, every endpoint but `/health`
returns 503 `SNAPSHOT_UNAVAILABLE`.

--- AI Service bridge -------------------------------------------------------

`POST /api/v1/ai/{action}` (action = explain | policyCopilot | qa) is the
piece infrastructure.md lists as not yet built: "backend 實際呼叫這支 Lambda
的程式碼". ai-service's own Lambda (ai-service/src/handlers/lambda.ts) does
NOT read DynamoDB or any local file in its deployed form — see
ai-service/DEPLOYMENT.md section 1 — it only accepts an already-assembled
`AiRequestContext` (evidence included) in its request body. So *this* file is
where "read DynamoDB, then call Bedrock" actually has to happen: we read the
same analytics items this Lambda already reads for the dashboard endpoints,
reshape their scalar fields into `AiEvidence` records
(ai-service/src/types/aiEvidence.ts), and invoke the ai-service Lambda
directly via IAM (`lambda:InvokeFunction`, no API Gateway in between).

Known caveat, deliberately not hidden: the analytics table stores
API-response-shaped items (dashboard KPIs, per-district summaries, named
analysis payloads), not the generic per-metric row shape ai-service's own
`shared/src/aiContextTable.ts` originally proposed. There is no ready-made
metricId/value row to copy — every scalar field on an item becomes its own
AiEvidence entry via `_flatten_scalars()`. That's honest but coarse: it
can't know a field's `unit` or `youthEligibility` on its own, so those come
from `_METRIC_META` (extend it as gaps show up in AI answers) and default to
`(None, "context_only")` otherwise. Nested list/dict fields (budgetTrend[],
keyword lists, …) are skipped rather than guessed at — see `knownLimitations`
in `_build_ai_context()`, which says out loud what was left out, the same
"honest degrade" pattern the rest of this codebase uses.

This route is deliberately NOT exposed through the API Gateway HTTP API
above: that API's integration timeout is a hard, non-configurable 30s
ceiling, and live Q&A alone measures 14-30s before any retry
(BEDROCK_MAX_ATTEMPTS defaults to 2). It goes out via a separate Lambda
Function URL instead (infrastructure/modules/api/main.tf), which has no such
cap and just inherits this Lambda's own `timeout`.
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

_lambda_client = boto3.client("lambda")
_AI_SERVICE_LAMBDA_NAME = os.environ.get("AI_SERVICE_LAMBDA_NAME")

# analysis_id -> extra (pk, sk) this analysis reuses instead of duplicating
# in its own item (see dynamodb_schema.md's no-duplication note for each).
_ANALYSIS_EXTRA_KEYS = {
    "politics-resource-io": ("DASHBOARD", "POLICY"),
    "policy-outcomes": ("DASHBOARD", "POPULATION_TREND"),
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


def _error(status, code, message, request_id, details=None):
    return _response(status, {
        "error": {"code": code, "message": message, "details": details or []},
        "request_id": request_id,
    })


def _parse_body(raw, is_base64_encoded):
    if not raw:
        return None
    decoded = base64.b64decode(raw).decode("utf-8") if is_base64_encoded else raw
    try:
        return json.loads(decoded)
    except json.JSONDecodeError:
        return None


# --- route handlers ----------------------------------------------------------
# Every handler now takes `body` (parsed JSON, or None) even though only
# `_handle_ai_run` uses it — keeping the signature uniform keeps the ROUTES
# dispatch loop below a single, boring line.

def _handle_health(match, qs, body, request_id):
    fetch = _get_items([("META", "MANIFEST")])
    manifest = fetch.get(("META", "MANIFEST"))
    body_ = {"status": "ok" if manifest else "degraded", "manifest_readable": manifest is not None}
    return _response(200, _envelope(manifest or {}, body_))


def _handle_catalog(match, qs, body, request_id):
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


def _handle_dashboard_overview(match, qs, body, request_id):
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


def _handle_district(match, qs, body, request_id):
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


def _handle_analysis(match, qs, body, request_id):
    analysis_id = match.group(1)
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
    elif analysis_id == "policy-outcomes":
        # populationTrend[] isn't stored on the analysis item (see
        # dynamodb_schema.md) — reshaped here from DASHBOARD/POPULATION_TREND.
        # yoy is a genuine per-year calculation, not just a reshape, so this
        # is a deliberate, documented exception to "Lambda doesn't compute".
        pop_years = fetch.get(("DASHBOARD", "POPULATION_TREND"), {}).get("years") or []
        population_trend = []
        prev = None
        for y in pop_years:
            pop = y["city"]["youth_population"]
            yoy = round((pop - prev) / prev * 100, 2) if prev else None
            population_trend.append({"year_roc": y["year_roc"], "population": pop, "yoy": yoy})
            prev = pop
        data["populationTrend"] = population_trend

    return _response(200, _envelope(manifest, data))


# --- AI Service bridge -------------------------------------------------------

# field name (as it appears on a DynamoDB item) -> (unit, youthEligibility).
# Anything not listed defaults to (None, "context_only") — safe but
# conservative. Extend this as gaps show up in AI answers (e.g. the model
# not being told a value is in NT$ or that it's a youth-specific figure).
_METRIC_META = {
    "youth_18_35_total": ("人", "eligible"),
    "opportunityIndex": (None, "eligible"),
    "retentionRisk": (None, "eligible"),
    "youthBoroughChiefRatioPercent": ("%", "eligible"),
    "yrr": (None, "eligible"),
    "currentBudget": ("元", "context_only"),
    "budgetYoY": ("%", "context_only"),
    "executionRate": ("%", "context_only"),
    "population_total": ("人", "context_only"),
}


def _evidence_id(dataset, period, district_id, metric_id):
    return f"{dataset}:{period}:{district_id or 'city'}:{metric_id}"


def _flatten_scalars(item, *, dataset, geo_level, district_id, district_name, period,
                      source_path, fetched_at, skip=()):
    """Turn a dict's top-level scalar fields into one AiEvidence dict each.

    Only int/float/str/bool/Decimal leaves become evidence — nested dict/list
    fields are skipped (see `skipped`) rather than guessed at. Every value in
    this table is already a finished, computed number (dynamodb_schema.md:
    "任何需要算術的收斂...寫進表裡就是最終值"), so `metricSource` is always
    `analytics_metric`, never `record_field` — these are never single raw
    records.
    """
    evidence = []
    skipped = []
    for key, value in item.items():
        if key in ("pk", "sk") or key in skip:
            continue
        if isinstance(value, (dict, list)):
            skipped.append(key)
            continue
        if value is None:
            continue
        unit, youth_eligibility = _METRIC_META.get(key, (None, "context_only"))
        numeric_value = float(value) if isinstance(value, Decimal) else value
        evidence.append({
            "evidenceId": _evidence_id(dataset, period, district_id, key),
            "dataset": dataset,
            "source": "data_pipeline_analytics",
            "sourceRecordId": None,
            "sourceUrl": None,
            "sourceKind": "dataset",
            "geoLevel": geo_level,
            "districtId": district_id,
            "districtName": district_name,
            "period": period,
            "periodStart": None,
            "periodEnd": None,
            "periodType": None,
            "metricId": key,
            "metricSource": "analytics_metric",
            "value": numeric_value,
            "unit": unit,
            "computation": None,
            "ageScope": None,
            "youthEligibility": youth_eligibility,
            "qualityFlags": [],
            "sourcePath": source_path,
            "fetchedAt": fetched_at,
        })
    return evidence, skipped


def _district_id_for_name(districts_item, name):
    for d in (districts_item or {}).get("districts", []) or []:
        if d.get("district_name") == name or d.get("districtName") == name:
            return d.get("district_id") or d.get("districtId")
    return None


def _build_ai_context(question, focus_district_name, focus_area, web_search):
    """Assemble an `AiRequestContext` dict (aiEvidence.ts's
    AiRequestContextSchema — field names below are the exact camelCase wire
    names, not Python convention) straight from the analytics table.

    Deliberately simple for a hackathon deadline: always reads
    META/MANIFEST + DASHBOARD/DISTRICTS (city-wide, all 29 districts — lets
    the model answer cross-district ranking questions) plus, when a district
    is named, that district's own DISTRICT#<id>/SUMMARY item. `focusArea`
    isn't yet used to pick which ANALYSIS#* items to pull in the way
    ai-service's own ANALYTICS_ARTIFACTS_BY_FOCUS_AREA does for the
    local-file path — add that here if prompt size becomes a problem.

    Returns (context_dict_or_None, extra_error_notes). context is None only
    when there is no published snapshot at all (mirrors the 503
    SNAPSHOT_UNAVAILABLE the read endpoints already return in that case).
    """
    keys = [("META", "MANIFEST"), ("DASHBOARD", "DISTRICTS")]
    fetch = _get_items(keys)
    manifest = fetch.get(("META", "MANIFEST"))
    if manifest is None:
        return None, []

    period = str(manifest.get("snapshot_id") or "unknown")
    fetched_at = manifest.get("generated_at")
    notes = []
    evidence = []

    districts_item = fetch.get(("DASHBOARD", "DISTRICTS"))
    district_list = (districts_item or {}).get("districts") or []
    if district_list:
        for d in district_list:
            if not isinstance(d, dict):
                continue
            d_id = d.get("district_id") or d.get("districtId")
            d_name = d.get("district_name") or d.get("districtName")
            flattened, _skipped = _flatten_scalars(
                d, dataset="analytics_dashboard_districts", geo_level="district",
                district_id=d_id, district_name=d_name, period=period,
                source_path="DASHBOARD/DISTRICTS", fetched_at=fetched_at,
                skip=("district_id", "districtId", "district_name", "districtName"),
            )
            evidence.extend(flattened)
        notes.append(
            f"已納入全 29 區的 DASHBOARD/DISTRICTS 指標，共 {len(district_list)} 區，可用於跨區比較與排名問題。"
        )
    else:
        notes.append("DASHBOARD/DISTRICTS 目前沒有資料，無法提供跨區比較。")

    district_id = None
    if focus_district_name:
        district_id = _district_id_for_name(districts_item, focus_district_name)
        if district_id:
            summary_fetch = _get_items([(f"DISTRICT#{district_id}", "SUMMARY")])
            summary = summary_fetch.get((f"DISTRICT#{district_id}", "SUMMARY"))
            if summary:
                flattened, _skipped = _flatten_scalars(
                    summary, dataset="analytics_district_summary", geo_level="district",
                    district_id=summary.get("district_id"), district_name=summary.get("district_name"),
                    period=period, source_path=f"DISTRICT#{district_id}/SUMMARY", fetched_at=fetched_at,
                    skip=("district_id", "district_name"),
                )
                evidence.extend(flattened)
            else:
                notes.append(f"DynamoDB 沒有 {focus_district_name}（{district_id}）的 DISTRICT#/SUMMARY 項目。")
        else:
            notes.append(f"無法辨識行政區名稱「{focus_district_name}」，本次未套用行政區篩選。")

    notes.append(
        f"本次 evidence 全部來自 analytics DynamoDB 表（{os.environ.get('ANALYTICS_TABLE_NAME', '')}），"
        "metricSource 一律標記為 analytics_metric：這張表存的是已經算好的最終值，"
        "不是逐筆原始資料，AI Service 不會、也不能再對這些數字做任何運算。"
        "巢狀欄位（例如 budgetTrend、populationTrend、關鍵字清單）目前未攤平進 evidence，"
        "若問題涉及這些面向，本次回應可能無法涵蓋。"
    )

    return {
        "question": question,
        "focusDistrict": focus_district_name,
        "focusArea": focus_area,
        "evidence": evidence,
        "knownLimitations": notes,
        "webFindings": [],
        "webSearch": web_search or {"enabled": False, "contextSize": "low", "scope": "all"},
    }, []


def _handle_ai_run(match, qs, body, request_id):
    if not _AI_SERVICE_LAMBDA_NAME:
        return _error(503, "AI_SERVICE_NOT_CONFIGURED", "AI_SERVICE_LAMBDA_NAME 環境變數未設定", request_id)

    action = match.group(1)
    if action not in ("explain", "policyCopilot", "qa"):
        return _error(400, "UNKNOWN_ACTION", f"未知的 action: {action}（合法值：explain / policyCopilot / qa）", request_id)

    payload = body or {}
    context, _extra_errors = _build_ai_context(
        question=payload.get("question"),
        focus_district_name=payload.get("focusDistrict"),
        focus_area=payload.get("focusArea"),
        web_search=payload.get("webSearch"),
    )
    if context is None:
        return _error(503, "SNAPSHOT_UNAVAILABLE", "no published snapshot available", request_id)

    ai_request = {"action": action, "context": context}
    try:
        response = _lambda_client.invoke(
            FunctionName=_AI_SERVICE_LAMBDA_NAME,
            InvocationType="RequestResponse",
            # ai-service's own handler expects the same API-Gateway-proxy-ish
            # {body, isBase64Encoded} shape it uses in production — see
            # ai-service/src/handlers/lambda.ts's LambdaEvent.
            Payload=json.dumps({"body": json.dumps(ai_request, ensure_ascii=False, cls=_DecimalEncoder)}).encode("utf-8"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return _error(502, "AI_SERVICE_INVOKE_FAILED", str(exc), request_id)

    raw_payload = response["Payload"].read()
    if response.get("FunctionError"):
        return _error(502, "AI_SERVICE_ERROR", raw_payload.decode("utf-8", "replace"), request_id)

    try:
        inner = json.loads(raw_payload)
        inner_body = json.loads(inner.get("body", "{}"))
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        return _error(502, "AI_SERVICE_BAD_RESPONSE", str(exc), request_id)

    return _response(inner.get("statusCode", 502), inner_body)


ROUTES = [
    ("GET", re.compile(r"^/api/v1/health$"), _handle_health),
    ("GET", re.compile(r"^/api/v1/catalog$"), _handle_catalog),
    ("GET", re.compile(r"^/api/v1/dashboard/overview$"), _handle_dashboard_overview),
    ("GET", re.compile(r"^/api/v1/districts/([^/]+)$"), _handle_district),
    ("GET", re.compile(r"^/api/v1/analyses/([^/]+)$"), _handle_analysis),
    ("POST", re.compile(r"^/api/v1/ai/([^/]+)$"), _handle_ai_run),
]


def handler(event, context):
    request_id = getattr(context, "aws_request_id", None) or "unknown"
    try:
        http = event.get("requestContext", {}).get("http", {})
        method = http.get("method", "GET")
        path = event.get("rawPath", "/")
        qs = event.get("queryStringParameters") or {}
        body = _parse_body(event.get("body"), event.get("isBase64Encoded", False))
        for route_method, pattern, fn in ROUTES:
            if method != route_method:
                continue
            m = pattern.match(path)
            if m:
                return fn(m, qs, body, request_id)
        return _error(404, "NOT_FOUND", f"no route for {method} {path}", request_id)
    except Exception as exc:  # pragma: no cover - defensive
        return _error(500, "INTERNAL_ERROR", str(exc), request_id)
