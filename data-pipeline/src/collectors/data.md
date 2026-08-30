# Collector 資料說明

## TDX REST API 金鑰設定

將 `data-pipeline/src/collectors/.env.example` 複製成同一資料夾下的 `.env`，填入：

```text
TDX_CLIENT_ID=你的資料存取Client Id
TDX_CLIENT_SECRET=你的資料存取Client Secret
```

`bus_stop.py`、`railway_stop.py` 與 `bike_stop.py` 會自動讀取這兩個欄位；`.env` 不要提交到 Git。

三個 collector 可共用同一個 `TdxClient`。client 會快取 access token，並在每次 HTTP request 間隔至少 13 秒，符合目前每金鑰 5 次／分的限制。開發取樣可使用 `max_records=5`，不需要的附加 endpoint 則關閉。

## 1. population_collector.py

### 1. 怎麼 call API

```python
from collectors.population_collector import fetch_population

# 新北市 29 區
records = fetch_population("11507")

# 全台
records = fetch_population("11507", county=None)
```

API：

```text
https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/{yyyymm}
```

`yyyymm` 為必填的民國年月，例如 `11507`。預設帶入 `COUNTY=新北市`；`county=None` 時省略縣市篩選，抓取全台資料。collector 會自動處理分頁。

### 2. API 回傳格式

API 回傳 envelope，collector 最後只回傳 `responseData`：

```json
{
  "responseCode": "OD-0101-S",
  "totalPage": "1",
  "responseData": [
    {
      "statistic_yyymm": "11507",
      "district_code": "65000010001",
      "site_id": "新北市板橋區",
      "village": "留侯里",
      "household_no": "733",
      "people_total": "1613",
      "people_age_018_m": "3",
      "people_age_018_f": "7"
    }
  ]
}
```

人口數與單一年齡欄位原始值為字串；18–35 歲彙總交由 transform 處理。

### 3. 前 5 筆資料

以下為 `fetch_population("11507")` 的前 5 筆：

| 統計年月 | 區域代碼 | 行政區 | 村里 | 戶數 | 人口數 | 18 歲男 | 18 歲女 |
|---|---|---|---|---:|---:|---:|---:|
| 11507 | 65000010001 | 新北市板橋區 | 留侯里 | 733 | 1613 | 3 | 7 |
| 11507 | 65000010002 | 新北市板橋區 | 流芳里 | 657 | 1430 | 2 | 5 |
| 11507 | 65000010003 | 新北市板橋區 | 赤松里 | 538 | 1083 | 6 | 1 |
| 11507 | 65000010004 | 新北市板橋區 | 黃石里 | 551 | 1267 | 2 | 5 |
| 11507 | 65000010005 | 新北市板橋區 | 挹秀里 | 875 | 1911 | 9 | 8 |

## 2. moving_in.py

### 1. 怎麼 call API

```python
from collectors.moving_in import fetch_moving

records = fetch_moving("11507")
records = fetch_moving("11507", town="板橋區")
```

API：

```text
https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP011/{yyyymm}
```

預設查詢新北市，指定 `town` 時再加入鄉鎮市區篩選；collector 會自動處理分頁。

### 2. API 回傳格式

API 回傳 envelope，collector 最後只回傳合併後的 `responseData`：

```json
{
  "responseCode": "OD-0101-S",
  "totalPage": "1",
  "responseData": [
    {
      "statistic_yyymm": "11507",
      "district_code": "65000010001",
      "site_id": "新北市板橋區",
      "village": "留侯里",
      "in_total_m": "2",
      "in_total_f": "0",
      "out_total_m": "5",
      "out_total_f": "3",
      "in_tp_m": "1",
      "out_tp_m": "2"
    }
  ]
}
```

遷入、遷出與來源／去向欄位原始值為字串；區級加總交由 transform 依 `site_id` 處理。

### 3. 前 5 筆資料

以下為 `fetch_moving("11507")` 的前 5 筆：

