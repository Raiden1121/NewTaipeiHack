# Collector 資料說明

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
```

API 金鑰請設定 `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`，或直接傳入 `client_id`、`client_secret`。也可以傳入既有 `access_token`。

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

v2 的資料 endpoint 回傳陣列；v3 回傳 `Items` 陣列。point-in-polygon 與站點密度計算交由後續 transform 處理。

### 3. 前 5 筆資料

目前工作區未設定 TDX API 金鑰，因此尚未取得 TDX live 前 5 筆；設定金鑰後可用以下程式輸出：

```python
import json

print(json.dumps(records[:5], ensure_ascii=False, indent=2))
```

輸出的站點資料會包含 `StopUID`、`StopID`、`StopName`、`StopPosition` 與 `Operators`。
