# Data Pipeline

## Purpose

Data Pipeline 是系統統計數字的主要計算來源，預計把政府 Open Data、新北市資料與青年局資源整理成可供 Backend 與 AI 使用的資料。

目前只有 Python pipeline 的 Dockerfile、requirements placeholder 與目錄 scaffold，尚未建立實際 ETL 或指標程式。

## Responsibilities

規劃使用 Python、AWS Lambda、S3、DynamoDB、Step Functions 與 EventBridge：

```text
Collect
  ↓
Raw Data
  ↓
Transform
  ↓
Normalize to 29 Districts
  ↓
Analytics
  ↓
Load
```

資料來源可能包含內政部戶政司、台灣就業通、勞動部、新北 Open Data、TDX 與新北市青年局。

## Project Usage

預計處理行政區名稱、日期、年齡、地址、座標與 Spatial Join，統一到新北市 29 區及明確資料期間。

Analytics 可能計算青年人口、YoY、Cohort Retention Signal、職缺／薪資、居住、交通、Resource Access、Resource Gap、Opportunity Index、Demand Index、Mismatch Index 與 Retention Risk inputs。

## Inputs & Outputs

- 輸入：政府公開資料、青年局資料與相關地理資料。
- 輸出：S3 Raw／Curated Data、DynamoDB 指標與 AI Evidence。

## Boundaries

Data Pipeline 負責抓資料、清理、標準化與計算數字。Frontend 與 LLM 不應取代這一層；職缺與畢業生資料也不能直接相減解釋成精確缺工人數。
