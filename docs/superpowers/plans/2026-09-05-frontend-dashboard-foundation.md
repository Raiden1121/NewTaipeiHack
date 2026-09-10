# 首頁戰情室與前端基礎架構 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `frontend/` 從純 JSX 地圖原型升級為 TypeScript + 路由 + 設計系統 +
資料層 + 狀態管理 + 測試工具的完整基礎架構，並完整實作 PRD §① 主頁戰情室
（29 區地圖、核心 KPI、四大板塊入口卡）。

**Architecture:** 逐步、每步都可建置/可測試地把現有 `App.jsx` / `TownMap.jsx`
轉為 TypeScript，再抽出 router／layout／design system／data-service／store／
query-hook 等基礎設施，最後把首頁內容遷移為由三個獨立資料驅動元件
（`DistrictChoroplethMap`、`KpiSummaryRow`、`SectionEntryCards`）組成，各自
用 TanStack Query 讀取同一份 fixture-backed data-service，並各自被
`react-error-boundary` 包裹以達成區塊級容錯隔離。

**Tech Stack:** TypeScript, Vite, React 18, react-router-dom, TanStack Query,
Zustand, PapaParse, Tailwind CSS, 手刻 shadcn/ui 風格元件
（`class-variance-authority` + `clsx` + `tailwind-merge`）, `motion`
（Framer Motion 新套件), lucide-react, react-error-boundary, Vitest +
@testing-library/react + jsdom, ESLint (typescript-eslint) + Prettier.

**Spec:** `docs/superpowers/specs/2026-09-05-frontend-dashboard-foundation-design.md`

## Global Constraints

- 語言一律 TypeScript，`tsconfig.json` 開 `strict: true`；`npm run build`
  （內含 `tsc -b`）必須零型別錯誤。
- 樣式一律 Tailwind CSS class；顏色只能透過 `tailwind.config.ts` 的
  `theme.extend.colors` token（`primary` `#005599`、`background` `#f8f9ff`、
  `surface` `#ffffff`、`accent.teal/warning/slate`、`risk.low/medium/high`）
  取用，元件內不得寫死色碼（SVG 內聯 `style` 例外，因 choropleth 顏色為
  執行期依資料計算）。
- 圖示庫固定用 `lucide-react`。
- 地圖幾何投影固定沿用 `d3-geo` + `topojson-client`，不得引入其他地圖/圖表
  庫做地理投影；`public/Map_NewTaipei.json` 內容保持不動。
- 路由固定用 `react-router-dom`。
- 伺服器 / fixture 資料一律經 TanStack Query 的 `useQuery` 存取，不得在元件
  內直接 `useEffect` + `fetch` 拼裝 server state（地圖幾何載入是例外，因為它
  不是本規格「可替換資料層」範圍內的資料，見 Task 10 說明）。
- 跨元件 UI 狀態（目前選取行政區）只能放在 Zustand store
  (`useSelectedDistrict`)，不得放 React Context 或散落的 `useState`。
- CSV 解析固定用 PapaParse，且只能在 `src/data/districts.ts` 內部使用；對外
  只能匯出 `async function fetchDistrictSummaries(): Promise<DistrictSummary[]>`。
- 動效庫固定用 `motion`（`import { motion } from 'motion/react'`），不用
  `framer-motion` 套件名稱。
- 本規格範圍內**不**導入 `react-hook-form`、`zod`、`recharts`（YAGNI：首頁
  無表單與圖表情境，留待各自子專案評估）。
- 測試固定用 Vitest + `@testing-library/react` + jsdom；不建立 E2E 測試。
- 首頁三大資料區塊（KPI、地圖、入口卡）各自被 `react-error-boundary` 的
  `<ErrorBoundary>` 包裹；區塊內部對「預期的」資料載入失敗（`isError`）要
  自行渲染錯誤 UI 與「重新載入」按鈕，`ErrorBoundary` 是攔截未預期
  render-time 例外的最後防線，兩者並存。
- Lint/Format 固定用 ESLint（typescript-eslint flat config）+ Prettier，
  `npm run lint` 需零錯誤。

---

