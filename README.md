# 留得青山在｜新北青年機會與留才風險地圖

**New Taipei Youth Opportunity & Retention Platform**

## Project Overview

本專案聚焦新北市 29 個行政區與 18–35 歲青年，整合跨部會、新北市政府及青年局公開資料，觀察各區的青年發展機會、人口變化、留才風險與資源配置情形。

目標不是只呈現統計數字，而是協助使用者理解青年需求與政府資源供給之間的關係，並以 AI 提供可追溯資料依據的政策分析輔助。

## Core Questions

1. 哪些行政區具有較好的青年發展機會？
2. 哪些行政區正在出現青年流失或留才風險訊號？
3. 青年需求和現有政府資源之間是否存在配置落差？
4. AI 如何協助使用者理解數據並取得政策決策參考？

## Key Features

- **29 District Youth Map**：以 29 區地圖作為主要入口，呈現行政區層級的青年資料。（目前已有地圖原型）
- **Youth Opportunity Index**：綜合工作、薪資、人才發展、居住負擔與交通可及性，比較青年發展環境。（規劃中）
- **Cohort Retention Signal**：觀察 18–24、25–29、30–35 歲人口趨勢與留才風險訊號。（規劃中）
- **Talent / Job Analysis**：分析職缺需求、職群、薪資、職業訓練與人才培育趨勢。（規劃中）
- **Youth Resource Gap**：比較青年需求與青年局／政府資源供給，辨識高需求低供給區域。（規劃中）
- **AI Policy Copilot**：根據已計算的指標與資料證據，整理問題、優勢、缺口與可能政策方向。（規劃中）
- **Data Explanation**：將圖表與統計結果轉換為一般使用者容易理解的文字說明。（規劃中）

職缺與畢業生資料的母體及時間尺度不同，不直接以「職缺數 - 畢業生數」定義人才缺口；相關分析應採用標準化指標與趨勢呈現。

## System Architecture

以下為目標架構，現階段各服務多為 repository scaffold：

```text
Open Data Sources
       ↓
Automated Data Pipeline
       ↓
S3 Raw / Curated Data
       ↓
Deterministic Analytics
       ↓
DynamoDB
       ↓
API Gateway + Lambda ─────→ React Dashboard
       ↓                              ↓
AI Context / Evidence       AI Policy Copilot
       ↓
Amazon Bedrock
```

資料更新流程預計由 EventBridge Scheduler 與 Step Functions 串接資料處理工作；部署與雲端資源則由 AWS CDK 管理。

## Project Structure

```text
newtaipei-youth/
├── frontend/           # React + Vite 地圖與 Dashboard 前端
│   ├── public/         # 前端公開資產，目前包含新北市地圖資料
│   ├── src/            # 目前地圖原型程式
│   └── package.json
├── backend/            # TypeScript + Node.js Lambda REST API 邊界
│   ├── src/
│   ├── tests/
│   └── package.json
├── ai-service/         # Amazon Bedrock／AI 回覆／RAG 邊界
│   ├── src/
│   ├── tests/
│   └── package.json
├── data-pipeline/      # Python ETL、資料分析與指標計算邊界
│   ├── src/
│   ├── config/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── shared/              # 前端、Backend、AI 共用 TypeScript Types
│   ├── src/
│   └── package.json
├── infrastructure/     # AWS CDK Infrastructure as Code 邊界
│   ├── bin/
│   ├── lib/
│   ├── package.json
│   └── cdk.json
├── scripts/             # 開發、部署與資料初始化工具位置
├── docs/                # 架構與技術文件
├── README.md
└── DESIGN_LANGUAGE.md
```

目前 `backend/`、`ai-service/`、`data-pipeline/`、`shared/` 與 `infrastructure/` 主要是目錄與設定 scaffold，尚未包含完整服務實作。

## Data Pipeline

資料管線的目標流程為：

```text
公開資料
  ↓
S3 Raw Data
  ↓
ETL / 清理 / 對齊行政區與期間
  ↓
Deterministic Analytics
  ↓
指標與來源證據
  ↓
DynamoDB / AI Context
```

人口、職缺、人才培育、居住、交通與青年資源資料應保留資料期間、來源與更新時間。青年人口 YoY、Youth Opportunity Index、Cohort Retention Signal、Youth Resource Gap 與 Retention Risk 等指標應由資料分析程式計算，而不是交由 LLM 推算。

目前 `data-pipeline/` 尚未建立實際 ETL 或指標計算程式。

## AI Architecture

AI Service 預計使用 Amazon Bedrock，透過已整理的 AI Context / Evidence 進行 Grounded Generation。LLM 的責任是解釋、摘要、語意理解與提出政策方向，不負責計算核心指標。

AI 回覆應盡可能符合以下原則：

- 使用 Structured Output，讓問題辨識、發展優勢、資源缺口、政策方向、判斷依據與資料限制可分開呈現。
- 提供 Evidence / Source reference，避免捏造數字或資料來源。
- 資料不足時明確標示限制。
- AI 建議屬於政策輔助資訊，不代表政府正式政策決定。

目前 `ai-service/` 尚未建立 Bedrock、RAG 或問答流程實作。

## Tech Stack

| Layer | Technology | Status |
| --- | --- | --- |
| Frontend | React, Vite, D3 Geo, TopoJSON | 目前已有地圖原型 |
| Backend | TypeScript, Node.js, AWS Lambda | Architecture / planned |
| AI | Amazon Bedrock, RAG / Knowledge Base | Architecture / planned |
| Data | Python, Pandas / GeoPandas | Architecture / planned |
| Storage | Amazon S3, DynamoDB | Architecture / planned |
| API | Amazon API Gateway | Architecture / planned |
| Workflow | EventBridge, Step Functions | Architecture / planned |
| Infrastructure | AWS CDK + TypeScript | Scaffold / planned |

## Development Status

本專案目前處於新北市 AI Hackathon 開發階段。repository 已建立 monorepo 目錄邊界與前端新北市地圖原型；後端 API、AI Service、資料管線、完整指標與 AWS 部署仍在規劃或後續開發中。
