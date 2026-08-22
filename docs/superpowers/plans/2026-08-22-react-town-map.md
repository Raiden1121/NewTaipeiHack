# React Town Map Implementation Plan

> **For agentic workers:** This plan is executed inline in the current session. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個 React + Vite 前端，將現有 29 個行政區 TopoJSON 顯示成可互動的 SVG 地圖。

**Architecture:** `App` 負責資料載入與選取狀態；`TownMap` 負責 D3 投影與 SVG path；`TownList` 與 `TownInfo` 負責清單互動及選取資訊。TopoJSON 會放在 Vite 的 `public` 資產目錄，由瀏覽器 fetch 後用 `topojson-client` 轉成 GeoJSON。

**Tech Stack:** React 18, Vite, D3-geo, topojson-client, plain CSS。

**Spec:** `docs/superpowers/specs/2026-08-22-react-town-map-design.md`

## Global Constraints

- 不建立測試檔或測試套件；使用 `npm run build` 與瀏覽器手動驗證。
- 不建立後端 API；前端直接載入 `public/taiwan-towns-65000.topo.json`。
- 使用 `objects.map`，其資料是 29 筆 Polygon，properties 至少包含 `id` 與 `name`。
- `properties.id` 是穩定識別值，`properties.name` 用於清單與資訊顯示。
- 不加入 Leaflet、地圖圖磚、登入、資料庫或部署設定。

### Task 1: Scaffold the Vite React application

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/App.jsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/public/taiwan-towns-65000.topo.json`

**Interfaces:**
- Produces a Vite entrypoint at `frontend/src/main.jsx` and a browser-loadable JSON asset at `/taiwan-towns-65000.topo.json`.

- [ ] **Step 1: Create the package manifest**

  Define scripts and runtime dependencies:

  ```json
  {
    "private": true,
    "scripts": {
      "dev": "vite",
      "build": "vite build",
      "preview": "vite preview"
    },
    "dependencies": {
      "d3-geo": "^3.1.1",
      "react": "^18.3.1",
      "react-dom": "^18.3.1",
      "topojson-client": "^3.1.0"
    },
    "devDependencies": {
      "@vitejs/plugin-react": "^4.3.1",
      "vite": "^5.4.8"
    }
  }
  ```

- [ ] **Step 2: Add the Vite configuration and HTML entrypoint**

  Configure the React plugin in `vite.config.js`, and set `index.html` to mount `<div id="root"></div>` with `/src/main.jsx` as a module entry.

- [ ] **Step 3: Add the React entrypoint and initial app shell**

  `main.jsx` imports React, `createRoot`, `App`, and `styles.css`, then renders `<App />` into `#root`. `App.jsx` initially renders the page shell so later tasks can add child components without changing the entrypoint contract.

- [ ] **Step 4: Copy the source TopoJSON into the Vite public asset directory**

  Copy `taiwan-towns-65000.topo.json` to `frontend/public/taiwan-towns-65000.topo.json` without changing its contents, so `fetch('/taiwan-towns-65000.topo.json')` works in both dev and preview servers.

- [ ] **Step 5: Install dependencies**

  Run `cd frontend && npm install` and confirm `package-lock.json` is generated. Do not add test dependencies.

### Task 2: Implement data loading and selection state

**Files:**
- Modify: `frontend/src/App.jsx`
- Create: `frontend/src/components/TownInfo.jsx`

**Interfaces:**
- `App` passes `features`, `selectedTownId`, and `onSelectTown` to map/list components.
- `TownInfo({ town })` renders the selected feature's `properties.name` and `properties.id`, or an empty-state message when `town` is null.

- [ ] **Step 1: Add the loading state model**

  `App` starts with `loading=true`, `error=null`, `features=[]`, and `selectedTownId=null`. A `useEffect` fetches `/taiwan-towns-65000.topo.json`, rejects non-OK responses, converts `topology.objects.map` with `feature(topology, topology.objects.map)`, stores `collection.features`, and selects the first feature only after data exists.