## Task 1: TypeScript 工具鏈遷移（不改變行為）

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Delete: `frontend/vite.config.js`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/vite-env.d.ts`
- Delete: `frontend/src/main.jsx`
- Create: `frontend/src/main.tsx`
- Delete: `frontend/src/App.jsx`
- Create: `frontend/src/App.tsx`
- Delete: `frontend/src/components/TownMap.jsx`
- Create: `frontend/src/components/TownMap.tsx`
- Modify: `frontend/index.html`

**Interfaces:**
- Produces: 路徑別名 `@/*` → `frontend/src/*`（`tsconfig.json` paths +
  `vite.config.ts` resolve.alias），後續所有任務皆可用 `@/xxx` import。
- Produces: `TownMap` 元件（`components/TownMap.tsx`）props
  `{ features: TownFeature[]; selectedTownId: string | null; onSelectTown: (townId: string) => void }`，
  沿用到 Task 10 前都不變。

此任務純屬工具鏈設定與逐字轉型別，不涉及新邏輯，因此沒有「先寫失敗測試」
步驟；驗證方式一律是編譯/建置成功。

- [ ] **Step 1: 更新 `package.json`**

```json
{
  "name": "@newtaipei-youth/frontend",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "d3-geo": "^3.1.1",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "topojson-client": "^3.1.0"
  },
  "devDependencies": {
    "@types/d3-geo": "^3.1.0",
    "@types/node": "^22.10.2",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@types/topojson-client": "^3.1.5",
    "@vitejs/plugin-react": "^4.3.1",
    "typescript": "^5.6.3",
    "vite": "^5.4.8"
  }
}
```

- [ ] **Step 2: 建立 `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    },
    "types": ["vite/client"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: 建立 `tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: 刪除 `vite.config.js`，建立 `vite.config.ts`**

```ts
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

- [ ] **Step 5: 建立 `src/vite-env.d.ts`**

```ts
/// <reference types="vite/client" />
```

- [ ] **Step 6: 刪除 `src/components/TownMap.jsx`，建立 `src/components/TownMap.tsx`**

```tsx
import { useMemo, useState } from "react";
import { geoMercator, geoPath } from "d3-geo";

export interface TownFeatureProperties {
  id: string;
  name: string;
}

export interface TownFeature {
  type: "Feature";
  properties: TownFeatureProperties;
  geometry: { type: string; coordinates: unknown };
}

const MAP_WIDTH = 760;
const MAP_HEIGHT = 560;
const TOWN_COLORS = [
  "#bde0fe",
  "#a2d2ff",
  "#cdeac0",
  "#f9d5a7",
  "#f7c8e0",
  "#d9c2f0",
];

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

interface TownMapProps {
  features: TownFeature[];
  selectedTownId: string | null;
  onSelectTown: (townId: string) => void;
}

export default function TownMap({
  features,
  selectedTownId,
  onSelectTown,
}: TownMapProps) {
  const [hoveredTownId, setHoveredTownId] = useState<string | null>(null);

  const collection = useMemo(
    () => ({ type: "FeatureCollection" as const, features }),
    [features],
  );

  const projection = useMemo(
    () => geoMercator().fitSize([MAP_WIDTH, MAP_HEIGHT], collection as never),
    [collection],
  );

  const pathGenerator = useMemo(() => geoPath(projection), [projection]);
  const hoveredTown = features.find(
    (town) => town.properties?.id === hoveredTownId,
  );
  const tooltipPoint = hoveredTown
    ? pathGenerator.centroid(hoveredTown as never)
    : null;
  const tooltipX = tooltipPoint
    ? clamp(tooltipPoint[0] - 54, 12, MAP_WIDTH - 132)
    : 0;
  const tooltipY = tooltipPoint
    ? clamp(tooltipPoint[1] - 42, 12, MAP_HEIGHT - 48)
    : 0;

  return (
    <div className="map-stage">
      <svg
        className="town-map"
        viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
        role="img"
        aria-label="新北市行政區互動地圖"
      >
        <defs>
          <filter id="map-shadow" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="8" stdDeviation="8" floodOpacity="0.12" />
          </filter>
        </defs>
        <g filter="url(#map-shadow)">
          {features.map((town, index) => {
            const id = town.properties?.id;
            const name = town.properties?.name ?? "未命名行政區";
            const className = [
              "town-path",
              id === selectedTownId ? "is-selected" : "",
              id === hoveredTownId ? "is-hovered" : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <path
                className={className}
                d={pathGenerator(town as never) ?? undefined}
                key={id}
                aria-label={name}
                data-town-id={id}
                style={
                  {
                    "--town-fill": TOWN_COLORS[index % TOWN_COLORS.length],
                  } as React.CSSProperties
                }
                onMouseEnter={() => setHoveredTownId(id)}
                onMouseLeave={() => setHoveredTownId(null)}
                onClick={() => onSelectTown(id)}
              >
                <title>{name}</title>
              </path>
            );
          })}
        </g>
        {hoveredTown && tooltipPoint && (
          <g
            className="map-tooltip"
            pointerEvents="none"
            transform={`translate(${tooltipX} ${tooltipY})`}
          >
            <rect width="132" height="36" rx="9" />
            <text x="66" y="23" textAnchor="middle">
              {hoveredTown.properties?.name ?? "未命名行政區"}
            </text>
          </g>
        )}
      </svg>
      <div className="map-legend">
        <span className="map-legend__swatch" />
        <span>行政區邊界</span>
        <span className="map-legend__selected" />
        <span>目前選取</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 7: 刪除 `src/App.jsx`，建立 `src/App.tsx`**

```tsx
import { useEffect, useState } from "react";
import { feature } from "topojson-client";
import TownMap, { type TownFeature } from "./components/TownMap";

const DATA_URL = "/Map_NewTaipei.json";

function getErrorMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "行政區資料載入失敗，請稍後再試。";
}

export default function App() {
  const [features, setFeatures] = useState<TownFeature[]>([]);
  const [selectedTownId, setSelectedTownId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function loadTopology() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(DATA_URL, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`資料請求失敗（HTTP ${response.status}）`);
        }

        const topology = await response.json();
        const mapObject = topology?.objects?.map;
        if (!mapObject) {
          throw new Error("TopoJSON 缺少 objects.map 資料。");
        }

        const collection = feature(topology, mapObject) as unknown as {
          features: TownFeature[];
        };
        const nextFeatures = collection.features ?? [];
        setFeatures(nextFeatures);
        setSelectedTownId(nextFeatures[0]?.properties?.id ?? null);
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setFeatures([]);
          setSelectedTownId(null);
          setError(getErrorMessage(loadError));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    loadTopology();

    return () => controller.abort();
  }, [reloadKey]);

  const showEmptyState = !loading && !error && features.length === 0;

  return (
    <main className="app-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">NEW TAIPEI · DATA VIEW</p>
          <h1>新北市行政區地圖</h1>
          <p className="page-subtitle">
            以 TopoJSON 呈現新北市 29 個行政區的邊界資料。
          </p>
        </div>
        <div
          className="data-badge"
          aria-label={`目前載入 ${features.length} 個行政區`}
        >
          <span className="data-badge__dot" />
          <span>{features.length || "--"} 個行政區</span>
        </div>
      </header>

      {loading && (
        <section className="state-panel" aria-live="polite">
          <span className="loader" aria-hidden="true" />
          <div>
            <h2>正在載入地圖資料</h2>
            <p>正在解析 650000 行政區 TopoJSON。</p>
          </div>
        </section>
      )}

      {error && (
        <section className="state-panel state-panel--error" role="alert">
          <span className="state-icon" aria-hidden="true">
            !
          </span>
          <div>
            <h2>地圖資料載入失敗</h2>
            <p>{error}</p>
            <button
              className="button button--light"
              type="button"
              onClick={() => setReloadKey((value) => value + 1)}
            >
              重新載入
            </button>
          </div>
        </section>
      )}

      {showEmptyState && (
        <section className="state-panel" role="status">
          <span className="state-icon" aria-hidden="true">
            ∅
          </span>
          <div>
            <h2>找不到行政區資料</h2>
            <p>目前的 TopoJSON 沒有可顯示的 Polygon。</p>
          </div>
        </section>
      )}

      {!loading && !error && features.length > 0 && (
        <section
          className="map-card map-card--solo"
          aria-labelledby="map-title"
        >
          <div className="card-heading">
            <div>
              <p className="section-kicker">INTERACTIVE MAP</p>
              <h2 id="map-title">行政區分布</h2>
            </div>
            <span className="card-hint">Hover / Click</span>
          </div>
          <TownMap
            features={features}
            selectedTownId={selectedTownId}
            onSelectTown={setSelectedTownId}
          />
        </section>
      )}
    </main>
  );
}
```

- [ ] **Step 8: 刪除 `src/main.jsx`，建立 `src/main.tsx`**

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("找不到 #root 掛載節點。");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 9: 更新 `index.html` 的 script 路徑**

把 `<script type="module" src="/src/main.jsx"></script>` 改成：

```html
<script type="module" src="/src/main.tsx"></script>
```

- [ ] **Step 10: 安裝依賴並驗證編譯**

```bash
cd frontend
npm install
npm run build
```

Expected: `tsc -b` 與 `vite build` 皆無錯誤，`dist/` 產生建置檔案。

- [ ] **Step 11: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/index.html frontend/src/vite-env.d.ts frontend/src/main.tsx frontend/src/App.tsx frontend/src/components/TownMap.tsx
git rm frontend/vite.config.js frontend/src/main.jsx frontend/src/App.jsx frontend/src/components/TownMap.jsx
git commit -m "$(cat <<'EOF'
chore(frontend): migrate to TypeScript toolchain

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 2: Vitest + Testing Library 設定

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/App.smoke.test.tsx`

**Interfaces:**
- Produces: `npm run test`（`vitest run`）與 `npm run test:watch`
  （`vitest`）指令，供 Task 6 起所有測試任務使用。
- Produces: 全域 `expect(...).toBeInTheDocument()` 等 jest-dom matcher
  （透過 `src/test/setup.ts`），以及 Vitest `globals: true`（測試檔不用
  另外 import `describe/it/expect`，但本規格所有測試仍顯式 import 以利
  可讀性）。

- [ ] **Step 1: 安裝測試依賴**

```bash
cd frontend
npm install -D vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom
```

- [ ] **Step 2: 更新 `vite.config.ts` 加入 `test` 設定**

```ts
/// <reference types="vitest/config" />
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

- [ ] **Step 3: 建立 `src/test/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 4: 更新 `tsconfig.json` 的 `types`**

把 Step 2（Task 1）建立的 `"types": ["vite/client"]` 改成：

```json
"types": ["vite/client", "vitest/globals", "@testing-library/jest-dom"]
```

- [ ] **Step 5: 寫一個煙霧測試驗證工具鏈本身可用**

```tsx
// src/App.smoke.test.tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App smoke test", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ objects: {} }),
      }),
    );
  });

  it("renders the loading state before data arrives", () => {
    render(<App />);
    expect(screen.getByText("正在載入地圖資料")).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: 執行測試確認通過**

```bash
npm run test
```

Expected: 1 個測試檔、1 個測試通過。

- [ ] **Step 7: 新增 `package.json` scripts**

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json frontend/src/test/setup.ts frontend/src/App.smoke.test.tsx
git commit -m "$(cat <<'EOF'
test(frontend): add Vitest + Testing Library toolchain

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 3: ESLint + Prettier 設定

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/eslint.config.js`
- Create: `frontend/.prettierrc.json`
- Create: `frontend/.prettierignore`

**Interfaces:**
- Produces: `npm run lint` 指令。之後每個任務新增檔案都應通過此 lint。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install -D eslint @eslint/js typescript-eslint eslint-plugin-react-hooks eslint-plugin-react-refresh globals prettier eslint-config-prettier
```

- [ ] **Step 2: 建立 `eslint.config.js`**

```js
import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier";

export default tseslint.config(
  { ignores: ["dist"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  eslintConfigPrettier,
);
```

- [ ] **Step 3: 建立 `.prettierrc.json`**

```json
{
  "semi": true,
  "singleQuote": false,
  "trailingComma": "all",
  "printWidth": 100
}
```

- [ ] **Step 4: 建立 `.prettierignore`**

```text
dist
node_modules
package-lock.json
```

- [ ] **Step 5: 新增 `package.json` script**

```json
"lint": "eslint ."
```

- [ ] **Step 6: 執行 lint 確認目前程式碼零錯誤**

```bash
npm run lint
```

Expected: 0 errors（若有 warning 可接受，但需人工確認非隱藏 bug）。

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/eslint.config.js frontend/.prettierrc.json frontend/.prettierignore
git commit -m "$(cat <<'EOF'
chore(frontend): add ESLint + Prettier configuration

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 4: Tailwind CSS + 設計語言 Token

**Files:**
- Create: `frontend/tailwind.config.ts`
- Create: `frontend/postcss.config.js`
- Modify: `frontend/src/styles.css`
- Create: `frontend/DESIGN_LANGUAGE.md`

**Interfaces:**
- Produces: Tailwind color tokens `primary`、`background`、`surface`、
  `accent.teal`/`accent.warning`/`accent.slate`、`risk.low`/`risk.medium`/
  `risk.high`，後續所有元件皆透過這些 class 名稱取色（例如
  `bg-primary`、`text-accent-slate`、`bg-risk-high/15`）。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install -D tailwindcss postcss autoprefixer
```

- [ ] **Step 2: 建立 `tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#005599",
          foreground: "#ffffff",
        },
        background: "#f8f9ff",
        surface: "#ffffff",
        accent: {
          teal: "#0f9d8a",
          warning: "#f2994a",
          slate: "#5b7799",
        },
        risk: {
          low: "#1f9d6c",
          medium: "#f2994a",
          high: "#d64545",
        },
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 3: 建立 `postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 4: 把 `src/styles.css` 換成 Tailwind 指令**

保留舊的 `.town-path` / `.map-*` / `.state-panel` 等 class（`TownMap.tsx`
與 `App.tsx` 目前仍依賴它們），只在檔案最上方加入 Tailwind 指令：

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

/* --- 以下為既有原型樣式，將於 Task 10-12 遷移為 Tailwind class 後移除 --- */
```

（`:root` 開始的其餘內容維持不動，之後 Task 10 遷移 `DistrictChoroplethMap`
與 Task 12 完成 `HomePage` 時，逐步刪除本檔案中已不再使用的規則。）

- [ ] **Step 5: 建立 `DESIGN_LANGUAGE.md`**

```markdown
# 設計語言（Design Language）

新北青年機會地圖 Dashboard 全站共用的視覺設計 token。所有頁面／板塊皆應
透過 Tailwind theme（`tailwind.config.ts`）取用這些顏色，不得在元件中
寫死色碼（SVG choropleth 依資料動態計算顏色除外）。

