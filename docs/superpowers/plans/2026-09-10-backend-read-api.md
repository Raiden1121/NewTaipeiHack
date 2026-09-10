# Backend Read API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立由 Node.js 執行、以 TypeScript 撰寫的唯讀 Dashboard REST API，先以 Local JSON published snapshot 完成可測試 vertical slice，再保留 DynamoDB storage adapter 的替換點。

**Architecture:** Lambda handler 只負責 API Gateway event adapter；純函式 application/router 負責 validation、use case 與 response envelope。Backend 只讀取 manifest 指定的 published analytics artifact，不直接呼叫 data-pipeline 或政府 API；Local JSON 與 DynamoDB 透過相同的 `PublishedDataStore` 介面替換。

**Tech Stack:** Node.js runtime, TypeScript, AWS Lambda HTTP API v2 event, Zod runtime validation, Vitest, `@types/aws-lambda`, AWS SDK v3 DynamoDB adapter。

**Spec:** `docs/superpowers/specs/2026-09-10-backend-read-api-design.md`

## Global Constraints

- Backend runtime is Node.js; TypeScript is the source language and compiles to JavaScript before Lambda execution.
- Backend does not call government APIs, run ETL, calculate Opportunity Index, calculate Retention Risk, or calculate cross-topic statistics during a request.
- Backend reads one atomic published snapshot selected by `current.json` and the snapshot `manifest.json`.
- JSON missing values remain `null`; no unavailable value is converted to `0`.
- `raw_record`, `raw_records`, PDF artifacts, arbitrary file paths, and unvalidated dataset names are never returned to clients.
- API paths are versioned under `/api/v1`.
- `district_id` joins must use the canonical New Taipei district id; no nearest-district fallback is allowed.
- County, national, organization, and official age-group data must carry proxy/context metadata when returned with district data.
- Frontend migration, analytics implementation, AWS CDK resources, and AI Service integration are separate follow-up work unless explicitly added to the task scope.
- Do not run `git add`, `git commit`, merge, or push; leave all implementation changes in the working tree for review.

---

## File and Responsibility Map

Files created by this plan:

- `backend/tsconfig.json`: Backend compiler settings and `dist` output.
- `backend/vitest.config.ts`: Backend test environment and path configuration.
<<<<<<< ours
- `shared/tsconfig.json`: Shared type-checking configuration.
=======
>>>>>>> theirs
- `backend/src/handler.ts`: API Gateway HTTP API v2 Lambda adapter.
- `backend/src/app.ts`: Pure application entry accepting a normalized request.
- `backend/src/config.ts`: Environment parsing for data root, origins, and cache values.
- `backend/src/http/router.ts`: Explicit method/path routing and parameter extraction.
<<<<<<< ours
- `backend/src/http/types.ts`: Normalized request and response types used by the app and Lambda adapter.
=======
>>>>>>> theirs
- `backend/src/http/response.ts`: Success, error, CORS, cache, and request-id headers.
- `backend/src/http/errors.ts`: Typed application errors and HTTP status mapping.
- `backend/src/application/catalog.ts`: Catalog/readiness use case.
- `backend/src/application/dashboard.ts`: Dashboard overview use case.
- `backend/src/application/districts.ts`: District detail use case.
- `backend/src/application/analyses.ts`: Analysis lookup use case.
- `backend/src/ports/publishedDataStore.ts`: Storage port shared by local and DynamoDB adapters.
- `backend/src/adapters/localPublishedDataStore.ts`: Manifest-controlled Local JSON reader.
- `backend/src/adapters/dynamoMetricsStore.ts`: DynamoDB implementation of the storage port.
- `backend/src/schemas/requests.ts`: Zod schemas for query and path parameters.
- `backend/src/schemas/responses.ts`: Runtime schemas for published data and API DTOs.
- `backend/tests/fixtures/published/*`: Small deterministic published snapshot fixture.
- `backend/tests/*.test.ts`: Unit, handler, adapter, and contract tests.
- `shared/src/api.ts`, `shared/src/metrics.ts`, `shared/src/index.ts`: Cross-package API types.

Files explicitly not modified by this Backend plan:

- `data-pipeline/src/collectors/`: source collection remains unchanged.
- `data-pipeline/src/transform/`: raw-to-curated transform remains unchanged.
- `data-pipeline/src/analytics/`: required published analytics producer is a separate pipeline task; this plan only defines the input contract and local fixture.
- `infrastructure/`: AWS resources require a separate CDK implementation plan.
- `frontend/src/`: API migration occurs after Backend contract tests pass.

