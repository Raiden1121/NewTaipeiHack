# Backend

## Purpose

Backend 是 Dashboard 的一般 REST API 層，預計提供前端查詢新北市 29 個行政區分析資料的統一入口。

目前 repository 只有 package 設定與 `src/`、`tests/` placeholder，尚未建立 API 或 Lambda 實作。

## Responsibilities

規劃使用 TypeScript、Node.js、AWS Lambda 與 API Gateway，提供：

- 行政區基本資料與青年人口。
- Opportunity Index、Retention Risk、Resource Access、Resource Gap。
- Jobs、Housing、Transport、Talent、Youth Resources 與趨勢資料。
- Request validation、query、response formatting 與 error handling。

主要資料預計從 DynamoDB 讀取，不在 request 期間重新執行完整分析。

## Project Usage

目前尚無可執行的 Backend service 或 API script。實作後，預計由 API Gateway 將請求導向 Lambda。

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

## Boundaries

Backend 不負責 ETL、政府資料抓取、核心指標計算或 AI Prompt。若未來需要 authentication，應在 API 邊界處理，不改變資料管線與 AI Service 的責任。