## 色彩 Token

| Token | 色碼 | 用途 |
| --- | --- | --- |
| `primary` | `#005599` | 主色：導覽列品牌色、主要按鈕、選取狀態、連結 |
| `background` | `#f8f9ff` | 頁面背景 |
| `surface` | `#ffffff` | 卡片／容器背景 |
| `accent.teal` | `#0f9d8a` | 正向趨勢、成功狀態輔助色 |
| `accent.warning` | `#f2994a` | 警示、待處理狀態輔助色 |
| `accent.slate` | `#5b7799` | 次要文字、標籤、圖例 |
| `risk.low` | `#1f9d6c` | 留才風險等級：低 |
| `risk.medium` | `#f2994a` | 留才風險等級：中 |
| `risk.high` | `#d64545` | 留才風險等級：高 |

## 字級

沿用 Tailwind 預設字級尺度（`text-xs` ~ `text-4xl`），標題一律使用
`font-bold` / `font-extrabold`，內文使用系統預設字重。

## 間距與圓角

- 卡片圓角：`rounded-2xl`（1rem）
- 卡片內距：`p-5`
- 版面最大寬度：`max-w-[1440px]`，左右內距 `px-6`

## Icon

全站使用 `lucide-react`，尺寸預設 20px，顏色跟隨文字色（`currentColor`）。
```

- [ ] **Step 6: 驗證建置**

```bash
npm run build
```

Expected: 建置成功，且 `dist` 內的 CSS 包含 Tailwind 產生的 utility class。

- [ ] **Step 7: Commit**

```bash
git add frontend/tailwind.config.ts frontend/postcss.config.js frontend/src/styles.css frontend/DESIGN_LANGUAGE.md frontend/package.json frontend/package-lock.json
git commit -m "$(cat <<'EOF'
feat(frontend): add Tailwind CSS and design language tokens

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 5: shadcn/ui 風格元件（Button、Card、Badge、Skeleton）+ `cn()`

**Files:**
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/card.tsx`
- Create: `frontend/src/components/ui/badge.tsx`
- Create: `frontend/src/components/ui/skeleton.tsx`
- Create: `frontend/src/components/ui/button.test.tsx`

**Interfaces:**
- Produces: `cn(...inputs: ClassValue[]): string`（`@/lib/utils`）。
- Produces: `Button`（`@/components/ui/button`，variant:
  `"default" | "outline" | "destructive"`, size: `"default" | "sm"`）。
- Produces: `Card`、`CardHeader`、`CardTitle`、`CardContent`
  （`@/components/ui/card`）。
- Produces: `Badge`（`@/components/ui/badge`，variant:
  `"default" | "secondary" | "low" | "medium" | "high"`）。
- Produces: `Skeleton`（`@/components/ui/skeleton`）。
- Consumes: Task 4 的 Tailwind color token（`primary`、`risk.*`）。

規格 §7 提到「透過 shadcn CLI 初始化 `components/ui/`」；`shadcn` CLI 需要
互動式終端機輸入與網路存取，在自動化執行的任務流程中不可靠。本任務改為
手刻與 shadcn CLI 產生結果等價的標準元件程式碼（同樣的 API、同樣的
`cva` + `cn()` 模式），效果相同且可重現。若之後要新增更多 shadcn 元件
（如 `Tabs`），可比照本任務的手刻模式，或在有互動式終端機時另外執行
CLI 並手動調整 import 路徑。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install clsx tailwind-merge class-variance-authority
```

- [ ] **Step 2: 建立 `src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: 建立 `src/components/ui/button.tsx`**

```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline: "border border-slate-300 bg-white hover:bg-slate-50",
        destructive: "bg-risk-high text-white hover:bg-risk-high/90",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 px-3 text-xs",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

- [ ] **Step 4: 建立 `src/components/ui/card.tsx`**

```tsx
import * as React from "react";
import { cn } from "@/lib/utils";

const Card = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div
    ref={ref}
    className={cn(
      "rounded-2xl border border-slate-200 bg-surface shadow-sm",
      className,
    )}
    {...props}
  />
));
Card.displayName = "Card";

const CardHeader = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("flex flex-col gap-1 p-5 pb-2", className)} {...props} />
));
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<
  HTMLHeadingElement,
  React.HTMLAttributes<HTMLHeadingElement>
>(({ className, ...props }, ref) => (
  <h3
    ref={ref}
    className={cn("font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
CardTitle.displayName = "CardTitle";

const CardContent = React.forwardRef<
  HTMLDivElement,
  React.HTMLAttributes<HTMLDivElement>
>(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("p-5 pt-2", className)} {...props} />
));
CardContent.displayName = "CardContent";

export { Card, CardHeader, CardTitle, CardContent };
```

- [ ] **Step 5: 建立 `src/components/ui/badge.tsx`**

```tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-white",
        secondary: "border-transparent bg-slate-100 text-slate-700",
        low: "border-transparent bg-risk-low/15 text-risk-low",
        medium: "border-transparent bg-risk-medium/15 text-risk-medium",
        high: "border-transparent bg-risk-high/15 text-risk-high",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
```

- [ ] **Step 6: 建立 `src/components/ui/skeleton.tsx`**

```tsx
import { cn } from "@/lib/utils";

function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("animate-pulse rounded-md bg-slate-200", className)} {...props} />
  );
}

export { Skeleton };
```

- [ ] **Step 7: 寫失敗測試驗證 `Button` variant 行為**

```tsx
// src/components/ui/button.test.tsx
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Button } from "./button";

describe("Button", () => {
  it("applies the destructive variant class when requested", () => {
    render(<Button variant="destructive">重新載入</Button>);
    expect(screen.getByRole("button", { name: "重新載入" })).toHaveClass(
      "bg-risk-high",
    );
  });
});
```

- [ ] **Step 8: 執行測試確認先失敗（元件尚未建立時應是 import 失敗）**

由於 Step 3 已建立 `button.tsx`，此步驟改為直接執行並確認通過：

```bash
npm run test -- button
```

Expected: PASS。

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/lib/utils.ts frontend/src/components/ui
git commit -m "$(cat <<'EOF'
feat(frontend): add hand-authored shadcn/ui primitives

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 6: 行政區型別、Fixture 與資料層（`data/districts.ts`）

**Files:**
- Create: `frontend/src/types/district.ts`
- Create: `frontend/src/fixtures/districts.csv`
- Create: `frontend/src/data/districts.ts`
- Create: `frontend/src/data/districts.test.ts`

**Interfaces:**
- Produces: `type RetentionRiskLevel = "low" | "medium" | "high"`
  （`@/types/district`）。
- Produces: `interface DistrictSummary { id: string; name: string;
  youthPopulation: number; opportunityIndex: number; retentionRiskLevel:
  RetentionRiskLevel; youthParticipationIndex: number; fertilityRate: number;
  policySupportScore: number }`（`@/types/district`）。
- Produces: `async function fetchDistrictSummaries(): Promise<DistrictSummary[]>`
  （`@/data/districts`），Task 9 的 `useDistrictSummary` 直接呼叫此函式作為
  `queryFn`。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install papaparse
npm install -D @types/papaparse
```

- [ ] **Step 2: 建立 `src/types/district.ts`**

```ts
export type RetentionRiskLevel = "low" | "medium" | "high";

export interface DistrictSummary {
  id: string;
  name: string;
  youthPopulation: number;
  opportunityIndex: number;
  retentionRiskLevel: RetentionRiskLevel;
  youthParticipationIndex: number;
  fertilityRate: number;
  policySupportScore: number;
}
```

- [ ] **Step 3: 建立 `src/fixtures/districts.csv`**

29 區資料為本地模擬 fixture（非真實統計數字），欄位對齊
`DistrictSummary`：

```csv
id,name,youthPopulation,opportunityIndex,retentionRiskLevel,youthParticipationIndex,fertilityRate,policySupportScore
65000010,板橋區,148000,86,low,72,42.1,81
65000020,三重區,132000,78,low,68,40.5,76
65000030,中和區,139000,80,low,70,41.0,78
65000040,永和區,58000,75,medium,65,38.2,70
65000050,新莊區,121000,79,low,69,43.0,79
65000060,新店區,84000,74,medium,64,39.5,73
65000070,樹林區,65000,71,medium,60,41.8,68
65000080,鶯歌區,29000,63,medium,55,44.0,60
65000090,三峽區,44000,66,medium,58,45.2,62
65000100,淡水區,86000,72,medium,63,42.7,71
65000110,汐止區,79000,73,medium,62,40.9,72
65000120,瑞芳區,21000,58,high,48,46.5,54
65000130,土城區,78000,77,low,67,41.3,75
65000140,蘆洲區,68000,76,low,66,39.8,74
65000150,五股區,42000,68,medium,57,43.5,64
65000160,泰山區,29000,65,medium,56,42.0,61
65000170,林口區,58000,81,low,71,44.8,80
65000180,深坑區,9000,61,medium,52,47.0,58
65000190,石碇區,3000,52,high,40,50.2,45
65000200,坪林區,2000,50,high,38,51.0,42
65000210,三芝區,8000,55,high,44,48.6,50
65000220,石門區,5000,53,high,42,49.1,47
65000230,八里區,15000,60,medium,50,45.9,56
65000240,平溪區,2000,49,high,37,52.3,40
65000250,雙溪區,3000,51,high,39,53.1,43
65000260,貢寮區,4000,54,high,41,49.8,46
65000270,金山區,6000,56,high,45,47.8,52
65000280,萬里區,5000,55,high,43,48.9,49
65000290,烏來區,1500,48,high,35,54.0,38
```

- [ ] **Step 4: 先寫失敗測試（`data/districts.test.ts`）**

```ts
import { describe, expect, it, vi, beforeEach } from "vitest";
import { fetchDistrictSummaries } from "./districts";

