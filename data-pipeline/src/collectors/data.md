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

## 6. college_major.py

### 1. 怎麼 call API

```python
from collectors.college_major import fetch_college_majors

# 預設抓 9621，且只保留學校所在地為新北市的資料
records = fetch_college_majors()

# 指定學年度；county=None 時抓全台
records = fetch_college_majors(academic_year="114", county=None)

# 改抓 9622 的性別／年級學生明細；不會在 collector 內合併
detail_records = fetch_college_majors(include_student_detail=True)
```

資料資源為教育部公開 JSON，無需 TDX 金鑰：

```text
https://stats.moe.gov.tw/files/opendata/sdata.json
https://stats.moe.gov.tw/files/opendata/students.json
```

### 2. API 回傳格式

兩個 endpoint 都回傳 JSON 陣列，collector 保留教育部原始字串欄位。
9621 主要使用 `學生數`；9622 主要使用 `總計`、`男生計`、`女生計`、年級與延修生欄位。

```json
{
  "學年度": "114",
  "學校代碼": "0017",
  "學校名稱": "國立臺北大學",
  "科系代碼": "220201",
  "科系名稱": "(中)國(語)文學系",
  "日間∕進修別": "D 日",
  "等級別": "B 學士",
  "學生數": "207",
  "縣市名稱": "01 新北市",
  "體系別": "1 一般"
}
```

### 3. 前 5 筆資料

以下為 `fetch_college_majors()` 目前 live 前 5 筆（2026-08-30）：

| 學年度 | 學校 | 科系 | 日間／進修 | 等級 | 學生數 | 縣市 |
|---|---|---|---|---|---:|---|
| 103 | 國立臺北大學 | (中)國(語)文學系 | D 日 | M 碩士 | 12 | 01 新北市 |
| 103 | 國立臺北大學 | (中)國(語)文學系 | D 日 | B 學士 | 207 | 01 新北市 |
| 103 | 國立臺北大學 | 應用外語系 | D 日 | B 學士 | 228 | 01 新北市 |
| 103 | 國立臺北大學 | (歷)史學系 | D 日 | M 碩士 | 17 | 01 新北市 |
| 103 | 國立臺北大學 | (歷)史學系 | D 日 | B 學士 | 199 | 01 新北市 |

### 4. 9621 與 9622 的合併方式

collector 只分別取得兩份原始資料；需要性別／年級欄位時，在 transform 執行：

1. 將學校代碼、科系代碼去除前導零。
2. 以以下欄位作為合併鍵：`學年度`、`學校代碼`、`科系代碼`、`日間∕進修別`、`等級別`、`縣市名稱`、`體系別`。
3. 先將 9622 同一合併鍵的多筆資料加總，例如 `總計`、`男生計`、`女生計` 與各年級人數。
4. 以 9621 為主表 left join 9622 聚合結果；9621 的 `學生數`保留作為總數核對欄位。

不要使用 `科系名稱` 作為唯一鍵，因為 9622 可能將同一科系代碼拆成不同班別／科系名稱。9622 沒有對應的學年度或鍵值則保留為未匹配資料，不補成 0。

目前合併檢查結果（以 9622 原始筆數計算）：

| 學年度 | 全台可合併比例 | 新北市可合併比例 |
|---|---:|---:|
| 113 | 94.10% | 99.18% |
| 114 | 94.07% | 99.16% |

9621 有 103–114 學年度，但 9622 目前只有 113、114 學年度；103–112 學年度沒有詳細學生資料可合併。

## 7. graduate_major.py

### 1. 怎麼 call API

9620 是教育部公開 JSON，不需要 TDX 金鑰；下載完整資料後由 collector 依學年度篩選：

```python
from collectors.graduate_major import fetch_graduate_majors

# 取得全國資料；academic_year 可省略
records = fetch_graduate_majors(academic_year="113", county=None)
```

API：`https://stats.moe.gov.tw/files/opendata/graduatesc.json`

### 2. API 回傳格式

回傳 JSON 陣列，collector 保留教育部原始欄位，不改名、不彙總：

