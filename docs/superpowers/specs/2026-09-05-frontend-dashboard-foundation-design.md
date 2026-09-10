# 新北青年機會地圖 Frontend：基礎架構與首頁戰情室設計規格

## 1. 目標

依據 `frontend/prd.md`，新北青年 Dashboard 前端規劃五大板塊（① 主頁戰情室、
② 青年就業、③ 青年參政、④ 青年生育、⑤ 施政協助），每一板塊內容都相當
龐大。本規格**只涵蓋第一個子專案**：

- 把現有的 React + Vite 地圖原型（純 JSX，只有 `d3-geo` /
  `topojson-client`）升級為完整的應用基礎架構：TypeScript、路由、設計
  系統、資料層、狀態管理、測試工具。
- 完整實作 PRD §① 主頁戰情室（29 區地圖、核心 KPI、四大板塊入口卡）。
- 其餘四個板塊（②～⑤）先建立路由 stub（顯示「規劃中」），不在本規格
  範圍內；待本子專案完成後，各自作為獨立子專案重複「brainstorming →
  spec → plan」流程。

`backend/`、`ai-service/`、`shared/` 目前都只是空 scaffold，沒有可用的
真實 API 或型別匯出，因此本階段資料一律以本地 fixture 模擬，並封裝在
可替換的資料層之後。

## 2. 核准方案：技術選型

| 類別 | 選擇 | 理由 |
| --- | --- | --- |
| 語言 | TypeScript | `shared/` 定位為跨模組共用 TS 型別，frontend 及早轉 TS 才能直接消費，也讓 29 區 × 多指標的複雜資料結構在編譯期被檢查 |
| 樣式 | Tailwind CSS + shadcn/ui | 兩者official 整合度最高；shadcn 元件（Card、Tabs、Badge、Skeleton 等）符合 PRD 大量卡片式版面需求 |
| 圖示 | lucide-react | shadcn/ui 預設圖示庫 |
| 一般圖表 | Recharts | shadcn/ui 官方 `chart` 元件即為 Recharts 封裝，雷達圖／雙軸折線／散佈圖／長條圖都有現成 API，與既有設計系統風格一致 |
| 地圖 | 沿用 d3-geo + topojson-client | 既有 29 區 choropleth 投影邏輯已可運作，不用 Recharts/其他圖表庫重做地理投影 |
| 路由 | react-router-dom | 五大板塊需要獨立路由與導覽列 |
| 伺服器狀態 | TanStack Query | 統一處理 loading/error/cache，之後把 fixture 換成真實 API 只需改 query function |
| 跨元件 UI 狀態 | Zustand | 管理「目前選取行政區」「篩選條件」等跨元件共享狀態，避免 prop drilling 或 Context re-render 範圍過大 |
| CSV 解析 | PapaParse | 本地 fixture 採 CSV 格式（貼近未來政府開放資料的實際格式），由 data-service 層解析成型別化物件 |
| 動效 | Framer Motion (`motion`) | KPI 數字進場、卡片 hover、頁面切換轉場 |
| 表單 | react-hook-form + zod（暫緩） | 本階段（基礎架構 + 首頁）沒有表單輸入情境，YAGNI 不先導入；待建置施政協助頁的 AI 領域選擇器/篩選表單時再評估導入 |
| 測試 | Vitest + @testing-library/react + jsdom | 與 Vite 原生整合，符合專案 TDD 慣例 |
| 錯誤邊界 | react-error-boundary | 讓單一小元件出錯不會讓整個 Dashboard 白屏 |
| Lint/Format | ESLint (typescript-eslint) + Prettier | 目前無任何 lint 設定，及早建立避免多頁面後風格分歧 |

## 3. 專案結構