function mockFetchResolvedWith(csvText: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      text: async () => csvText,
    }),
  );
}

const VALID_HEADER =
  "id,name,youthPopulation,opportunityIndex,retentionRiskLevel,youthParticipationIndex,fertilityRate,policySupportScore";

describe("fetchDistrictSummaries", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("parses a valid CSV row into a typed DistrictSummary", async () => {
    mockFetchResolvedWith(
      `${VALID_HEADER}\n65000010,板橋區,148000,86,low,72,42.1,81\n`,
    );

    const result = await fetchDistrictSummaries();

    expect(result).toEqual([
      {
        id: "65000010",
        name: "板橋區",
        youthPopulation: 148000,
        opportunityIndex: 86,
        retentionRiskLevel: "low",
        youthParticipationIndex: 72,
        fertilityRate: 42.1,
        policySupportScore: 81,
      },
    ]);
  });

  it("throws when the HTTP response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 500 }),
    );

    await expect(fetchDistrictSummaries()).rejects.toThrow("HTTP 500");
  });

  it("throws when retentionRiskLevel is not a known value", async () => {
    mockFetchResolvedWith(
      `${VALID_HEADER}\n65000010,板橋區,148000,86,unknown,72,42.1,81\n`,
    );

    await expect(fetchDistrictSummaries()).rejects.toThrow(
      "未知的留才風險等級",
    );
  });

  it("throws when a numeric field cannot be parsed", async () => {
    mockFetchResolvedWith(
      `${VALID_HEADER}\n65000010,板橋區,not-a-number,86,low,72,42.1,81\n`,
    );

    await expect(fetchDistrictSummaries()).rejects.toThrow(
      "不是有效數字",
    );
  });
});
```

- [ ] **Step 5: 執行測試確認失敗（`districts.ts` 尚未存在）**

```bash
npm run test -- districts
```

Expected: FAIL，錯誤訊息為找不到模組 `./districts`。

- [ ] **Step 6: 建立 `src/data/districts.ts`**

```ts
import Papa from "papaparse";
import type { DistrictSummary, RetentionRiskLevel } from "@/types/district";
import districtsCsvUrl from "@/fixtures/districts.csv?url";

const VALID_RISK_LEVELS: RetentionRiskLevel[] = ["low", "medium", "high"];

interface DistrictCsvRow {
  id: string;
  name: string;
  youthPopulation: string;
  opportunityIndex: string;
  retentionRiskLevel: string;
  youthParticipationIndex: string;
  fertilityRate: string;
  policySupportScore: string;
}

function toRiskLevel(value: string): RetentionRiskLevel {
  const normalized = value.trim().toLowerCase();
  if ((VALID_RISK_LEVELS as string[]).includes(normalized)) {
    return normalized as RetentionRiskLevel;
  }
  throw new Error(`未知的留才風險等級："${value}"`);
}

function toNumber(value: string, field: string): number {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) {
    throw new Error(`欄位 "${field}" 不是有效數字："${value}"`);
  }
  return parsed;
}

function parseRow(row: DistrictCsvRow): DistrictSummary {
  if (!row.id || !row.name) {
    throw new Error("行政區資料缺少 id 或 name 欄位。");
  }

  return {
    id: row.id,
    name: row.name,
    youthPopulation: toNumber(row.youthPopulation, "youthPopulation"),
    opportunityIndex: toNumber(row.opportunityIndex, "opportunityIndex"),
    retentionRiskLevel: toRiskLevel(row.retentionRiskLevel),
    youthParticipationIndex: toNumber(
      row.youthParticipationIndex,
      "youthParticipationIndex",
    ),
    fertilityRate: toNumber(row.fertilityRate, "fertilityRate"),
    policySupportScore: toNumber(row.policySupportScore, "policySupportScore"),
  };
}

export async function fetchDistrictSummaries(): Promise<DistrictSummary[]> {
  const response = await fetch(districtsCsvUrl);
  if (!response.ok) {
    throw new Error(`行政區資料請求失敗（HTTP ${response.status}）`);
  }

  const csvText = await response.text();
  const { data, errors } = Papa.parse<DistrictCsvRow>(csvText, {
    header: true,
    skipEmptyLines: true,
  });

  if (errors.length > 0) {
    throw new Error(`行政區資料解析失敗：${errors[0].message}`);
  }

  return data.map(parseRow);
}
```

- [ ] **Step 7: 執行測試確認通過**

```bash
npm run test -- districts
```

Expected: 4 個測試全數 PASS。

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/types/district.ts frontend/src/fixtures/districts.csv frontend/src/data/districts.ts frontend/src/data/districts.test.ts
git commit -m "$(cat <<'EOF'
feat(frontend): add district types, CSV fixture and data-service layer

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 7: Zustand「目前選取行政區」Store

**Files:**
- Create: `frontend/src/stores/useSelectedDistrict.ts`
- Create: `frontend/src/stores/useSelectedDistrict.test.ts`

**Interfaces:**
- Produces: `useSelectedDistrict` Zustand store，state:
  `{ selectedDistrictId: string | null }`，actions:
  `selectDistrict(districtId: string): void`、`clearSelection(): void`。
  Task 10 的 `DistrictChoroplethMap` 直接讀寫此 store。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install zustand
```

- [ ] **Step 2: 先寫失敗測試**

```ts
// src/stores/useSelectedDistrict.test.ts
import { describe, expect, it, beforeEach } from "vitest";
import { useSelectedDistrict } from "./useSelectedDistrict";

describe("useSelectedDistrict", () => {
  beforeEach(() => {
    useSelectedDistrict.setState({ selectedDistrictId: null });
  });

  it("starts with no district selected", () => {
    expect(useSelectedDistrict.getState().selectedDistrictId).toBeNull();
  });

  it("selectDistrict sets the selected district id", () => {
    useSelectedDistrict.getState().selectDistrict("65000010");
    expect(useSelectedDistrict.getState().selectedDistrictId).toBe(
      "65000010",
    );
  });

  it("clearSelection resets the selected district id to null", () => {
    useSelectedDistrict.getState().selectDistrict("65000010");
    useSelectedDistrict.getState().clearSelection();
    expect(useSelectedDistrict.getState().selectedDistrictId).toBeNull();
  });
});
```

- [ ] **Step 3: 執行測試確認失敗**

```bash
npm run test -- useSelectedDistrict
```

Expected: FAIL，找不到模組 `./useSelectedDistrict`。

- [ ] **Step 4: 建立 `src/stores/useSelectedDistrict.ts`**

```ts
import { create } from "zustand";

interface SelectedDistrictState {
  selectedDistrictId: string | null;
  selectDistrict: (districtId: string) => void;
  clearSelection: () => void;
}

export const useSelectedDistrict = create<SelectedDistrictState>((set) => ({
  selectedDistrictId: null,
  selectDistrict: (districtId) => set({ selectedDistrictId: districtId }),
  clearSelection: () => set({ selectedDistrictId: null }),
}));
```

- [ ] **Step 5: 執行測試確認通過**

```bash
npm run test -- useSelectedDistrict
```

Expected: 3 個測試全數 PASS。

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/stores
git commit -m "$(cat <<'EOF'
feat(frontend): add Zustand store for selected district UI state

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 8: 路由、AppLayout、NavBar、Placeholder 頁與 QueryClientProvider

**Files:**
- Create: `frontend/src/app/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/routes.tsx`
- Create: `frontend/src/app/AppLayout.tsx`
- Create: `frontend/src/components/shared/NavBar.tsx`
- Create: `frontend/src/components/shared/PlaceholderPage.tsx`
- Create: `frontend/src/features/home/HomePage.tsx`
- Modify: `frontend/index.html`
- Delete: `frontend/src/main.tsx`
- Delete: `frontend/src/App.tsx`
- Delete: `frontend/src/App.smoke.test.tsx`（改為 Task 12 針對新 HomePage 的
  測試涵蓋範圍，原 smoke test 依賴的舊 `App` 已被拆分移除）

**Interfaces:**
- Produces: `router`（`@/app/routes`，`createBrowserRouter` 結果），5 條
  路由：`/`、`/employment`、`/politics`、`/fertility`、`/policy-support`。
- Produces: 全域 `QueryClient` 實例，透過 `QueryClientProvider` 包在
  `App.tsx` 最外層，Task 9 的 `useDistrictSummary` 依賴它才能運作。
- Consumes: Task 1 的 `TownMap`（暫時原封不動地被 `HomePage.tsx` 使用，
  直到 Task 10 才替換為 `DistrictChoroplethMap`）。

此任務是「搬移＋補管線」而非新邏輯，因此沒有先寫失敗測試的步驟；驗證方式
是建置成功 + 手動確認路由可切換。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install react-router-dom @tanstack/react-query
```

- [ ] **Step 2: 建立 `src/components/shared/PlaceholderPage.tsx`**

```tsx
interface PlaceholderPageProps {
  title: string;
}