## Task 1: Initialize Node.js + TypeScript Backend and Shared Contract

**Files:**

- Modify: `backend/package.json`
- Modify: `shared/package.json`
- Create: `backend/tsconfig.json`
- Create: `backend/vitest.config.ts`
<<<<<<< ours
- Create: `shared/tsconfig.json`
=======
>>>>>>> theirs
- Create: `shared/src/metrics.ts`
- Create: `shared/src/api.ts`
- Create: `shared/src/index.ts`
- Create: `backend/tests/contracts.test.ts`

**Interfaces:**

- Produces `MetricStatus = "available" | "partial" | "unavailable"`.
- Produces `YouthEligibility = "eligible" | "proxy_only" | "context_only"`.
- Produces `PeriodType = "day" | "month" | "year" | "snapshot"`.
- Produces `MetricValue<T = number>` with `metric_id`, `value: T | null`, `unit`, period fields, `geo_level`, `youth_eligibility`, `source`, `quality_flags`, `status`, and `is_proxy`.
- Produces `ApiMeta` with `api_version`, `snapshot_id`, `generated_at`, `as_of`, and `warnings`.
- Produces `ApiResponse<T> = { data: T; meta: ApiMeta }` and `ApiErrorResponse`.
- Produces `PeriodSelection = { period?: string; timeframe?: "recent_3y" | "historical_10y" }`.

- [ ] **Step 1: Write the failing contract test**

```ts
import { describe, expect, it } from "vitest";
import type { ApiResponse, MetricValue } from "@newtaipei-youth/shared";

describe("shared API contract", () => {
  it("allows an unavailable metric without replacing its value with zero", () => {
    const metric: MetricValue = {
      metric_id: "national_youth_18_35_total",
      value: null,
      unit: "people",
      period_start: null,
      period_end: null,
      period_type: "year",
      geo_level: "national",
      youth_eligibility: "eligible",
      source: null,
      quality_flags: ["source_not_available"],
      status: "unavailable",
      is_proxy: false,
    };

    const response: ApiResponse<{ metric: MetricValue }> = {
      data: { metric },
      meta: {
        api_version: "v1",
        snapshot_id: "fixture-snapshot",
        generated_at: "2026-09-10T00:00:00Z",
        as_of: "2026-07-31",
        warnings: [],
      },
    };

    expect(response.data.metric.value).toBeNull();
    expect(response.data.metric.status).toBe("unavailable");
  });
});
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- contracts.test.ts
```

Expected: FAIL because the Backend TypeScript/Vitest configuration and shared contract exports do not exist.

- [ ] **Step 3: Add the package scripts and compiler configuration**

Add these scripts to `backend/package.json`:

```json
{
  "type": "module",
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint ."
  }
}
```

Add runtime/build dependencies for `zod` and `@newtaipei-youth/shared`, plus development dependencies for `typescript`, `tsx`, `vitest`, `@types/node`, and `@types/aws-lambda`. Configure `tsconfig.json` with `target: ES2022`, `module: NodeNext`, `moduleResolution: NodeNext`, `rootDir: "src"`, `outDir: "dist"`, `strict: true`, and `declaration: true`.

<<<<<<< ours
Configure `shared/package.json` as an ESM, types-only workspace package and add `shared/tsconfig.json` with `target: ES2022`, `module: NodeNext`, `moduleResolution: NodeNext`, `strict: true`, and `noEmit: true`. Add the Backend `tsconfig.json` path mapping `@newtaipei-youth/shared` to `../shared/src/index.ts`; all Backend imports of shared definitions must use `import type` so the compiled Lambda does not require a runtime Shared module.

Create `backend/vitest.config.ts` with Node environment and the same `@newtaipei-youth/shared` alias:

```ts
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@newtaipei-youth/shared": fileURLToPath(
        new URL("../shared/src/index.ts", import.meta.url),
      ),
    },
  },
  test: { environment: "node" },
});
```

=======
>>>>>>> theirs
- [ ] **Step 4: Define and export the shared metric and API types**

Create the types used by all later tasks:

```ts
export type MetricStatus = "available" | "partial" | "unavailable";
export type YouthEligibility = "eligible" | "proxy_only" | "context_only";
export type PeriodType = "day" | "month" | "year" | "snapshot";

export interface MetricValue<T = number> {
  metric_id: string;
  value: T | null;
  unit: string | null;
  period_start: string | null;
  period_end: string | null;
  period_type: PeriodType;
  geo_level: "district" | "county" | "national" | "organization";
  youth_eligibility: YouthEligibility;
  source: string | null;
  quality_flags: string[];
  status: MetricStatus;
  is_proxy: boolean;
}
```