- [ ] **Step 2: Add explicit loading, error, and empty states**

  Render a loading panel while `loading` is true; render the error message plus a reload button when `error` is set; render a no-data panel if loading finished with no features. The reload button increments a `reloadKey` state used by the fetch effect.

- [ ] **Step 3: Derive the selected feature by stable id**

  Compute `selectedTown` with `features.find((town) => town.properties.id === selectedTownId) || null`. Pass `selectedTown` to `TownInfo` and pass `setSelectedTownId` through the event props.

### Task 3: Build the SVG map component

**Files:**
- Create: `frontend/src/components/TownMap.jsx`

**Interfaces:**
- `TownMap({ features, selectedTownId, onSelectTown })` renders an accessible `<svg>` with one `<path>` per feature.

- [ ] **Step 1: Fit a geographic projection to the feature collection**

  Use `geoMercator().fitSize([width, height], { type: 'FeatureCollection', features })` and `geoPath(projection)`. Use a fixed viewBox such as `0 0 760 560`, so the map scales with its responsive container.

- [ ] **Step 2: Render paths with stable keys and properties**

  Render each path with `key={town.properties.id}`, `d={path(town)}`, and `aria-label={town.properties.name}`. Add `data-town-id` for inspection and use `selected`/`hovered` classes for interaction styling.

- [ ] **Step 3: Add hover and click behavior**

  Track `hoveredTownId` locally. Mouse enter updates the hovered id, mouse leave clears it, and click calls `onSelectTown(town.properties.id)`. Render a positioned label for the hovered town using its `properties.name`.

### Task 4: Build the list and information panel

**Files:**
- Create: `frontend/src/components/TownList.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- `TownList({ towns, selectedTownId, onSelectTown })` renders a button per feature and calls `onSelectTown` with its `properties.id`.

- [ ] **Step 1: Sort town features by display name**

  In `TownList`, create a copied array sorted by `properties.name` using `localeCompare('zh-Hant')`, so the incoming feature order is not mutated.

- [ ] **Step 2: Render accessible selection buttons**

  Use `<button type="button">` for every town, add `aria-pressed={isSelected}`, and include the town name plus a short id label. Apply an `is-selected` class to the selected item.

- [ ] **Step 3: Compose the desktop and mobile layout**

  Update `App` to render the map in the main panel and `TownList` plus `TownInfo` in the side panel. Add a page header describing that the data comes from the supplied Taiwan town TopoJSON.

### Task 5: Add visual styling and verify the frontend

**Files:**
- Modify: `frontend/src/styles.css`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/TownMap.jsx`

- [ ] **Step 1: Style the page shell and responsive layout**

  Add a dark navy page background, light cards, a two-column desktop grid, and a single-column layout below `900px`. Ensure the map panel has a minimum height and the list can scroll without expanding the page indefinitely.

- [ ] **Step 2: Style map, hover, selected, tooltip, and state panels**

  Give paths a visible fill and border, increase opacity and stroke for hover, use a distinct accent for selected, and style loading/error/empty panels consistently. Keep text contrast readable on both light cards and the dark page background.

- [ ] **Step 3: Build the production bundle**

  Run `cd frontend && npm run build`. Confirm Vite exits with code 0 and creates `frontend/dist/`.

- [ ] **Step 4: Run the dev server for browser verification**

  Run `cd frontend && npm run dev -- --host 127.0.0.1`, open the printed local URL, and manually confirm: 29 paths render, town names appear in the list, hover changes the path and tooltip, map/list clicks synchronize the selected info, the reload error state is reachable when the JSON URL is unavailable, and the layout stacks below 900px.

## Verification Summary

Run these commands after implementation:

```bash
cd frontend
npm run build
npm run dev -- --host 127.0.0.1
```

Use the browser for visual verification. No automated tests are added per the user's instruction.
