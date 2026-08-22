# Frontend

## Purpose

Frontend 是新北青年 Dashboard 的使用者介面，服務新北市 29 個行政區與 18–35 歲青年資料的視覺化閱讀。

目前實際內容是 React + Vite 的新北市行政區地圖原型，程式使用 JSX，尚未導入 TypeScript。

## Responsibilities

目前負責：

- 載入 `public/Map_NewTaipei.json` TopoJSON。
- 解析 `objects.map` 並顯示 29 個行政區。
- 提供行政區 Hover、Click、Loading、Error 與 Empty 狀態。

後續預計加入：

- KPI、Youth Opportunity Index 與 Youth Resource Gap。
- 青年人口、Cohort、人才／工作、居住與交通趨勢。
- 青年局資源、公共參與與 AI Policy Copilot UI。

## Project Usage

```text
cd frontend
npm run dev
npm run build
```

## Inputs & Outputs

- 目前輸入：前端公開目錄中的新北市地圖資料。
- 未來輸入：Backend API 與 AI Service API 的整理後結果。
- 目前輸出：可互動的 29 區地圖畫面。

## Boundaries

Frontend 負責 presentation，不是資料計算來源。它不應自行抓取政府 Open Data、計算 Opportunity Index 或 Retention Risk，也不應把 ETL、資料庫或複雜 business logic 寫在 UI 中。