Export the types from `shared/src/index.ts` and make the Backend workspace resolve `@newtaipei-youth/shared` through the repository workspace.

- [ ] **Step 5: Run the focused test and compiler**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- contracts.test.ts
npm --workspace @newtaipei-youth/backend run build
```

Expected: the contract test passes and TypeScript emits `backend/dist` without errors.

## Task 2: Build the Published Snapshot Port and Local JSON Adapter

**Files:**

- Create: `backend/src/config.ts`
- Create: `backend/src/ports/publishedDataStore.ts`
- Create: `backend/src/schemas/responses.ts`
- Create: `backend/src/adapters/localPublishedDataStore.ts`
- Create: `backend/tests/fixtures/published/current.json`
- Create: `backend/tests/fixtures/published/fixture-snapshot/manifest.json`
- Create: `backend/tests/fixtures/published/fixture-snapshot/dashboard_overview.json`
- Create: `backend/tests/fixtures/published/fixture-snapshot/district_details.json`
- Create: `backend/tests/fixtures/published/fixture-snapshot/analyses/housing-affordability.json`
- Create: `backend/tests/localPublishedDataStore.test.ts`

**Interfaces:**

- Produces `PublishedManifest` with `schema_version`, `snapshot_id`, `generated_at`, `as_of`, `artifacts`, `datasets`, and `warnings`.
<<<<<<< ours
- Produces `PublishedCatalog`, `DashboardOverview`, `DistrictDetail`, and `AnalysisResult` DTOs validated by runtime schemas.
- Produces `PublishedDataStore`:

Define the published DTOs in `shared/src/api.ts`:

```ts
export interface PublishedManifest {
  schema_version: 1;
  snapshot_id: string;
  generated_at: string;
  as_of: string | null;
  artifacts: {
    dashboard_overview: string;
    district_details: string;
    analyses: Record<string, string>;
  };
  datasets: Array<Record<string, unknown>>;
  warnings: string[];
}

export interface PublishedCatalog extends ApiMeta {
  datasets: Array<Record<string, unknown>>;
}

export interface DistrictSummary {
  district_id: string;
  district_name: string;
  metrics: Record<string, MetricValue>;
}

export interface DomainBlock {
  status: MetricStatus;
  metrics: MetricValue[];
  limitations: string[];
}

export interface DashboardOverview {
  kpis: Record<string, MetricValue>;
  districts: DistrictSummary[];
  availability: Record<string, MetricStatus>;
}

export interface DistrictDetail {
  district: { district_id: string; district_name: string };
  employment: DomainBlock;
  housing: DomainBlock;
  fertility: DomainBlock;
  transport: DomainBlock;
  resources: DomainBlock;
  limitations: string[];
}

export interface AnalysisResult {
  analysis_id: string;
  x_metric: string;
  y_metric: string;
  geo_level: string;
  period: { start: string | null; end: string | null };
  data: Array<Record<string, unknown>>;
  statistics: {
    correlation: number | null;
    sample_size: number | null;
    method: string | null;
  };
  limitations: string[];
}
```

=======
- Produces `DashboardOverview`, `DistrictDetail`, and `AnalysisResult` DTOs validated by runtime schemas.
- Produces `PublishedDataStore`:

>>>>>>> theirs
```ts
export interface PublishedDataStore {
  getCatalog(): Promise<PublishedCatalog>;
  getDashboardOverview(selection: PeriodSelection): Promise<DashboardOverview>;
  getDistrictDetail(
    districtId: string,
    selection: PeriodSelection,
  ): Promise<DistrictDetail | null>;
  getAnalysis(
    analysisId: string,
    selection: PeriodSelection,
  ): Promise<AnalysisResult | null>;
  checkReadiness(): Promise<{ ready: boolean; reason?: string }>;
}
```

- [ ] **Step 1: Write failing local adapter tests**

```ts
import { describe, expect, it } from "vitest";
import { LocalPublishedDataStore } from "../src/adapters/localPublishedDataStore";