```text
frontend/
├── src/
│   ├── app/
│   │   ├── main.tsx
│   │   ├── App.tsx            # Router + QueryClientProvider + ErrorBoundary 組裝
│   │   ├── routes.tsx         # 五大板塊路由定義（②～⑤ 為 placeholder）
│   │   └── AppLayout.tsx      # 固定導覽列 + 版面外框
│   ├── features/
│   │   └── home/
│   │       ├── HomePage.tsx
│   │       ├── components/
│   │       │   ├── DistrictChoroplethMap.tsx   # 由 TownMap.tsx 遷移而來
│   │       │   ├── KpiSummaryRow.tsx
│   │       │   └── SectionEntryCards.tsx
│   │       └── hooks/
│   │           └── useDistrictSummary.ts       # TanStack Query hook
│   ├── components/
│   │   ├── ui/                 # shadcn/ui 產生的元件（Card, Badge, Skeleton…）
│   │   └── shared/              # 跨 feature 共用元件（NavBar, PlaceholderPage）
│   ├── data/
│   │   └── districts.ts         # data-service：解析 fixture、之後改為 fetch()
│   ├── stores/
│   │   └── useSelectedDistrict.ts  # Zustand store
│   ├── fixtures/
│   │   └── districts.csv        # 29 區模擬資料（PapaParse 解析）
│   ├── types/
│   │   └── district.ts          # 本地型別，待 shared/ 有實作後改為匯入
│   └── lib/
│       └── utils.ts             # cn() 等工具
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

`DESIGN_LANGUAGE.md`（目前為空檔）將在本子專案中補上色彩／字級／間距
token 定義，並對應到 Tailwind theme 設定，供全站共用。

## 4. 資料契約與資料流

```text
src/fixtures/districts.csv
    → PapaParse（於 src/data/districts.ts）
    → 型別化物件陣列（DistrictSummary[]，定義於 src/types/district.ts）
    → TanStack Query hook（useDistrictSummary）
    → 元件（DistrictChoroplethMap / KpiSummaryRow / SectionEntryCards）
```

- `src/data/districts.ts` 對外只輸出 async function（例如
  `fetchDistrictSummaries(): Promise<DistrictSummary[]>`）。內部現在用
  PapaParse 讀 fixture；未來換成真實 API 時，只需把內部實作換成
  `fetch()`，回傳型別與呼叫端介面不變。
- `DistrictSummary` 型別欄位比照 PRD §① 需要的欄位：`id`、`name`、
  `youthPopulation`、`opportunityIndex`、`retentionRiskLevel` 等，命名
  預先對齊 `shared/shared.md` 提到的欄位原則（例如用
  `opportunityIndex` 而非 `opportunity_score`），降低未來對接 `shared/`
  真實型別時的改名成本。
- 選取狀態（`selectedDistrictId`）存在 Zustand store，由地圖與 KPI 卡片
  共同讀寫；不放進 TanStack Query cache（那是純 UI 狀態，非伺服器資料）。

## 5. 路由與頁面殼

```text
/                 → HomePage（本規格實作範圍）
/employment       → PlaceholderPage「青年就業 · 規劃中」
/politics         → PlaceholderPage「青年參政 · 規劃中」
/fertility        → PlaceholderPage「青年生育 · 規劃中」
/policy-support   → PlaceholderPage「施政協助 · 規劃中」
```

`AppLayout` 提供固定頂部導覽列（5 個板塊連結，依 PRD §五 配色：主色
`#005599`、背景 `#f8f9ff`），確保即使只有首頁完整實作，整體導覽與版面
骨架也是可展示、可驗收的。

## 6. 元件責任（首頁戰情室）

### `HomePage.tsx`
- 組合 `DistrictChoroplethMap`、`KpiSummaryRow`、`SectionEntryCards`。
- 透過 `useDistrictSummary` 取得資料，處理整頁 loading/error/empty 狀態
  （沿用現有 `App.jsx` 的狀態切分邏輯，遷移為 TS 版本）。

### `DistrictChoroplethMap.tsx`
- 由現有 `TownMap.jsx` 遷移，幾何投影與 hover/click 邏輯保留，樣式改為
  Tailwind class。
- 依 `opportunityIndex` 做分層設色（choropleth scale），而非目前單一色。
- 選取事件寫入 `useSelectedDistrict` store，而非本地 `useState`。

### `KpiSummaryRow.tsx`
- 4 張 shadcn `Card`：全台 18–35 歲青年人口總數與佔比、新北市青年佔總
  人口比例（28.4%）、青年人口 YoY、平均留才風險等級。
- 使用 Framer Motion 做數字進場動畫。

### `SectionEntryCards.tsx`
- 4 張入口卡（就業／參政／生育／施政協助），各自顯示一項代表性指標
  （來自 fixture），點擊導向對應 placeholder 路由。