| 統計年月 | 區域代碼 | 行政區 | 村里 | 遷入男 | 遷入女 | 遷出男 | 遷出女 | 來自臺北市男 | 遷往臺北市男 |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| 11507 | 65000010001 | 新北市板橋區 | 留侯里 | 2 | 0 | 5 | 3 | 1 | 2 |
| 11507 | 65000010002 | 新北市板橋區 | 流芳里 | 1 | 0 | 1 | 3 | 0 | 0 |
| 11507 | 65000010003 | 新北市板橋區 | 赤松里 | 0 | 0 | 3 | 4 | 0 | 0 |
| 11507 | 65000010004 | 新北市板橋區 | 黃石里 | 0 | 0 | 5 | 1 | 0 | 0 |
| 11507 | 65000010005 | 新北市板橋區 | 挹秀里 | 7 | 7 | 2 | 3 | 1 | 1 |

## 3. bus_stop.py

### 1. 怎麼 call API

```python
from collectors.bus_stop import fetch_bus_stops

# 預設使用 v2、新北市
records = fetch_bus_stops()

# 使用 v3
records = fetch_bus_stops(version="v3")

# 只取前 5 個站點，不呼叫 StopOfRoute
records = fetch_bus_stops(max_records=5, include_operators=False)
```

API 金鑰會自動從 `data-pipeline/src/collectors/.env` 讀取，也可直接傳入 `client_id`、`client_secret` 或既有 `access_token`。

collector 會呼叫：

```text
https://tdx.transportdata.tw/api/basic/{version}/Bus/Stop/City/NewTaipei
https://tdx.transportdata.tw/api/basic/{version}/Bus/StopOfRoute/City/NewTaipei
```

### 2. API 回傳格式

`Stop` 提供站點資料；`StopOfRoute` 提供路線與 `Operators`。collector 會依 `StopUID` 合併業者：

```json
{
  "StopUID": "NWT...",
  "StopID": "...",
  "StopName": {
    "Zh_tw": "站牌名稱",
    "En": "Stop name"
  },
  "StopPosition": {
    "PositionLat": 25.000000,
    "PositionLon": 121.000000
  },
  "Operators": [
    {
      "OperatorCode": "...",
      "OperatorNo": "...",
      "OperatorName": {
        "Zh_tw": "客運業者"
      }
    }
  ]
}
```

v2 的資料 endpoint 回傳陣列；v3 回傳 `Items` 陣列。`include_operators=False` 時只保留站點原始資料；point-in-polygon 與站點密度計算交由後續 transform 處理。

### 3. 前 5 筆資料

以下為 `fetch_bus_stops(max_records=5, include_operators=False)` 的 live 前 5 筆（2026-08-30）：

| StopUID | StopID | 站名 | 緯度 | 經度 |
|---|---:|---|---:|---:|
| NWT10353 | 10353 | 管理中心 | 25.063771 | 121.457635 |
| NWT10354 | 10354 | 標準廠房 | 25.065040 | 121.456024 |
| NWT10355 | 10355 | 五權三五工路口 | 25.065315 | 121.453673 |
| NWT10356 | 10356 | 勞工活動中心 | 25.06236578 | 121.450092 |
| NWT10357 | 10357 | 工商展覽中心 | 25.065092 | 121.449031 |

這次取樣未呼叫 `StopOfRoute`，因此未附加 `Operators`。

## 4. railway_stop.py

### 1. 怎麼 call API

```python
from collectors.railway_stop import fetch_railway_stops

# 預設：v2、新北市；臺鐵、高鐵、捷運與新北輕軌
records = fetch_railway_stops()

# v3 目前使用臺鐵
records = fetch_railway_stops(version="v3", rail_systems=("TRA",))

# 取樣：只取新北市臺鐵站點，不呼叫 StationOfLine
records = fetch_railway_stops(
    version="v2",
    rail_systems=("TRA",),
    max_records=5,
    include_lines=False,
)
```

API 金鑰會自動從 `data-pipeline/src/collectors/.env` 讀取，也可傳入 `client_id`、`client_secret` 或既有 `access_token`。

v2 會呼叫各運具的 `Station` 與 `StationOfLine`；v3 目前官方 OAS 提供 `TRA`、`AFR`。渡輪不納入本 collector，且 v3 的新北市過濾與 29 區 point-in-polygon 交由 transform 處理。