describe("LocalPublishedDataStore", () => {
  it("loads only the snapshot selected by current.json", async () => {
    const store = new LocalPublishedDataStore({
<<<<<<< ours
      rootDir: "tests/fixtures/published",
=======
      rootDir: "backend/tests/fixtures/published",
>>>>>>> theirs
    });

    const catalog = await store.getCatalog();

    expect(catalog.snapshot_id).toBe("fixture-snapshot");
    expect(catalog.datasets).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ dataset: "population" }),
      ]),
    );
  });

  it("returns null for an unknown district without reading an arbitrary path", async () => {
    const store = new LocalPublishedDataStore({
<<<<<<< ours
      rootDir: "tests/fixtures/published",
=======
      rootDir: "backend/tests/fixtures/published",
>>>>>>> theirs
    });

    await expect(
      store.getDistrictDetail("99999999", {}),
    ).resolves.toBeNull();
  });
});
```

- [ ] **Step 2: Run the adapter tests and verify they fail**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- localPublishedDataStore.test.ts
```

Expected: FAIL because the port, schemas, fixture, and adapter do not exist.

- [ ] **Step 3: Create the deterministic published fixture**

Create `current.json` containing only:

```json
{ "snapshot_id": "fixture-snapshot" }
```

<<<<<<< ours
Create a manifest whose artifact paths are relative, manifest-controlled paths. The overview fixture contains all 29 canonical districts; the detail fixture contains at least `65000010` and an unavailable metric. Every metric must include status, period, source, eligibility, and quality fields; include one `unavailable` metric with `value: null` and no `raw_record`.
=======
Create a manifest whose artifact paths are relative, manifest-controlled paths. Include exactly three districts in the fixture test data and a separate contract assertion for the production-shaped 29-district overview. Every metric must include status, period, source, eligibility, and quality fields; include one `unavailable` metric with `value: null` and no `raw_record`.
>>>>>>> theirs

- [ ] **Step 4: Implement config and manifest-controlled file access**

`config.ts` must read `BACKEND_DATA_ROOT` with a default suitable for local tests, `BACKEND_ALLOWED_ORIGINS` as a comma-separated list, and `BACKEND_CACHE_MAX_AGE_SECONDS` as a non-negative integer. Reject a root that does not exist at readiness time.

`LocalPublishedDataStore` must:

1. Read `current.json`.
2. Validate the snapshot id as a single safe path component.
3. Read and validate that snapshot's `manifest.json`.
4. Resolve only artifact paths present in the manifest.
5. Reject absolute paths, `..` segments, non-JSON files, malformed JSON, and response data containing `raw_record` keys.
6. Return typed DTOs after Zod parsing.

- [ ] **Step 5: Run adapter tests and build**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- localPublishedDataStore.test.ts
npm --workspace @newtaipei-youth/backend run build
```

Expected: all adapter tests pass and the compiled adapter is emitted.

## Task 3: Add HTTP Core, Request Validation, and Health/Catalog Routes

**Files:**

- Create: `backend/src/http/errors.ts`
- Create: `backend/src/http/response.ts`
- Create: `backend/src/http/router.ts`
<<<<<<< ours
- Create: `backend/src/http/types.ts`
=======
>>>>>>> theirs
- Create: `backend/src/application/catalog.ts`
- Create: `backend/src/app.ts`
- Create: `backend/src/handler.ts`
- Create: `backend/src/schemas/requests.ts`
- Create: `backend/tests/router.test.ts`
- Create: `backend/tests/handler.test.ts`

**Interfaces:**

- Produces `createApp(store, config): App`.
- Produces `app.handle(request): Promise<HttpResponse>`.
- Produces `handler(event): Promise<APIGatewayProxyStructuredResultV2>`.
- Produces `parsePeriodSelection(query): PeriodSelection`.
- Produces `toHttpError(error): ApiErrorResponse`.
<<<<<<< ours
- Produces `getCatalog(store): Promise<PublishedCatalog>`.

Define the normalized HTTP interfaces in `backend/src/http/types.ts`:

```ts
export interface HttpRequest {
  method: string;
  path: string;
  query: Record<string, string | undefined>;
  headers: Record<string, string | undefined>;
  requestId?: string;
}

export interface HttpResponse {
  statusCode: number;
  headers: Record<string, string>;
  body: Record<string, unknown>;
}

export interface App {
  handle(request: HttpRequest): Promise<HttpResponse>;
}
```
=======
>>>>>>> theirs

- [ ] **Step 1: Write failing HTTP tests**

```ts
import { describe, expect, it } from "vitest";
import { createApp } from "../src/app";
import { LocalPublishedDataStore } from "../src/adapters/localPublishedDataStore";

