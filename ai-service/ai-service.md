# AI Service

## Purpose

AI Service 專門處理 Amazon Bedrock 與 AI 回覆，將已整理的統計資料、證據與政策文件轉換成可理解的分析內容。

目前 repository 只有 package 設定與 `src/`、`tests/` placeholder，尚未建立 Bedrock、RAG 或 Lambda 流程。

## Responsibilities

規劃使用 TypeScript、Node.js、AWS Lambda、Amazon Bedrock 與 RAG，提供：

- **Dashboard Data Explanation**：解釋人口、機會、留才、人才、資源、居住與交通資料。
- **AI Policy Copilot**：整理問題辨識、發展優勢、資源缺口、政策方向、判斷依據與資料限制。
- **AI Data Q&A**：回答使用者對 29 區資料的比較與查詢。

## Project Usage

AI Context 預計來自 DynamoDB 已計算指標、Evidence 與青年局／政策文件 RAG，再交由 Amazon Bedrock 產生回覆。

## Inputs & Outputs

- 輸入：結構化指標、資料來源、期間、證據與政策文件。
- 輸出：結構化 explanation、policy advice、Q&A response 與資料限制。

## Boundaries

LLM 不負責計算 YoY、Opportunity Index、Resource Gap 或 Retention Risk。重要數字應來自 evidence/context，不可自行捏造；資料不足時必須標示限制。AI 建議只是政策輔助資訊，不代表官方政策決定。
