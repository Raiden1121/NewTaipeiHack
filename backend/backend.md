# Backend

## Purpose

Backend 是 Dashboard 的一般 REST API 層，提供前端查詢新北市 29 個行政區分析資料的統一入口。

目前資料讀取 API 已由 `infrastructure/modules/api/lambda/handler.py` 實作，
並由 Terraform 部署成 Python API Lambda + API Gateway HTTP API。本文件的 Backend
邊界包含該既有 Lambda，不另新增 TypeScript Backend Lambda。

## Responsibilities

使用 Python Lambda、API Gateway 與 DynamoDB，提供：

- 行政區基本資料與青年人口。
- Opportunity Index、Retention Risk、Resource Access、Resource Gap。
- Jobs、Housing、Transport、Talent、Youth Resources 與趨勢資料。
- Request validation、query、response formatting 與 error handling。
- `POST /api/v1/ai/query`：驗證公開 AI query contract，拒絕 `context`、`evidence`、
  `webFindings`，同步 invoke 私有 AI Service Lambda。

主要資料預計從 DynamoDB 讀取，不在 request 期間重新執行完整分析。

## Project Usage

API Gateway 將請求導向既有 Python Lambda；AI query 的同步呼叫不新增非同步 job 系統。

## Inputs & Outputs

```text
Frontend
   ↓
API Gateway
   ↓
Backend Lambda
   ↓
DynamoDB
```

輸入為前端查詢參數；輸出為穩定且可供 Frontend 與 shared types 使用的 API response。

Metric 的來源欄位由 pipeline 的 published snapshot／DynamoDB projection 提供：`source` 是穩定來源 ID，`sourceName` 是中文顯示名稱，`sourceUrl` 是可點擊查證的官方網址，`sourceRefs` 用於多來源衍生指標。Backend 只轉送與驗證這些欄位，不讀取 `sources.json`、Raw 或外部政府 API，也不在 request 時補來源。

## Boundaries

Backend 不負責 ETL、政府資料抓取、核心指標計算或 AI Prompt。若未來需要 authentication，應在 API 邊界處理，不改變資料管線與 AI Service 的責任。

AI query 的公開 request 只包含 `action`、`question`、`focusDistrict`、`focusArea`、
`period` 與 `webSearch`；`qa` 的 `question` 最多 400 字且必填。未指定期間時由
AI Service 依各 dataset 最新可用期選 evidence；web search 預設為全網 `all`、低上下文
`low`，`trusted` 僅限 `gov.tw` 與 `edu.tw`。API Lambda timeout 為 28 秒，Lambda SDK
read timeout 約 25 秒，會將 AI validation/runtime/configuration/timeout 映射為
400/502/503/504。