describe("HTTP core", () => {
  it("returns readiness and catalog metadata", async () => {
    const app = createApp(
      new LocalPublishedDataStore({
<<<<<<< ours
        rootDir: "tests/fixtures/published",
=======
        rootDir: "backend/tests/fixtures/published",
>>>>>>> theirs
      }),
      { allowedOrigins: ["http://localhost:5173"], cacheMaxAgeSeconds: 60 },
    );

    const response = await app.handle({
      method: "GET",
      path: "/api/v1/catalog",
      query: {},
      headers: {},
    });

    expect(response.statusCode).toBe(200);
    expect(response.body).toMatchObject({
      data: { snapshot_id: "fixture-snapshot" },
      meta: { api_version: "v1" },
    });
  });

  it("rejects an unsupported timeframe before storage access", async () => {
    const store = { getCatalog: async () => { throw new Error("must not call"); } };
    const app = createApp(store as never, {
      allowedOrigins: [],
      cacheMaxAgeSeconds: 0,
    });

    const response = await app.handle({
      method: "GET",
      path: "/api/v1/dashboard/overview",
      query: { timeframe: "weekly" },
      headers: {},
    });

    expect(response.statusCode).toBe(400);
    expect(response.body.error.code).toBe("INVALID_QUERY");
  });
});
```

- [ ] **Step 2: Run the HTTP tests and verify they fail**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- router.test.ts handler.test.ts
```

Expected: FAIL because `createApp`, HTTP types, router, and handler do not exist.

- [ ] **Step 3: Implement typed errors and response helpers**

Implement these errors:

```ts
export class InvalidQueryError extends Error {}
export class DistrictNotFoundError extends Error {}
export class AnalysisNotFoundError extends Error {}
export class SnapshotUnavailableError extends Error {}
```

Map them to `400`, `404`, `404`, and `503`. Map unknown errors to `500 INTERNAL_ERROR` without stack traces. `response.ts` must add `content-type`, `x-request-id`, CORS headers for configured origins, and `cache-control` for successful published data responses.

- [ ] **Step 4: Implement allowlist request schemas and explicit router**

<<<<<<< ours
Implement `parsePeriodSelection(query)` so it accepts only `latest`, ISO `YYYY`, ISO `YYYY-MM`, `recent_3y`, and `historical_10y`. Reject empty values, both `period` and `timeframe` together, unsupported values, and repeated values. Route only these exact paths:
=======
Implement `parsePeriodSelection(query)` so it accepts only `latest`, three-digit ROC years converted by the published contract, ISO `YYYY` years, ISO `YYYY-MM`, `recent_3y`, and `historical_10y`. Reject empty values, both `period` and `timeframe` together, unsupported values, and repeated values. Route only these exact paths:
>>>>>>> theirs

```text
GET /api/v1/health
GET /api/v1/catalog
GET /api/v1/dashboard/overview
GET /api/v1/districts/{districtId}
GET /api/v1/analyses/{analysisId}
```

Return `404` for every other path and `405` for unsupported methods on a known path.

- [ ] **Step 5: Implement app and Lambda adapters**

`app.handle()` receives a normalized request and delegates to application services. `handler.ts` converts API Gateway HTTP API v2 `rawPath`, `requestContext.http.method`, `queryStringParameters`, and `headers` into that normalized request; it must generate a request id when API Gateway did not provide one. It must not read environment variables inside every route branch.

<<<<<<< ours
Implement `getCatalog(store)` in `application/catalog.ts` by calling `store.getCatalog()` once and returning the manifest metadata without loading dashboard rows. Connect `/api/v1/health` to `store.checkReadiness()` and `/api/v1/catalog` to `getCatalog(store)`; readiness failure returns `503 SNAPSHOT_UNAVAILABLE`.

=======
>>>>>>> theirs
- [ ] **Step 6: Run focused tests and build**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- router.test.ts handler.test.ts
npm --workspace @newtaipei-youth/backend run build
```

Expected: all HTTP tests pass and `dist/handler.js` is emitted.

## Task 4: Implement Dashboard Overview and District Detail Use Cases

**Files:**

- Create: `backend/src/application/dashboard.ts`
- Create: `backend/src/application/districts.ts`
- Modify: `backend/src/http/router.ts`
- Modify: `backend/src/app.ts`
- Create: `backend/tests/dashboard.test.ts`
- Create: `backend/tests/districts.test.ts`
- Modify: `backend/tests/fixtures/published/fixture-snapshot/dashboard_overview.json`
- Modify: `backend/tests/fixtures/published/fixture-snapshot/district_details.json`

**Interfaces:**

- Produces `getDashboardOverview(store, selection): Promise<DashboardOverview>`.
- Produces `getDistrictDetail(store, districtId, selection): Promise<DistrictDetail>`.
- `DashboardOverview` contains `kpis`, `districts`, and `availability`.
- `DistrictDetail` contains `district`, `employment`, `housing`, `fertility`, `transport`, `resources`, and `limitations` blocks; unavailable blocks remain present with `status: "unavailable"`.

- [ ] **Step 1: Write failing overview and detail tests**

```ts
import { describe, expect, it } from "vitest";
import { createApp } from "../src/app";
import { LocalPublishedDataStore } from "../src/adapters/localPublishedDataStore";