### 2. API 回傳格式

v2 的站點 API 回傳陣列；v3 回傳 `Stations` 與 `Count` envelope。collector 保留原始 TDX 欄位，並補上：

```json
{
  "StationUID": "TRA-...",
  "StationID": "1001",
  "StationName": {"Zh_tw": "站名"},
  "StationPosition": {
    "PositionLat": 25.01,
    "PositionLon": 121.46
  },
  "rail_system": "TRA",
  "transport_type": "TRA",
  "line_ids": ["TRA-L1"],
  "line_nos": ["1"]
}
```

### 3. 前 5 筆資料

以下為 `fetch_railway_stops(version="v2", rail_systems=("TRA",), max_records=5, include_lines=False)` 的 live 前 5 筆（2026-08-30）：

| StationUID | StationID | 站名 | 行政區 | 緯度 | 經度 |
|---|---:|---|---|---:|---:|
| TRA-0950 | 0950 | 五堵 | 汐止區 | 25.07799 | 121.66758 |
| TRA-0960 | 0960 | 汐止 | 汐止區 | 25.06790 | 121.66113 |
| TRA-0970 | 0970 | 汐科 | 汐止區 | 25.06406 | 121.65233 |
| TRA-1020 | 1020 | 板橋 | 板橋區 | 25.01434 | 121.46377 |
| TRA-1030 | 1030 | 浮洲 | 板橋區 | 25.00419 | 121.44477 |

這次取樣未呼叫 `StationOfLine`，因此 `line_ids`、`line_nos` 為空集合。

## 5. bike_stop.py

### 1. 怎麼 call API

```python
from collectors.bike_stop import fetch_bike_stops

# 預設：新北市靜態站點資料
records = fetch_bike_stops()

# 需要即時可借／可還數量時才呼叫 Availability
records = fetch_bike_stops(include_availability=True)
```

API 金鑰會自動從 `data-pipeline/src/collectors/.env` 讀取。API endpoint 為：

```text
https://tdx.transportdata.tw/api/basic/v2/Bike/Station/City/NewTaipei
https://tdx.transportdata.tw/api/basic/v2/Bike/Availability/City/NewTaipei
```

### 2. API 回傳格式

v2 回傳陣列。collector 保留靜態站點欄位；指定 `include_availability=True` 時，將即時原始資料依 `StationUID` 合併到 `Availability`：

```json
{
  "StationUID": "NWT...",
  "StationID": "001",
  "StationName": {"Zh_tw": "站點名稱"},
  "StationPosition": {
    "PositionLat": 25.01,
    "PositionLon": 121.46
  },
  "BikesCapacity": 30,
  "Availability": {
    "ServiceStatus": 1,
    "AvailableRentBikes": 12,
    "AvailableReturnBikes": 18
  }
}
```

### 3. 前 5 筆資料

以下為 `fetch_bike_stops(max_records=5)` 的 live 前 5 筆靜態站點資料（2026-08-30）：

| StationUID | StationID | 站名 | 緯度 | 經度 | 容量 | ServiceType | UpdateTime |
|---|---:|---|---:|---:|---:|---:|---|
| NWT500201001 | 500201001 | YouBike2.0_下庄市場 | 25.14678 | 121.39990 | 20 | 2 | 2026-08-30T13:08:36+08:00 |
| NWT500201002 | 500201002 | YouBike2.0_八里行政中心 | 25.15397 | 121.40721 | 20 | 2 | 2026-08-30T13:08:36+08:00 |
| NWT500201003 | 500201003 | YouBike2.0_八里中庄市場綜合大樓 | 25.15993 | 121.41407 | 28 | 2 | 2026-08-30T13:08:36+08:00 |
| NWT500201004 | 500201004 | YouBike2.0_大崁國小 | 25.16064 | 121.41938 | 20 | 2 | 2026-08-30T13:08:36+08:00 |
| NWT500201006 | 500201006 | YouBike2.0_龍形停車場 | 25.13041 | 121.45130 | 40 | 2 | 2026-08-30T13:08:36+08:00 |

這次未設定 `include_availability=True`，因此未呼叫即時可借／可還資料 endpoint。
