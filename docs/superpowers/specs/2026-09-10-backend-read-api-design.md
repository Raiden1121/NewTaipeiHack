# Backend Read API Design

<<<<<<< ours
**Date:** 2026-09-10
=======
**Date:** 2026-09-10  
>>>>>>> theirs
**Status:** Design approved for planning; implementation not started

## Goal

建立一個由 Node.js 執行、以 TypeScript 撰寫的唯讀 REST API，讓 Frontend 透過穩定的 API contract 讀取已發布的 Dashboard analytics snapshot。

Backend 只負責 request validation、資料查詢、response composition、錯誤處理與服務邊界；資料抓取、清理與核心指標計算仍由 `data-pipeline` 負責。

## Current Repository Evidence

- `backend/` 目前只有 `backend.md`、`package.json` 與空的 `src/`、`tests/`。
- `frontend/` 已使用 React、Vite、TypeScript、TanStack Query，首頁資料層仍由 `frontend/src/data/districts.ts` 讀取 `districts.csv`。
- Frontend 的 employment、fertility、politics、policy-support 頁面仍有 placeholder 指標或固定展示值。
- `data-pipeline/` 已產生 raw、curated、quality、quarantine 與 refresh state，但尚未建立 `src/analytics/`。
- Pipeline curated record 具有 `district_id`、`period_start`、`metric_id`、`value`、`unit`、`geo_level`、`youth_eligibility` 與 `quality_flags`。
- `data/quality/dataset_index.json` 是單次 pipeline run 的成功輸出索引，不是全站永久 published snapshot。

## Scope

### Included

- `backend` TypeScript package 與 Node.js Lambda handler。
- API Gateway HTTP API v2 event 的 request adapter。
- `/api/v1/health`、`/api/v1/catalog`、`/api/v1/dashboard/overview`、`/api/v1/districts/{districtId}` 與 `/api/v1/analyses/{analysisId}`。
- Local JSON published-data adapter，供本地開發與測試使用。
- 可替換的 DynamoDB adapter 介面；實際 AWS resource 由 `infrastructure/` 另行定義。
- `shared/` 的 API types 與資料 contract。
- response envelope、missing-value、proxy、quality、snapshot 與 error contract。

### Excluded

- Backend 直接呼叫政府 Open Data API。
- Backend 執行 collector、ETL、完整歷史資料聚合或核心指標計算。
- Backend 讀取或回傳 `raw_record`、PDF artifact 或任意本地路徑。
- AI prompt、Bedrock、RAG 與政策回答生成；這些屬於 `ai-service/`。
- 同步觸發資料更新；若未來需要管理操作，應異步啟動 pipeline workflow 並回傳 `run_id`。
- 登入系統；第一版是公開、唯讀 Dashboard API。

## Architecture

```text
External Sources
       ↓
data-pipeline: collector → transform → analytics
       ↓
published snapshot + manifest
       ↓
Local JSON adapter / S3 + DynamoDB adapter
       ↓
Node.js Lambda + API Gateway HTTP API
       ↓
React Frontend
```

Backend 與 data-pipeline 不直接 import 或呼叫彼此。兩者只透過 published snapshot、manifest 與 shared contract 溝通。

第一版採單一 Lambda entrypoint 加上純函式 application/router；`handler.ts` 只處理 Lambda event adapter，實際查詢流程放在 application service。未來流量或權限邊界需要拆分時，再依 domain 拆 Lambda。

## Published Snapshot Contract

Backend 不直接掃描 `data-pipeline/data/curated/`。Pipeline analytics 應產出一個可原子切換的 published snapshot：

```text
data/analytics/published/{snapshot_id}/manifest.json
data/analytics/published/{snapshot_id}/dashboard_overview.json
data/analytics/published/{snapshot_id}/district_details.json
data/analytics/published/{snapshot_id}/analyses/{analysis_id}.json
data/analytics/published/current.json
```

`current.json` 只包含目前 snapshot id；Backend 讀取後，只使用該 snapshot 的 manifest 所列 artifact。

Manifest 至少包含：

```json
{
  "schema_version": 1,
  "snapshot_id": "2026-09-10T00:00:00Z",
  "generated_at": "2026-09-10T00:00:00Z",
  "as_of": "2026-07-31",
  "artifacts": {
    "dashboard_overview": "dashboard_overview.json",
    "district_details": "district_details.json",
    "analyses": {
      "housing-affordability": "analyses/housing-affordability.json"
    }
  },
  "datasets": [],
  "warnings": []
}
```

每個 dataset entry 應保留 `dataset`、`path`、`period_strategy`、`source_period`、`transform_version`、`geo_level`、`coverage` 與 `quality_flags`。Backend 使用 manifest 來呈現 freshness、coverage 與來源說明，而不是自行猜測資料期間。

## API Contract

### Common response

成功回應統一為：

```json
{
  "data": {},
  "meta": {
    "api_version": "v1",
    "snapshot_id": "2026-09-10T00:00:00Z",
    "generated_at": "2026-09-10T00:00:00Z",
    "as_of": "2026-07-31",
    "warnings": []
  }
}
```

Metric 應包含：

```json
{
  "metric_id": "youth_18_35_total",
  "value": 106473,
  "unit": "people",
  "period_start": "2026-07-01",
  "period_end": "2026-07-31",
  "period_type": "month",
  "geo_level": "district",
  "youth_eligibility": "eligible",
  "source": "moi_household_registration",
  "quality_flags": [],
  "status": "available",
  "is_proxy": false
}
```

未知或不適用數值使用 JSON `null`，不使用 `0`。`status` 使用 `available`、`partial` 或 `unavailable`。資料不存在不等同於 HTTP 404；只要 resource 存在但來源沒有資料，就回傳 `200` 並標記 `unavailable`。