const app = createApp(
<<<<<<< ours
  new LocalPublishedDataStore({ rootDir: "tests/fixtures/published" }),
=======
  new LocalPublishedDataStore({ rootDir: "backend/tests/fixtures/published" }),
>>>>>>> theirs
  { allowedOrigins: [], cacheMaxAgeSeconds: 60 },
);

describe("dashboard and district routes", () => {
  it("returns one snapshot and 29 district summaries", async () => {
    const response = await app.handle({
      method: "GET",
      path: "/api/v1/dashboard/overview",
      query: { period: "latest" },
      headers: {},
    });

    expect(response.statusCode).toBe(200);
    expect(response.body.data.districts).toHaveLength(29);
    expect(new Set(response.body.data.districts.map((item: { district_id: string }) => item.district_id)).size).toBe(29);
    expect(response.body.meta.snapshot_id).toBe("fixture-snapshot");
  });

  it("returns 404 for an unknown district and preserves unavailable metrics", async () => {
    const missing = await app.handle({
      method: "GET",
      path: "/api/v1/districts/99999999",
      query: {},
      headers: {},
    });
    expect(missing.statusCode).toBe(404);

    const detail = await app.handle({
      method: "GET",
      path: "/api/v1/districts/65000010",
      query: {},
      headers: {},
    });
    expect(detail.statusCode).toBe(200);
    expect(detail.body.data.fertility.status).toBe("unavailable");
<<<<<<< ours
    expect(detail.body.data.fertility.metrics[0].value).toBeNull();
=======
    expect(detail.body.data.fertility.value).toBeNull();
>>>>>>> theirs
  });
});
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- dashboard.test.ts districts.test.ts
```

Expected: FAIL because the use cases and route handlers are not implemented.

- [ ] **Step 3: Implement the overview use case**

`getDashboardOverview()` must call `store.getDashboardOverview(selection)` exactly once, attach the catalog snapshot metadata, and return the existing 29 district records in published order. It must not sum raw records, calculate ratios, or fill missing metrics. The response must include a `national_youth_18_35_total` metric with `value: null` and `status: "unavailable"` when no national source exists.

- [ ] **Step 4: Implement the district detail use case**

Validate the district id against the canonical district id format and storage result. Return `DistrictNotFoundError` only when the requested district is not in the published snapshot. Keep county/national/organization data inside its domain block with `is_proxy: true` or `youth_eligibility: "context_only"`; do not attach it to a different district.

- [ ] **Step 5: Connect the routes and response envelope**

Connect `/dashboard/overview` and `/districts/{districtId}` to the two use cases. Both responses must include the same snapshot metadata used by the data blocks. A successful response must not contain any `raw_record` key at any nesting level.

- [ ] **Step 6: Run focused tests and build**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- dashboard.test.ts districts.test.ts
npm --workspace @newtaipei-youth/backend run build
```

Expected: all overview/detail tests pass and the handler compiles.

<<<<<<< ours
## Task 5: Implement Analysis Endpoint and Contract/Quality Checks

**Files:**

=======
## Task 5: Implement Catalog, Analysis Endpoint, and Contract/Quality Checks

**Files:**

- Create: `backend/src/application/catalog.ts` tests if not completed in Task 3
>>>>>>> theirs
- Create: `backend/src/application/analyses.ts`
- Modify: `backend/src/http/router.ts`
- Create: `backend/tests/analyses.test.ts`
- Create: `backend/tests/api-contract.test.ts`
- Create: `backend/tests/quality.test.ts`

**Interfaces:**

<<<<<<< ours
=======
- Produces `getCatalog(store): Promise<PublishedCatalog>`.
>>>>>>> theirs
- Produces `getAnalysis(store, analysisId, selection): Promise<AnalysisResult>`.
- Produces a contract assertion that checks snapshot consistency, district uniqueness, `null` missing values, and absence of raw fields.

