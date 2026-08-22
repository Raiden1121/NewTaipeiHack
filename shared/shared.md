# Shared

## Purpose

Shared 用來保存 Frontend、Backend 與 AI Service 共用的 TypeScript data types 與 contract，避免各模組使用不同欄位名稱或資料格式。

目前只有 package 設定與 `src/` placeholder，尚未建立實際 type definitions。

## Responsibilities

未來可能包含：

- `District` 與 `DistrictMetrics`。
- `OpportunityIndex` 與 `RetentionRisk`。
- `YouthResource`、API Request / Response。
- `PolicyAdvice` 與 `AI Evidence`。

共用格式應讓各模組對同一個欄位有一致理解，例如不要讓 Frontend 使用 `opportunityIndex`，Backend 卻回傳 `opportunity_score`。

## Project Usage

```text
frontend
backend
ai-service
    ↓
共用 Type Definition / Contract
```

## Inputs & Outputs

- 輸入：跨模組需要共享的資料結構與 API contract。
- 輸出：可被各 workspace package 引用的 TypeScript types。

## Boundaries

Shared 不是 AWS Service，不會獨立部署；不負責 business logic、資料庫、ETL、AI Prompt 或 API request 的執行。