export default function PlaceholderPage({ title }: PlaceholderPageProps) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
        Coming Soon
      </p>
      <h1 className="text-3xl font-bold text-slate-900">{title} · 規劃中</h1>
      <p className="max-w-md text-slate-500">
        此板塊將於後續子專案中實作，敬請期待。
      </p>
    </div>
  );
}
```

- [ ] **Step 3: 建立 `src/components/shared/NavBar.tsx`**

```tsx
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "主頁戰情室" },
  { to: "/employment", label: "青年就業" },
  { to: "/politics", label: "青年參政" },
  { to: "/fertility", label: "青年生育" },
  { to: "/policy-support", label: "施政協助" },
];

export default function NavBar() {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-[1440px] items-center gap-6 px-6 py-4">
        <span className="text-lg font-extrabold text-primary">
          新北青年機會地圖
        </span>
        <ul className="flex flex-1 items-center gap-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-4 py-2 text-sm font-semibold text-slate-600 transition-colors hover:bg-primary/10 hover:text-primary",
                    isActive && "bg-primary text-white hover:bg-primary hover:text-white",
                  )
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
```

- [ ] **Step 4: 建立 `src/app/AppLayout.tsx`**

```tsx
import { Outlet } from "react-router-dom";
import NavBar from "@/components/shared/NavBar";

export default function AppLayout() {
  return (
    <div className="min-h-screen bg-background">
      <NavBar />
      <Outlet />
    </div>
  );
}
```

- [ ] **Step 5: 把 `src/App.tsx` 內容搬到 `src/features/home/HomePage.tsx`**

內容與 Task 1 的 `App.tsx` 完全相同，只改函式名稱與 import 路徑：

```tsx
import { useEffect, useState } from "react";
import { feature } from "topojson-client";
import TownMap, { type TownFeature } from "@/components/TownMap";

const DATA_URL = "/Map_NewTaipei.json";

function getErrorMessage(error: unknown) {
  if (error instanceof Error && error.message) {
    return error.message;
  }

  return "行政區資料載入失敗，請稍後再試。";
}

export default function HomePage() {
  const [features, setFeatures] = useState<TownFeature[]>([]);
  const [selectedTownId, setSelectedTownId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    async function loadTopology() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(DATA_URL, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`資料請求失敗（HTTP ${response.status}）`);
        }

        const topology = await response.json();
        const mapObject = topology?.objects?.map;
        if (!mapObject) {
          throw new Error("TopoJSON 缺少 objects.map 資料。");
        }

        const collection = feature(topology, mapObject) as unknown as {
          features: TownFeature[];
        };
        const nextFeatures = collection.features ?? [];
        setFeatures(nextFeatures);
        setSelectedTownId(nextFeatures[0]?.properties?.id ?? null);
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setFeatures([]);
          setSelectedTownId(null);
          setError(getErrorMessage(loadError));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    }

    loadTopology();

    return () => controller.abort();
  }, [reloadKey]);

  const showEmptyState = !loading && !error && features.length === 0;

  return (
    <main className="app-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">NEW TAIPEI · DATA VIEW</p>
          <h1>新北市行政區地圖</h1>
          <p className="page-subtitle">
            以 TopoJSON 呈現新北市 29 個行政區的邊界資料。
          </p>
        </div>
        <div
          className="data-badge"
          aria-label={`目前載入 ${features.length} 個行政區`}
        >
          <span className="data-badge__dot" />
          <span>{features.length || "--"} 個行政區</span>
        </div>
      </header>

      {loading && (
        <section className="state-panel" aria-live="polite">
          <span className="loader" aria-hidden="true" />
          <div>
            <h2>正在載入地圖資料</h2>
            <p>正在解析 650000 行政區 TopoJSON。</p>
          </div>
        </section>
      )}

      {error && (
        <section className="state-panel state-panel--error" role="alert">
          <span className="state-icon" aria-hidden="true">
            !
          </span>
          <div>
            <h2>地圖資料載入失敗</h2>
            <p>{error}</p>
            <button
              className="button button--light"
              type="button"
              onClick={() => setReloadKey((value) => value + 1)}
            >
              重新載入
            </button>
          </div>
        </section>
      )}

      {showEmptyState && (
        <section className="state-panel" role="status">
          <span className="state-icon" aria-hidden="true">
            ∅
          </span>
          <div>
            <h2>找不到行政區資料</h2>
            <p>目前的 TopoJSON 沒有可顯示的 Polygon。</p>
          </div>
        </section>
      )}

      {!loading && !error && features.length > 0 && (
        <section
          className="map-card map-card--solo"
          aria-labelledby="map-title"
        >
          <div className="card-heading">
            <div>
              <p className="section-kicker">INTERACTIVE MAP</p>
              <h2 id="map-title">行政區分布</h2>
            </div>
            <span className="card-hint">Hover / Click</span>
          </div>
          <TownMap
            features={features}
            selectedTownId={selectedTownId}
            onSelectTown={setSelectedTownId}
          />
        </section>
      )}
    </main>
  );
}
```

- [ ] **Step 6: 建立 `src/app/routes.tsx`**

```tsx
import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./AppLayout";
import HomePage from "@/features/home/HomePage";
import PlaceholderPage from "@/components/shared/PlaceholderPage";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/employment", element: <PlaceholderPage title="青年就業" /> },
      { path: "/politics", element: <PlaceholderPage title="青年參政" /> },
      { path: "/fertility", element: <PlaceholderPage title="青年生育" /> },
      {
        path: "/policy-support",
        element: <PlaceholderPage title="施政協助" />,
      },
    ],
  },
]);
```

- [ ] **Step 7: 建立 `src/app/App.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { router } from "./routes";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
```

- [ ] **Step 8: 建立 `src/app/main.tsx`（刪除舊的 `src/main.tsx`）**

```tsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "../styles.css";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("找不到 #root 掛載節點。");
}