- [ ] **Step 1: Write failing analysis and quality tests**

```ts
import { describe, expect, it } from "vitest";
import { createApp } from "../src/app";
import { LocalPublishedDataStore } from "../src/adapters/localPublishedDataStore";

describe("analysis route", () => {
  it("returns a published analysis with provenance", async () => {
    const app = createApp(
<<<<<<< ours
      new LocalPublishedDataStore({ rootDir: "tests/fixtures/published" }),
=======
      new LocalPublishedDataStore({ rootDir: "backend/tests/fixtures/published" }),
>>>>>>> theirs
      { allowedOrigins: [], cacheMaxAgeSeconds: 60 },
    );
    const response = await app.handle({
      method: "GET",
      path: "/api/v1/analyses/housing-affordability",
      query: { timeframe: "recent_3y" },
      headers: {},
    });

    expect(response.statusCode).toBe(200);
    expect(response.body.data.analysis_id).toBe("housing-affordability");
    expect(response.body.data.statistics).toHaveProperty("sample_size");
    expect(response.body.data.limitations).toEqual(expect.any(Array));
  });

  it("does not expose raw source records", async () => {
    const app = createApp(
<<<<<<< ours
      new LocalPublishedDataStore({ rootDir: "tests/fixtures/published" }),
=======
      new LocalPublishedDataStore({ rootDir: "backend/tests/fixtures/published" }),
>>>>>>> theirs
      { allowedOrigins: [], cacheMaxAgeSeconds: 60 },
    );
    const response = await app.handle({
      method: "GET",
      path: "/api/v1/dashboard/overview",
      query: {},
      headers: {},
    });

    expect(JSON.stringify(response.body)).not.toContain("raw_record");
    expect(JSON.stringify(response.body)).not.toContain("raw_records");
  });
});
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- analyses.test.ts api-contract.test.ts quality.test.ts
```

Expected: FAIL because analysis lookup and contract assertions are not implemented.

<<<<<<< ours
- [ ] **Step 3: Implement analysis lookup**

`getAnalysis()` accepts an analysis id only if the manifest lists it; calls the store once; and returns the precomputed `statistics`, `method`, `sample_size`, `limitations`, `geo_level`, and period without recomputing them. Catalog behavior is implemented in Task 3 and is covered by the HTTP contract tests.
=======
- [ ] **Step 3: Implement catalog and analysis lookup**

`getCatalog()` returns only manifest metadata: snapshot, generated time, as-of period, dataset entries, coverage, transform versions, and warnings. `getAnalysis()` accepts an analysis id only if the manifest lists it; calls the store once; and returns the precomputed `statistics`, `method`, `sample_size`, `limitations`, `geo_level`, and period without recomputing them.
>>>>>>> theirs

- [ ] **Step 4: Add recursive response quality assertions**

Implement a test helper that recursively visits response objects and fails if a key is `raw_record`, `raw_records`, `overview_raw_record`, `detail_raw_record`, `detail_raw_records`, or a path-like storage field. Add assertions that every metric has `status`, `quality_flags`, and an explicit `value` key, even when its value is `null`.

- [ ] **Step 5: Run all Backend tests and build**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test
npm --workspace @newtaipei-youth/backend run build
```

Expected: all Backend tests pass and TypeScript emits the Lambda build.

## Task 6: Add DynamoDB Adapter Behind the Existing Port

**Files:**

- Modify: `backend/package.json`
- Create: `backend/src/adapters/dynamoMetricsStore.ts`
- Create: `backend/tests/dynamoMetricsStore.test.ts`
- Modify: `backend/src/config.ts`

**Interfaces:**

- `DynamoMetricsStore` implements the exact `PublishedDataStore` interface from Task 2.
- Storage configuration reads `DYNAMODB_TABLE_NAME`, `DYNAMODB_REGION`, and `PUBLISHED_SNAPSHOT_ID` without changing application services or routes.

<<<<<<< ours
Use these queryable keys for the first table contract:

```text
dashboard overview: PK=SNAPSHOT#{snapshot_id}#RESOURCE#dashboard_overview
                   SK=DISTRICT#{district_id}
district detail:   PK=SNAPSHOT#{snapshot_id}#RESOURCE#district_details
                   SK=DISTRICT#{district_id}
analysis rows:     PK=SNAPSHOT#{snapshot_id}#ANALYSIS#{analysis_id}
                   SK=ROW#{row_id}
