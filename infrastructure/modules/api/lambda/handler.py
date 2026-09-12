"""Single Lambda serving the 5 read endpoints in api_contract.md.

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
"""

import json
import os
import re
from decimal import Decimal

import boto3

API_VERSION = "v1"

_dynamodb = boto3.resource("dynamodb")
_TABLE_NAME = os.environ["ANALYTICS_TABLE_NAME"]

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


ROUTES = [
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
        for route_method, pattern, fn in ROUTES:
            if method != route_method:
                continue
            m = pattern.match(path)
            if m:
                return fn(m, qs, request_id)
        return _error(404, "NOT_FOUND", f"no route for {method} {path}", request_id)
    except Exception as exc:  # pragma: no cover - defensive
        return _error(500, "INTERNAL_ERROR", str(exc), request_id)