```json
{
  "學年度": "106",
  "細學類": "1111",
  "細學類名稱": "綜合教育細學類",
  "科系名稱": "文教事業經營研究所",
  "日間_進修別": "D 日",
  "等級別": "M 碩士",
  "上學年畢業生人數男": "1",
  "上學年畢業生人數女": "11"
}
```

本次 API 實測共 48,727 筆。9620 目前沒有 `縣市名稱`、學校代碼或學校所在地，因此無法在此資料源篩選新北市；使用預設新北市篩選會明確報錯，需傳 `county=None` 取得全國資料。`151516` 已下架，僅保留為歷史來源備註，未接入 collector。

### 3. 前 5 筆資料

以下為 `fetch_graduate_majors(county=None)` 的實際前 5 筆：

| 學年度 | 細學類 | 細學類名稱 | 科系名稱 | 日間／進修 | 等級 | 男 | 女 |
|---|---:|---|---|---|---|---:|---:|
| 106 | 1111 | 綜合教育細學類 | 文教事業經營研究所 | D 日 | M 碩士 | 1 | 11 |
| 106 | 1111 | 綜合教育細學類 | 文教事業經營研究所 | N 職 | M 碩士 | 3 | 25 |
| 106 | 1111 | 綜合教育細學類 | 文教事業經營碩士在職學位學程 | N 職 | M 碩士 | 1 | 7 |
| 106 | 1111 | 綜合教育細學類 | 國際文教與比較教育學系 | D 日 | D 博士 | 1 | 1 |
| 106 | 1111 | 綜合教育細學類 | 國際文教與比較教育學系 | D 日 | M 碩士 | 2 | 9 |

`細學類` 可在後續 transform 依對照表彙整到 93 學類、27 學門或 11 領域；目前 collector 不自行建立 mapping。

## 8. vt_course.py

### 1. 怎麼 call API

使用勞動部 6060 REST API，預設篩選新北市並以 100 筆分頁抓取：

```python
from collectors.vt_course import count_distinct_courses, fetch_vt_courses

records = fetch_vt_courses()
course_count = count_distinct_courses(records)  # 不重複的課程編號數

# 全台或指定行政區
records = fetch_vt_courses(county=None, district="板橋區")
```

API：`https://apiservice.mol.gov.tw/OdService/rest/datastore/A17000000J-000007-Hv9`

### 2. API 回傳格式

API 回傳 `success`、`updateTime` 與 `result.records`；collector 保留 records 的原始欄位，並依 `offset` 持續分頁。實際回應可能沒有 `result.total`，此時以短頁／空頁停止：

```json
{
  "success": true,
  "updateTime": "20260416T135831",
  "result": {
    "resource_id": "A17000000J-000007-Hv9",
    "records": [
      {
        "訓練縣市": "新北市",
        "訓練區域": "五股區",
        "郵遞區號前三碼": "248",
        "訓練地址": "五權路17號8樓",
        "課程編號": "156211",
        "課程名稱": "水電(五股)",
        "數量": "3"
      }
    ]
  }
}
```

`職訓課程數` 使用不重複的 `課程編號` 計算；`數量` 僅保留為原始欄位，不直接加總為課程數。

### 3. 前 5 筆資料

以下為 `fetch_vt_courses()` 的實際結果：共 74 筆、74 個不重複課程編號。

| 訓練區域 | 郵遞區號 | 訓練地址 | 課程編號 | 課程名稱 | 數量 |
|---|---:|---|---:|---|---:|
| 五股區 | 248 | 五權路17號8樓 | 156211 | 水電(五股) | 3 |
| 五股區 | 248 | 五權路17號7樓 | 156212 | 水電(五股) | 4 |
| 五股區 | 248 | 五權路17號4樓 | 156243 | 3D 立體設計與AI繪圖應用(五股) | 2 |
| 五股區 | 248 | 五權路17號4樓 | 156244 | 3D 立體設計與列印(五股) | 1 |
| 泰山區 | 243 | 致遠新村55-1號 | 156309 | 網路規劃架設(泰山) | 2 |