### Endpoints

| Endpoint | 用途 |
|---|---|
| `GET /api/v1/health` | liveness/readiness；檢查 manifest 是否可讀 |
| `GET /api/v1/catalog` | snapshot、資料集、期間、粒度、品質與更新時間 |
| `GET /api/v1/dashboard/overview` | 首頁 KPI 與 29 區摘要，一次回傳同一 snapshot |
| `GET /api/v1/districts/{districtId}` | 單一行政區的工作、居住、生育、交通與資源資料 |
| `GET /api/v1/analyses/{analysisId}` | 預先計算的 housing、demand、education 等分析 |

查詢參數只接受 allowlist：

- `period=latest`、`period=YYYY` 或 `period=YYYY-MM`。
- `timeframe=recent_3y` 或 `timeframe=historical_10y`。
- `period` 與 `timeframe` 不可同時使用。
- `districtId` 必須是新北市 29 區中的正式 `district_id`。
- `analysisId` 必須存在於 manifest，不允許由 request 建立任意檔案路徑。

<<<<<<< ours
API 對外只使用 ISO period；ROC period 只存在於 pipeline source metadata，不要求 Frontend 處理 ROC 轉換。`timeframe` 只選擇 analytics 已經產出的結果，不在 Backend request 期間計算三年平均或十年綜合分數。
=======
`timeframe` 只選擇 analytics 已經產出的結果，不在 Backend request 期間計算三年平均或十年綜合分數。
>>>>>>> theirs

### Analysis response

```json
{
  "analysis_id": "housing-affordability",
  "x_metric": "housing_price_per_ping_median",
  "y_metric": "wage_new_taipei_age_proxy",
  "geo_level": "district",
  "period": { "start": "2024-01-01", "end": "2024-12-31" },
  "data": [],
  "statistics": {
    "correlation": null,
    "sample_size": 27,
    "method": "spearman"
  },
  "limitations": ["薪資為新北市 county-level proxy"]
}
```

正式分析的 `period`、`geo_level`、`sample_size`、`method` 與 limitation 必須由 data-pipeline 提供；Frontend 只繪圖，Backend 只查詢與格式化。

## Data Availability Rules

第一版只能呈現實際有來源支撐的資料：

- `population` 的 18–35 歲人口可作 district-level eligible metric。
- `births` 的生母 18–35 歲出生數可作 district-level eligible metric。
- 房價、租金、職缺、交通、托育屬 context data，必須保留 snapshot 與品質資訊。
- 工資、教育、畢業生多為 county、national 或 official age-group proxy，不可拆成 29 區。
- `youth_budgets` 是 organization-level context，不可分配到 29 區。
- 政治參與、政策執行率、政策達成率與全國青年人口目前沒有完整 pipeline source，API 回傳 `unavailable`，不得複製 Frontend placeholder 數值。

## Error Contract

```json
{
  "error": {
    "code": "INVALID_QUERY",
    "message": "timeframe is not supported",
    "details": []
  },
  "request_id": "..."
}
```

規則：

- `400 INVALID_QUERY`：參數格式或 allowlist 不合法。
- `404 DISTRICT_NOT_FOUND`／`ANALYSIS_NOT_FOUND`：resource id 不存在。
- `503 SNAPSHOT_UNAVAILABLE`：current manifest 遺失、格式錯誤或 artifact 不可讀。
- `500 INTERNAL_ERROR`：未預期錯誤；response 不暴露本地路徑、stack trace 或原始資料。

所有 response 都加入 request id；CORS allowed origins、cache max-age 與資料根目錄由 environment config 提供，不寫死在 handler。

## File Boundaries

```text
backend/src/handler.ts                    # Lambda event adapter
backend/src/app.ts                        # 可測試的 application entry
backend/src/http/router.ts                 # method/path dispatch
<<<<<<< ours
backend/src/http/types.ts                  # normalized request/response types
=======
>>>>>>> theirs
backend/src/http/response.ts               # success/error envelope
backend/src/http/errors.ts                 # domain error → HTTP mapping
backend/src/application/                  # use cases
backend/src/ports/publishedDataStore.ts    # storage interface
backend/src/adapters/localPublishedDataStore.ts
backend/src/adapters/dynamoMetricsStore.ts
backend/src/schemas/requests.ts            # runtime request validation
backend/src/schemas/responses.ts           # runtime response validation
shared/src/api.ts                           # shared API types
shared/src/metrics.ts                       # shared metric types
```

`data-pipeline/src/analytics/` 負責產出 published artifact；`infrastructure/` 負責 API Gateway、Lambda、S3、DynamoDB 與 IAM，不放進 Backend application。

## Testing and Acceptance

- Unit tests 覆蓋 request validation、period selection、district lookup、error mapping 與 response serialization。
- Integration tests 使用 local published fixture，不呼叫政府 API、不需要 AWS credentials。
- Contract tests 驗證 29 個 district id 唯一、同一回應只使用一個 snapshot、缺值保持 `null`、response 不包含 `raw_record`。
- DynamoDB adapter 以 fake DocumentClient 驗證 query key 與 mapping，不在單元測試連線真實 AWS。
- `GET /dashboard/overview` 成功時回傳 29 區；未知 district 回 `404`；非法 timeframe 回 `400`；無 published snapshot 回 `503`。

## Delivery Order

1. Shared contract、published fixture 與 Backend package baseline。
2. Local JSON adapter、Lambda handler、health/catalog API。
3. Dashboard overview 與 district detail API。
4. Analysis API 與完整 proxy/quality/error metadata。
5. DynamoDB adapter 與 production configuration。
6. Infrastructure/CDK 與 Frontend API migration 另以整合任務驗證。
<<<<<<< ours
=======

>>>>>>> theirs
