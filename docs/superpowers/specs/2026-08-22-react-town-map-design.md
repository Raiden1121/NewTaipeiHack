# React 行政區地圖前端設計規格

## 1. 目標

建立一個獨立的 React + Vite 前端，讀取現有的
`taiwan-towns-65000.topo.json`，將其中 `map` 物件的 29 個行政區 Polygon
顯示成可互動的 SVG 地圖。

前端不新增後端 API，也不改變現有 `main.py` 的 Python 資料轉換用途。

## 2. 核准方案

採用 React + Vite + D3.js + `topojson-client`：

- React 管理載入狀態、目前選取的行政區與元件組合。
- `topojson-client` 將 TopoJSON 的 `objects.map` 轉成 GeoJSON FeatureCollection。
- D3 的 `geoPath` 將行政區幾何資料投影成 SVG path。
- 不使用 Leaflet、地圖圖磚或外部地圖 API。

## 3. 專案結構

```text
frontend/
├── package.json
├── vite.config.js
├── index.html
├── public/
│   └── taiwan-towns-65000.topo.json
└── src/
    ├── main.jsx
    ├── App.jsx
    ├── components/
    │   └── TownMap.jsx
    └── styles.css
```

原始 TopoJSON 保留在專案根目錄；`frontend/public/` 的檔案是前端可直接
載入的展示資產，兩者內容一致。

## 4. 資料契約與資料流

目前資料格式：

- 根節點 `type`: `Topology`
- 根節點 `objects.map.type`: `GeometryCollection`
- `objects.map.geometries`: 29 筆 Polygon
- 每筆 properties 至少包含 `id` 與 `name`

資料流如下：

```text
/taiwan-towns-65000.topo.json
    → fetch()
    → topojson.feature(topology, topology.objects.map)
    → FeatureCollection
    → TownMap 的 D3 geoPath
    → SVG path
```

每個行政區以 `properties.id` 作為穩定識別值，以 `properties.name` 作為
顯示名稱與清單排序欄位。載入失敗時顯示可理解的錯誤訊息，不讓整個畫面
無限停留在載入狀態。

## 5. 元件責任

### `App.jsx`

- 載入 TopoJSON。
- 管理 `loading`、`error`、`features` 與 `selectedTownId`。
- 將選取事件傳給地圖元件。
- 組合頁首與全寬地圖區。

### `TownMap.jsx`

- 接收行政區 FeatureCollection 與目前選取的 id。
- 使用 D3 `geoMercator` 或等價投影配合 `fitSize` 自動適應容器。
- 產生 SVG 行政區 path。
- 處理 hover、leave、click，並以 className 表示 hover/selected 狀態。

## 6. UI 狀態與互動

- 初始：顯示載入提示。
- 載入失敗：顯示錯誤訊息與重新載入按鈕。
- 載入成功但沒有資料：顯示沒有行政區資料。
- 載入成功：顯示全寬 SVG 地圖。
- 滑鼠移入：顯示行政區名稱 tooltip 或標籤，並突出 Polygon。
- 點擊 Polygon：更新地圖上的 selected Polygon。

版面優先支援桌面寬度，窄螢幕時維持地圖單欄排列。

## 7. 執行方式

```bash
cd frontend
npm install
npm run dev
```

正式建置使用：

```bash
cd frontend
npm run build
npm run preview
```

## 8. 範圍外事項

- 不建立測試檔或測試套件。
- 不建立 FastAPI API。
- 不加入底圖、縮放控制、地理編碼或路線功能。
- 不加入登入、資料庫或部署設定。

## 9. 驗收條件

1. `npm run dev` 能啟動 React 開發伺服器。
2. 頁面能成功載入 29 個行政區 Polygon。
3. 地圖能顯示 29 個行政區 Polygon。
4. 點擊或 hover 地圖區域後，能顯示名稱並更新 selected 狀態。
5. `npm run build` 成功產生正式建置檔案。
6. 使用瀏覽器實際檢查載入、hover、click、錯誤狀態與窄螢幕排列。