catalog metadata:  PK=SNAPSHOT#{snapshot_id}#RESOURCE#catalog
                   SK=METADATA
```

Overview uses a keyed Query for one snapshot resource and never uses a table Scan. A district detail uses a keyed GetItem or Query. The loader that writes these items belongs to the data-pipeline/infrastructure integration task and must preserve the same snapshot id.

=======
>>>>>>> theirs
- [ ] **Step 1: Write failing DynamoDB mapping tests**

```ts
import { describe, expect, it } from "vitest";
import { DynamoMetricsStore } from "../src/adapters/dynamoMetricsStore";

describe("DynamoMetricsStore", () => {
  it("queries a district by canonical district id and period", async () => {
    const send = async () => ({
      Items: [{
<<<<<<< ours
        PK: "SNAPSHOT#fixture-snapshot#RESOURCE#district_details",
        SK: "DISTRICT#65000010",
=======
        PK: "SNAPSHOT#fixture-snapshot",
        SK: "DISTRICT#65000010#DOMAIN#overview",
>>>>>>> theirs
        district_id: "65000010",
        metrics: [],
      }],
    });
    const store = new DynamoMetricsStore({
      tableName: "metrics",
      client: { send } as never,
      snapshotId: "fixture-snapshot",
    });

    const result = await store.getDistrictDetail("65000010", {});

    expect(result?.district.district_id).toBe("65000010");
  });
});
```

- [ ] **Step 2: Run the adapter test and verify it fails**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test -- dynamoMetricsStore.test.ts
```

Expected: FAIL because the DynamoDB adapter and AWS SDK dependency do not exist.

- [ ] **Step 3: Add the AWS SDK and implement query mapping**

Use AWS SDK v3 DocumentClient commands. The adapter must query by the published snapshot id and canonical district/domain keys; it must not perform a table scan for a dashboard request. Map DynamoDB items through the same Zod response schemas used by Local JSON. A missing item returns `null`; malformed items throw `SnapshotUnavailableError`.

- [ ] **Step 4: Run adapter, contract, and full tests**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test
npm --workspace @newtaipei-youth/backend run build
```

Expected: Local JSON and DynamoDB adapter tests pass against fake clients, with no AWS network call.

## Task 7: Integration Handoff and Verification Gate

**Files:**

- Modify: `backend/backend.md`
- Create: `backend/.env.example`
- Create: `backend/tests/README.md`

**Interfaces:**

- Documentation exposes exact local commands, environment names, route list, and data boundary.
- The verification checklist distinguishes Backend contract readiness from unimplemented pipeline analytics, CDK deployment, and Frontend API migration.

- [ ] **Step 1: Document local Backend execution**

Document these commands in `backend/backend.md`:

```bash
npm --workspace @newtaipei-youth/backend run build
npm --workspace @newtaipei-youth/backend run test
```

Document `BACKEND_DATA_ROOT`, `BACKEND_ALLOWED_ORIGINS`, `BACKEND_CACHE_MAX_AGE_SECONDS`, `DYNAMODB_TABLE_NAME`, `DYNAMODB_REGION`, and `PUBLISHED_SNAPSHOT_ID` with their local/test meaning.

<<<<<<< ours
Create `backend/.env.example` with these local/test defaults:

```dotenv
BACKEND_DATA_ROOT=tests/fixtures/published
BACKEND_ALLOWED_ORIGINS=http://localhost:5173
BACKEND_CACHE_MAX_AGE_SECONDS=60
DYNAMODB_TABLE_NAME=
DYNAMODB_REGION=
PUBLISHED_SNAPSHOT_ID=fixture-snapshot
```

=======
>>>>>>> theirs
- [ ] **Step 2: Document the integration order**

State that the next cross-module work is: pipeline `analytics` publishes the manifest/artifacts; Frontend replaces `fetchDistrictSummaries()` with the API client; Infrastructure creates API Gateway/Lambda/S3/DynamoDB; AI remains in `ai-service`.

- [ ] **Step 3: Run the final Backend verification commands**

Run:

```bash
npm --workspace @newtaipei-youth/backend run test
npm --workspace @newtaipei-youth/backend run build
git diff --check
git status --short
```

Expected: Backend tests pass, TypeScript build exits `0`, `git diff --check` reports no whitespace errors, and the working tree lists only the intended uncommitted Backend/shared/documentation changes.
<<<<<<< ours
=======

>>>>>>> theirs