createRoot(rootElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 9: 更新 `index.html` script 路徑**

```html
<script type="module" src="/src/app/main.tsx"></script>
```

- [ ] **Step 10: 刪除舊檔案**

刪除 `frontend/src/main.tsx`、`frontend/src/App.tsx`、
`frontend/src/App.smoke.test.tsx`（此煙霧測試依賴的舊 `App` 元件已被
`HomePage` 取代，其涵蓋的「loading 狀態」行為會在 Task 12 的
`HomePage`/`KpiSummaryRow`/`DistrictChoroplethMap` 測試中重新涵蓋）。

- [ ] **Step 11: 驗證建置**

```bash
npm run build
```

Expected: 無型別錯誤，建置成功。

- [ ] **Step 12: 手動驗證路由**

```bash
npm run dev
```

在瀏覽器開啟 dev server URL，依序點擊導覽列 5 個連結，確認：
- `/` 顯示原本的地圖原型內容（尚未套用新設計，這是預期的，Task 10-12
  才會重做視覺）。
- `/employment`、`/politics`、`/fertility`、`/policy-support` 顯示對應的
  「板塊名稱 · 規劃中」文字，且瀏覽器 URL 正確切換、無 console 錯誤。

- [ ] **Step 13: Commit**

```bash
git add frontend/index.html frontend/src/app frontend/src/components/shared frontend/src/features/home/HomePage.tsx frontend/package.json frontend/package-lock.json
git rm frontend/src/main.tsx frontend/src/App.tsx frontend/src/App.smoke.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add router, layout shell and QueryClientProvider

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 9: `useDistrictSummary` TanStack Query Hook

**Files:**
- Create: `frontend/src/features/home/hooks/useDistrictSummary.ts`
- Create: `frontend/src/features/home/hooks/useDistrictSummary.test.tsx`

**Interfaces:**
- Consumes: `fetchDistrictSummaries`（Task 6, `@/data/districts`）。
- Consumes: `QueryClientProvider`（Task 8, 已包在 `App.tsx` 最外層）。
- Produces: `useDistrictSummary(): UseQueryResult<DistrictSummary[], Error>`
  （`@/features/home/hooks/useDistrictSummary`，含 `data`、`isLoading`、
  `isError`、`error`、`refetch`），Task 10、11、12 的三個首頁元件皆呼叫
  此 hook 取得同一份 query cache。

- [ ] **Step 1: 先寫失敗測試**

```tsx
// src/features/home/hooks/useDistrictSummary.test.tsx
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { useDistrictSummary } from "./useDistrictSummary";
import * as districtsData from "@/data/districts";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

describe("useDistrictSummary", () => {
  it("exposes the data returned by fetchDistrictSummaries", async () => {
    vi.spyOn(districtsData, "fetchDistrictSummaries").mockResolvedValue([
      {
        id: "65000010",
        name: "板橋區",
        youthPopulation: 148000,
        opportunityIndex: 86,
        retentionRiskLevel: "low",
        youthParticipationIndex: 72,
        fertilityRate: 42.1,
        policySupportScore: 81,
      },
    ]);

    const { result } = renderHook(() => useDistrictSummary(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].name).toBe("板橋區");
  });
});
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
npm run test -- useDistrictSummary
```

Expected: FAIL，找不到模組 `./useDistrictSummary`。

- [ ] **Step 3: 建立 `src/features/home/hooks/useDistrictSummary.ts`**

```ts
import { useQuery } from "@tanstack/react-query";
import { fetchDistrictSummaries } from "@/data/districts";

export function useDistrictSummary() {
  return useQuery({
    queryKey: ["district-summaries"],
    queryFn: fetchDistrictSummaries,
  });
}
```

- [ ] **Step 4: 執行測試確認通過**

```bash
npm run test -- useDistrictSummary
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/home/hooks
git commit -m "$(cat <<'EOF'
feat(frontend): add useDistrictSummary TanStack Query hook

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 10: `DistrictChoroplethMap` 遷移

**Files:**
- Create: `frontend/src/features/home/components/DistrictChoroplethMap.tsx`
- Create: `frontend/src/features/home/components/DistrictChoroplethMap.test.tsx`
- Delete: `frontend/src/components/TownMap.tsx`

**Interfaces:**
- Consumes: `useDistrictSummary`（Task 9）。
- Consumes: `useSelectedDistrict`（Task 7）。
- Consumes: `Skeleton`、`Button`（Task 5）。
- Produces: `DistrictChoroplethMap`（no props，`@/features/home/components/DistrictChoroplethMap`），
  Task 12 的 `HomePage` 直接引用。

- [ ] **Step 1: 先寫失敗測試**

```tsx
// src/features/home/components/DistrictChoroplethMap.test.tsx
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import DistrictChoroplethMap from "./DistrictChoroplethMap";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";

vi.mock("../hooks/useDistrictSummary");
vi.mock("topojson-client", () => ({
  feature: () => ({
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { id: "A", name: "測試甲區" },
        geometry: {
          type: "Polygon",
          coordinates: [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]],
        },
      },
      {
        type: "Feature",
        properties: { id: "B", name: "測試乙區" },
        geometry: {
          type: "Polygon",
          coordinates: [[[20, 0], [20, 10], [30, 10], [30, 0], [20, 0]]],
        },
      },
    ],
  }),
}));

const mockedUseDistrictSummary = vi.mocked(useDistrictSummary);

const SAMPLE_DISTRICTS = [
  {
    id: "A",
    name: "測試甲區",
    youthPopulation: 1000,
    opportunityIndex: 80,
    retentionRiskLevel: "low" as const,
    youthParticipationIndex: 60,
    fertilityRate: 40,
    policySupportScore: 70,
  },
  {
    id: "B",
    name: "測試乙區",
    youthPopulation: 500,
    opportunityIndex: 50,
    retentionRiskLevel: "high" as const,
    youthParticipationIndex: 40,
    fertilityRate: 45,
    policySupportScore: 50,
  },
];

beforeEach(() => {
  useSelectedDistrict.setState({ selectedDistrictId: null });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ objects: { map: {} } }),
    }),
  );
  mockedUseDistrictSummary.mockReturnValue({
    data: SAMPLE_DISTRICTS,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useDistrictSummary>);
});

describe("DistrictChoroplethMap", () => {
  it("selects a district in the store when its path is clicked", async () => {
    render(<DistrictChoroplethMap />);
    const pathA = await screen.findByLabelText("測試甲區");

    fireEvent.click(pathA);

    expect(useSelectedDistrict.getState().selectedDistrictId).toBe("A");
  });

  it("shows a tooltip with the district name on hover", async () => {
    render(<DistrictChoroplethMap />);
    const pathB = await screen.findByLabelText("測試乙區");

    fireEvent.mouseEnter(pathB);
    expect(screen.getAllByText("測試乙區").length).toBeGreaterThan(0);

    fireEvent.mouseLeave(pathB);
  });

  it("renders an inline error state and retries via the reload button", async () => {
    const refetch = vi.fn();
    mockedUseDistrictSummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("模擬行政區資料失敗"),
      refetch,
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<DistrictChoroplethMap />);

    expect(await screen.findByText("模擬行政區資料失敗")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新載入" }));
    expect(refetch).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: 執行測試確認失敗**

```bash
npm run test -- DistrictChoroplethMap
```

Expected: FAIL，找不到模組 `./DistrictChoroplethMap`。

- [ ] **Step 3: 建立 `src/features/home/components/DistrictChoroplethMap.tsx`**

```tsx
import { useEffect, useMemo, useState } from "react";
import { feature } from "topojson-client";
import { geoMercator, geoPath } from "d3-geo";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const TOPOLOGY_URL = "/Map_NewTaipei.json";
const MAP_WIDTH = 760;
const MAP_HEIGHT = 560;

interface DistrictProperties {
  id: string;
  name: string;
}

interface DistrictFeature {
  type: "Feature";
  properties: DistrictProperties;
  geometry: { type: string; coordinates: unknown };
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function opportunityFillColor(opportunityIndex: number | undefined) {
  if (opportunityIndex === undefined) return "#d8e3ee";
  if (opportunityIndex >= 80) return "#0a5aa8";
  if (opportunityIndex >= 70) return "#3b82c8";
  if (opportunityIndex >= 60) return "#7fb0dd";
  if (opportunityIndex >= 50) return "#b9d4ec";
  return "#e3edf7";
}

export default function DistrictChoroplethMap() {
  const [features, setFeatures] = useState<DistrictFeature[]>([]);
  const [topologyState, setTopologyState] = useState<
    "loading" | "ready" | "error"
  >("loading");
  const [topologyError, setTopologyError] = useState<string | null>(null);
  const [hoveredDistrictId, setHoveredDistrictId] = useState<string | null>(
    null,
  );

  const {
    data: districts = [],
    isLoading: isDistrictsLoading,
    isError: isDistrictsError,
    error: districtsError,
    refetch,
  } = useDistrictSummary();

  useEffect(() => {
    const controller = new AbortController();

    async function loadTopology() {
      setTopologyState("loading");
      try {
        const response = await fetch(TOPOLOGY_URL, {
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(`地圖幾何資料請求失敗（HTTP ${response.status}）`);
        }
        const topology = await response.json();
        const mapObject = topology?.objects?.map;
        if (!mapObject) {
          throw new Error("TopoJSON 缺少 objects.map 資料。");
        }
        const collection = feature(topology, mapObject) as unknown as {
          features: DistrictFeature[];
        };
        setFeatures(collection.features ?? []);
        setTopologyState("ready");
      } catch (loadError) {
        if ((loadError as Error).name !== "AbortError") {
          setFeatures([]);
          setTopologyError(
            loadError instanceof Error
              ? loadError.message
              : "地圖幾何資料載入失敗，請稍後再試。",
          );
          setTopologyState("error");
        }
      }
    }

    loadTopology();
    return () => controller.abort();
  }, []);

  const districtById = useMemo(() => {
    return new Map(districts.map((district) => [district.id, district]));
  }, [districts]);

  const collection = useMemo(
    () => ({ type: "FeatureCollection" as const, features }),
    [features],
  );
  const projection = useMemo(
    () => geoMercator().fitSize([MAP_WIDTH, MAP_HEIGHT], collection as never),
    [collection],
  );
  const pathGenerator = useMemo(() => geoPath(projection), [projection]);

  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const selectDistrict = useSelectedDistrict((state) => state.selectDistrict);

  const hoveredDistrict = features.find(
    (item) => item.properties.id === hoveredDistrictId,
  );
  const tooltipPoint = hoveredDistrict
    ? pathGenerator.centroid(hoveredDistrict as never)
    : null;
  const tooltipX = tooltipPoint
    ? clamp(tooltipPoint[0] - 54, 12, MAP_WIDTH - 132)
    : 0;
  const tooltipY = tooltipPoint
    ? clamp(tooltipPoint[1] - 42, 12, MAP_HEIGHT - 48)
    : 0;

  const isLoading = topologyState === "loading" || isDistrictsLoading;
  const isError = topologyState === "error" || isDistrictsError;

  if (isLoading) {
    return (
      <Skeleton
        className="h-[520px] w-full rounded-2xl"
        data-testid="map-skeleton"
      />
    );
  }

  if (isError) {
    const message =
      topologyState === "error"
        ? topologyError ?? "地圖幾何資料載入失敗，請稍後再試。"
        : districtsError instanceof Error
          ? districtsError.message
          : "行政區資料載入失敗，請稍後再試。";

    return (
      <section
        role="alert"
        className="flex min-h-[320px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
        data-testid="map-error"
      >
        <h2 className="text-lg font-bold text-red-700">地圖資料載入失敗</h2>
        <p className="text-sm text-red-600">{message}</p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="map-title"
      className="rounded-2xl border border-slate-200 bg-white p-7 shadow-sm"
    >
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Interactive Map
          </p>
          <h2 id="map-title" className="text-xl font-bold text-slate-900">
            29 區機會指數分布
          </h2>
        </div>
        <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold uppercase text-slate-500">
          Hover / Click
        </span>
      </div>

      <div className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
        <svg
          viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
          role="img"
          aria-label="新北市 29 行政區機會指數互動地圖"
          className="block h-auto w-full"
        >
          <g>
            {features.map((district) => {
              const id = district.properties.id;
              const name = district.properties.name ?? "未命名行政區";
              const opportunityIndex = districtById.get(id)?.opportunityIndex;
              const isSelected = id === selectedDistrictId;
              const isHovered = id === hoveredDistrictId;

              return (
                <path
                  key={id}
                  d={pathGenerator(district as never) ?? undefined}
                  data-town-id={id}
                  aria-label={name}
                  className={cn(
                    "cursor-pointer stroke-white stroke-[1.5] transition-[filter,stroke-width] duration-150",
                    isHovered && "stroke-[3] stroke-amber-500 brightness-95",
                    isSelected && "stroke-[3] stroke-amber-700",
                  )}
                  style={{
                    fill: isSelected
                      ? "#ffad5a"
                      : opportunityFillColor(opportunityIndex),
                  }}
                  onMouseEnter={() => setHoveredDistrictId(id)}
                  onMouseLeave={() => setHoveredDistrictId(null)}
                  onClick={() => selectDistrict(id)}
                >
                  <title>{name}</title>
                </path>
              );
            })}
          </g>
          {hoveredDistrict && tooltipPoint && (
            <g
              pointerEvents="none"
              transform={`translate(${tooltipX} ${tooltipY})`}
            >
              <rect width="132" height="36" rx="9" fill="#10233f" />
              <text
                x="66"
                y="23"
                textAnchor="middle"
                fill="#ffffff"
                fontSize="14"
                fontWeight="700"
              >
                {hoveredDistrict.properties.name}
              </text>
            </g>
          )}
        </svg>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: 刪除舊的 `src/components/TownMap.tsx`**

`HomePage.tsx` 在 Task 12 才會停止引用 `TownMap`，因此本步驟先保留刪除
動作到 Task 12 執行（此處不刪除，避免 Task 12 之前建置失敗）。跳過本步驟。

- [ ] **Step 5: 執行測試確認通過**

```bash
npm run test -- DistrictChoroplethMap
```

Expected: 3 個測試全數 PASS。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/home/components/DistrictChoroplethMap.tsx frontend/src/features/home/components/DistrictChoroplethMap.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): migrate TownMap to DistrictChoroplethMap with opportunity-index coloring

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 11: `KpiSummaryRow` 元件

**Files:**
- Create: `frontend/src/features/home/components/KpiSummaryRow.tsx`
- Create: `frontend/src/features/home/components/KpiSummaryRow.test.tsx`

**Interfaces:**
- Consumes: `useDistrictSummary`（Task 9）。
- Consumes: `Card`、`CardHeader`、`CardTitle`、`CardContent`、`Skeleton`、
  `Badge`、`Button`（Task 5）。
- Produces: `KpiSummaryRow`（no props，
  `@/features/home/components/KpiSummaryRow`），Task 12 的 `HomePage`
  直接引用。

- [ ] **Step 1: 安裝依賴**

```bash
cd frontend
npm install motion
```

- [ ] **Step 2: 先寫失敗測試**

```tsx
// src/features/home/components/KpiSummaryRow.test.tsx
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import KpiSummaryRow from "./KpiSummaryRow";
import { useDistrictSummary } from "../hooks/useDistrictSummary";

vi.mock("../hooks/useDistrictSummary");
const mockedUseDistrictSummary = vi.mocked(useDistrictSummary);

const SAMPLE_DISTRICTS = [
  {
    id: "A",
    name: "甲",
    youthPopulation: 1000,
    opportunityIndex: 80,
    retentionRiskLevel: "low" as const,
    youthParticipationIndex: 60,
    fertilityRate: 40,
    policySupportScore: 70,
  },
  {
    id: "B",
    name: "乙",
    youthPopulation: 2000,
    opportunityIndex: 60,
    retentionRiskLevel: "high" as const,
    youthParticipationIndex: 50,
    fertilityRate: 42,
    policySupportScore: 55,
  },
  {
    id: "C",
    name: "丙",
    youthPopulation: 1500,
    opportunityIndex: 70,
    retentionRiskLevel: "high" as const,
    youthParticipationIndex: 55,
    fertilityRate: 41,
    policySupportScore: 60,
  },
];

describe("KpiSummaryRow", () => {
  it("renders skeleton placeholders while loading", () => {
    mockedUseDistrictSummary.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<KpiSummaryRow />);
    expect(screen.getByTestId("kpi-skeleton")).toBeInTheDocument();
  });

  it("renders an inline error state with a working reload button", () => {
    const refetch = vi.fn();
    mockedUseDistrictSummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("模擬 KPI 資料失敗"),
      refetch,
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<KpiSummaryRow />);
    expect(screen.getByText("模擬 KPI 資料失敗")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新載入" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("renders aggregated KPI values and the most common retention risk level", () => {
    mockedUseDistrictSummary.mockReturnValue({
      data: SAMPLE_DISTRICTS,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<KpiSummaryRow />);
    expect(screen.getByText("新北市青年人口 4,500 人")).toBeInTheDocument();
    expect(screen.getByText("高風險")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: 執行測試確認失敗**

```bash
npm run test -- KpiSummaryRow
```

Expected: FAIL，找不到模組 `./KpiSummaryRow`。

- [ ] **Step 4: 建立 `src/features/home/components/KpiSummaryRow.tsx`**

```tsx
import { motion } from "motion/react";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { DistrictSummary, RetentionRiskLevel } from "@/types/district";

const NATIONAL_YOUTH_POPULATION = 4_820_000;
const NATIONAL_YOUTH_POPULATION_SHARE = 20.6;
const CITY_YOUTH_POPULATION_SHARE = 28.4;
const YOUTH_POPULATION_YOY = -1.2;

const RISK_LABEL: Record<RetentionRiskLevel, string> = {
  low: "低風險",
  medium: "中風險",
  high: "高風險",
};

function averageRetentionRisk(
  districts: DistrictSummary[],
): RetentionRiskLevel {
  const counts: Record<RetentionRiskLevel, number> = {
    low: 0,
    medium: 0,
    high: 0,
  };
  districts.forEach((district) => {
    counts[district.retentionRiskLevel] += 1;
  });

  return (Object.keys(counts) as RetentionRiskLevel[]).reduce(
    (mostCommon, level) =>
      counts[level] > counts[mostCommon] ? level : mostCommon,
    "low" as RetentionRiskLevel,
  );
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("zh-Hant-TW").format(Math.round(value));
}

export default function KpiSummaryRow() {
  const {
    data: districts = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useDistrictSummary();

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="kpi-skeleton"
      >
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-32 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    const message =
      error instanceof Error ? error.message : "青年 KPI 資料載入失敗，請稍後再試。";

    return (
      <section
        role="alert"
        className="flex min-h-[140px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
        data-testid="kpi-error"
      >
        <h2 className="text-lg font-bold text-red-700">KPI 資料載入失敗</h2>
        <p className="text-sm text-red-600">{message}</p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  const cityYouthPopulation = districts.reduce(
    (total, district) => total + district.youthPopulation,
    0,
  );
  const riskLevel = averageRetentionRisk(districts);

  const kpis = [
    {
      label: "全台 18–35 歲青年人口",
      value: `${formatNumber(NATIONAL_YOUTH_POPULATION)} 人`,
      detail: `全台佔比 ${NATIONAL_YOUTH_POPULATION_SHARE}%`,
    },
    {
      label: "新北市青年佔總人口比例",
      value: `${CITY_YOUTH_POPULATION_SHARE}%`,
      detail: `新北市青年人口 ${formatNumber(cityYouthPopulation)} 人`,
    },
    {
      label: "青年人口年增率 (YoY)",
      value: `${YOUTH_POPULATION_YOY > 0 ? "+" : ""}${YOUTH_POPULATION_YOY}%`,
      detail: "較去年同期",
    },
  ];

  return (
    <div
      className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      data-testid="kpi-success"
    >
      {kpis.map((kpi, index) => (
        <motion.div
          key={kpi.label}
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: index * 0.08, duration: 0.35 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-semibold text-accent-slate">
                {kpi.label}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-bold text-slate-900">{kpi.value}</p>
              <p className="mt-1 text-xs text-slate-500">{kpi.detail}</p>
            </CardContent>
          </Card>
        </motion.div>
      ))}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.24, duration: 0.35 }}
      >
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold text-accent-slate">
              平均留才風險等級
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant={riskLevel}>{RISK_LABEL[riskLevel]}</Badge>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}
```

- [ ] **Step 5: 執行測試確認通過**

```bash
npm run test -- KpiSummaryRow
```

Expected: 3 個測試全數 PASS。

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/features/home/components/KpiSummaryRow.tsx frontend/src/features/home/components/KpiSummaryRow.test.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): add KpiSummaryRow with animated aggregated youth KPIs

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 12: `SectionEntryCards` + `HomePage` 最終組裝與 Error Boundary

**Files:**
- Create: `frontend/src/features/home/components/SectionEntryCards.tsx`
- Create: `frontend/src/components/shared/SectionErrorFallback.tsx`
- Modify: `frontend/src/features/home/HomePage.tsx`
- Modify: `frontend/src/styles.css`（移除已不再被任何元件使用的舊
  `.app-shell` / `.map-card` / `.town-*` / `.state-panel` 等規則）
- Delete: `frontend/src/components/TownMap.tsx`

**Interfaces:**
- Consumes: `useDistrictSummary`（Task 9）、`DistrictChoroplethMap`
  （Task 10）、`KpiSummaryRow`（Task 11）、`Card`/`CardHeader`/`CardTitle`/
  `CardContent`/`Skeleton`（Task 5）。
- Produces: `HomePage`（`@/features/home/HomePage`）最終版本，供
  `@/app/routes` 的 `/` 路由使用（路由本身已在 Task 8 接好，本任務只換
  `HomePage.tsx` 內容）。

- [ ] **Step 1: 先寫 `SectionEntryCards` 的用法（無獨立單元測試，涵蓋於
  下方 `HomePage` 整合驗證，符合規格第 9 節列出的測試範圍）**

- [ ] **Step 2: 建立 `src/features/home/components/SectionEntryCards.tsx`**

```tsx
import { Link } from "react-router-dom";
import { Briefcase, Vote, Baby, Sparkles } from "lucide-react";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import type { DistrictSummary } from "@/types/district";

function average(
  districts: DistrictSummary[],
  selector: (district: DistrictSummary) => number,
) {
  if (districts.length === 0) return 0;
  return (
    districts.reduce((total, district) => total + selector(district), 0) /
    districts.length
  );
}

const SECTIONS = [
  {
    key: "employment",
    title: "青年就業",
    to: "/employment",
    metricLabel: "平均機會指數",
    icon: Briefcase,
    selector: (district: DistrictSummary) => district.opportunityIndex,
    format: (value: number) => value.toFixed(1),
  },
  {
    key: "politics",
    title: "青年參政",
    to: "/politics",
    metricLabel: "平均參政指數",
    icon: Vote,
    selector: (district: DistrictSummary) => district.youthParticipationIndex,
    format: (value: number) => value.toFixed(1),
  },
  {
    key: "fertility",
    title: "青年生育",
    to: "/fertility",
    metricLabel: "平均生育率",
    icon: Baby,
    selector: (district: DistrictSummary) => district.fertilityRate,
    format: (value: number) => `${value.toFixed(1)}‰`,
  },
  {
    key: "policy-support",
    title: "施政協助",
    to: "/policy-support",
    metricLabel: "政策支持度分數",
    icon: Sparkles,
    selector: (district: DistrictSummary) => district.policySupportScore,
    format: (value: number) => value.toFixed(1),
  },
] as const;

export default function SectionEntryCards() {
  const {
    data: districts = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useDistrictSummary();

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
        data-testid="entry-cards-skeleton"
      >
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-28 w-full rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    const message =
      error instanceof Error
        ? error.message
        : "板塊入口資料載入失敗，請稍後再試。";

    return (
      <section
        role="alert"
        className="flex min-h-[140px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
        data-testid="entry-cards-error"
      >
        <h2 className="text-lg font-bold text-red-700">板塊入口資料載入失敗</h2>
        <p className="text-sm text-red-600">{message}</p>
        <Button variant="destructive" onClick={() => refetch()}>
          重新載入
        </Button>
      </section>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {SECTIONS.map((section) => {
        const value = average(districts, section.selector);
        const Icon = section.icon;
        return (
          <Link key={section.key} to={section.to} className="block">
            <Card className="h-full transition-shadow hover:shadow-md">
              <CardHeader className="flex-row items-center justify-between space-y-0">
                <CardTitle className="text-base font-bold text-slate-900">
                  {section.title}
                </CardTitle>
                <Icon className="h-5 w-5 text-primary" aria-hidden="true" />
              </CardHeader>
              <CardContent>
                <p className="text-xs font-semibold uppercase tracking-wide text-accent-slate">
                  {section.metricLabel}
                </p>
                <p className="mt-1 text-xl font-bold text-primary">
                  {section.format(value)}
                </p>
              </CardContent>
            </Card>
          </Link>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: 安裝 `lucide-react`**

```bash
cd frontend
npm install lucide-react react-error-boundary
```

- [ ] **Step 4: 建立 `src/components/shared/SectionErrorFallback.tsx`**

```tsx
import type { FallbackProps } from "react-error-boundary";
import { Button } from "@/components/ui/button";

export default function SectionErrorFallback({
  error,
  resetErrorBoundary,
}: FallbackProps) {
  const message =
    error instanceof Error ? error.message : "區塊發生未預期的錯誤。";

  return (
    <section
      role="alert"
      className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
    >
      <h2 className="text-lg font-bold text-red-700">區塊發生未預期的錯誤</h2>
      <p className="text-sm text-red-600">{message}</p>
      <Button variant="destructive" onClick={resetErrorBoundary}>
        重新載入
      </Button>
    </section>
  );
}
```

- [ ] **Step 5: 改寫 `src/features/home/HomePage.tsx`**

```tsx
import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import DistrictChoroplethMap from "./components/DistrictChoroplethMap";
import KpiSummaryRow from "./components/KpiSummaryRow";
import SectionEntryCards from "./components/SectionEntryCards";
import SectionErrorFallback from "@/components/shared/SectionErrorFallback";

export default function HomePage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-8 px-6 py-10">
      <header>
        <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          NEW TAIPEI · YOUTH OPPORTUNITY MAP
        </p>
        <h1 className="text-3xl font-bold text-slate-900 md:text-4xl">
          新北青年機會地圖
        </h1>
      </header>

      <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
        <KpiSummaryRow />
      </ErrorBoundary>

      <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
        <DistrictChoroplethMap />
      </ErrorBoundary>

      <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
        <SectionEntryCards />
      </ErrorBoundary>
    </main>
  );
}
```

- [ ] **Step 6: 刪除不再使用的 `src/components/TownMap.tsx`**

`HomePage.tsx` 已不再引用 `TownMap`（改用 `DistrictChoroplethMap`），可
安全刪除。

- [ ] **Step 7: 清理 `src/styles.css`**

刪除 `.app-shell`、`.page-header`、`.eyebrow`、`.page-subtitle`、
`.data-badge*`、`.map-card*`、`.card-heading*`、`.card-hint`、
`.list-count`、`.map-stage`、`.town-map`、`.town-path*`、`.map-tooltip*`、
`.map-legend*`、`.state-panel*`、`.state-icon`、`.loader`、`.button*`、
`@keyframes spin` 與相關 `@media` 區塊（這些全是舊 `App.jsx`/`TownMap.jsx`
專用的手刻樣式，新元件已全面改用 Tailwind class）。保留檔案最上方的
`@tailwind base/components/utilities` 三行。

- [ ] **Step 8: 執行全部測試與建置**

```bash
npm run test
npm run build
npm run lint
```

Expected: 全部測試 PASS，建置與 lint 皆無錯誤。

- [ ] **Step 9: 手動驗證**

```bash
npm run dev
```

開啟瀏覽器檢查 `/`：
- 顯示 4 張 KPI 卡（含動畫進場）、29 區 choropleth 地圖、4 張板塊入口卡。
- 地圖 hover 顯示 tooltip、click 後該區邊框變色（選取樣式）。
- 點擊任一入口卡導向對應 placeholder 路由。

- [ ] **Step 10: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/features/home/HomePage.tsx frontend/src/features/home/components/SectionEntryCards.tsx frontend/src/components/shared/SectionErrorFallback.tsx frontend/src/styles.css
git rm frontend/src/components/TownMap.tsx
git commit -m "$(cat <<'EOF'
feat(frontend): compose HomePage from data-driven sections with error boundaries

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01FU5DYdoytxohARNVEdUXgb
EOF
)"
```

---

## Task 13: 最終驗收（含錯誤隔離手動驗證）

**Files:**
- No new files. This task only runs verification commands and a temporary,
  reverted manual edit to `frontend/src/data/districts.ts`.

**Interfaces:**
- Consumes: 所有先前任務的最終產出。No new interfaces produced.

- [ ] **Step 1: 全量建置**

```bash
cd frontend
npm run build
```

Expected: 對應規格驗收條件 1、6 —— 無型別錯誤，建置成功產生 `dist/`。

- [ ] **Step 2: 全量測試**

```bash
npm run test
```

Expected: 對應規格驗收條件 7 —— 第 9 節列出的所有單元／元件測試（
`districts.test.ts`、`useSelectedDistrict.test.ts`、
`useDistrictSummary.test.tsx`、`DistrictChoroplethMap.test.tsx`、
`KpiSummaryRow.test.tsx`、`button.test.tsx`）全數 PASS。

- [ ] **Step 3: 全量 lint**

```bash
npm run lint
```

Expected: 零錯誤。

- [ ] **Step 4: 手動驗證錯誤隔離（規格驗收條件 5）**

暫時修改 `frontend/src/data/districts.ts` 的 `fetchDistrictSummaries`，
在函式最開頭加入：

```ts
export async function fetchDistrictSummaries(): Promise<DistrictSummary[]> {
  return Promise.reject(new Error("手動測試：模擬資料來源失敗"));
  // 以下原本程式碼暫時不會執行
  ...
}
```

執行 `npm run dev`，開啟瀏覽器檢查 `/`：
- KPI 區塊顯示「KPI 資料載入失敗」與「重新載入」按鈕。
- 地圖區塊顯示「地圖資料載入失敗」與「重新載入」按鈕。
- 板塊入口卡區塊顯示「板塊入口資料載入失敗」與「重新載入」按鈕。
- 三個區塊互不影響（沒有任何一個區塊拖累其他兩個區塊，也沒有整頁白屏）。

確認後**還原**這次修改（`git checkout -- frontend/src/data/districts.ts`
或手動刪除剛加的那一行）。

- [ ] **Step 5: 手動驗證路由與版面（規格驗收條件 2、3、4、8）**

```bash
npm run dev
```

在桌面寬度視窗下檢查：
- 導覽列可切換 5 個路由，②～⑤ 顯示「規劃中」placeholder，無路由錯誤、
  無 console 錯誤。
- 首頁載入 fixture 後顯示 29 區地圖、4 張 KPI 卡、4 張入口卡，版面在
  `max-w-[1440px]` 容器內置中，卡片排列符合 `grid` 響應式設定。
- 地圖 hover 顯示名稱 tooltip 與 hover 邊框樣式；click 後邊框轉為選取
  樣式，且再次 hover 其他區不影響已選取區的樣式。
- 重新整理頁面觀察初次載入的 `Skeleton` 呈現（可用瀏覽器 devtools 節流
  網路速度以利觀察）。

- [ ] **Step 6: 確認 `git status` 乾淨**

```bash
git status
```

Expected: 除了 Step 4 已還原的檔案外，無其他未預期的變更。若一切正常，
本任務不需要額外 commit（純驗證，無程式碼變更）。