## 7. 設計系統

- 於 `DESIGN_LANGUAGE.md` 定義色彩 token（主色 `#005599`、背景
  `#f8f9ff`、容器 `#ffffff`、輔助青綠／警示橙／灰藍階層），並在
  `tailwind.config.ts` 的 `theme.extend.colors` 對應設定，避免各頁面各
  自寫死色碼。
- 透過 shadcn CLI 初始化 `components/ui/`，之後各板塊共用同一套元件與
  token，不重造樣式。

## 8. UI 狀態與互動

延續現有 `App.jsx` 已經驗證過的狀態機（loading / error / empty /
success），但整頁層級改用 `react-error-boundary` 包裹主要區塊：地圖與
KPI 區各自有獨立 error boundary，任一區塊資料失敗只影響該區塊，不會讓
整個首頁白屏。

- 初次載入：shadcn `Skeleton` 取代目前純文字 loading 提示。
- 載入失敗：保留「重新載入」按鈕語意，樣式改用 shadcn。
- 地圖 hover/click：行為與現有 `TownMap.jsx` 一致（tooltip、hover 樣式、
  selected 樣式），只是資料來源改為 store。

## 9. 測試策略

- `src/data/districts.ts`：單元測試驗證 CSV → 型別化物件的解析正確性
  （欄位缺漏、型別轉換錯誤時的行為）。
- `src/stores/useSelectedDistrict.ts`：單元測試驗證選取/清除邏輯。
- `DistrictChoroplethMap`：元件測試涵蓋 hover/click 後的 class 與
  callback（沿用現有原型已隱含驗證過的互動，遷移時補上測試鎖住行為）。
- `KpiSummaryRow`：元件測試驗證 loading/error/success 三態渲染正確的
  內容。
- 不建立 E2E（Playwright 等）測試，本階段以元件與單元測試為主。

## 10. Migration 說明

- `frontend/src/App.jsx` → 拆分為 `app/App.tsx`（路由/provider 組裝）與
  `features/home/HomePage.tsx`（原本的頁面內容），邏輯不重寫、只搬移並
  補型別。
- `frontend/src/components/TownMap.jsx` → 遷移為
  `features/home/components/DistrictChoroplethMap.tsx`，投影/互動邏輯
  保留，樣式改 Tailwind。
- `frontend/src/styles.css` → 拆解為 Tailwind utility class + shadcn
  primitives；`:root` 色彩對應到 `DESIGN_LANGUAGE.md` 定義的 token。
- `frontend/public/Map_NewTaipei.json` 保留不動，仍是地圖資料來源。

## 11. 範圍外事項

- 板塊 ②～⑤（青年就業、參政、生育、施政協助）的完整功能，僅先建立
  placeholder 路由，實作留待各自獨立子專案。
- 與真實 `backend`／`ai-service` API 串接（目前皆為空 scaffold）。
- AI Policy Copilot 對話介面與領域約束邏輯。
- `react-hook-form` + `zod` 表單導入（無表單情境，見第 2 節）。
- 登入／權限、AWS 部署設定、E2E 測試。

## 12. 驗收條件

1. `npm run dev` 能啟動 TypeScript 版本的開發伺服器，無型別錯誤。
2. 導覽列可切換 5 個路由，②～⑤ 顯示「規劃中」placeholder，不出現路由
   錯誤。
3. 首頁能載入 fixture 資料並顯示 29 區 choropleth 地圖、4 張 KPI 卡、4
   張板塊入口卡。
4. 地圖 hover／click 行為與現有原型一致（名稱提示、hover 樣式、selected
   樣式），且選取狀態由 Zustand store 驅動。
5. 手動將 `src/data/districts.ts` 內部實作暫時改成會 reject 的假
   `fetch`，確認地圖與 KPI 區各自顯示錯誤狀態、互不影響（驗證 error
   boundary 隔離）。
6. `npm run build` 成功產生正式建置檔案。
7. `npm run test`（Vitest）通過第 9 節列出的單元／元件測試。
8. 使用瀏覽器實際檢查桌面寬度下的排版、hover/click 互動與 loading/
   error/empty 狀態。
