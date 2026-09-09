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

## 9. training_nums.py

### 1. 怎麼 call API

使用資料集 59296 的勞動部 REST API，預設只抓新北市，並以 `limit`／`offset` 分頁：

```python
from collectors.training_nums import fetch_training_numbers, sum_training_people

records = fetch_training_numbers()                 # 縣市別辦訓地=新北市
training_people = sum_training_people(records)     # 加總訓練人次
records = fetch_training_numbers(county=None)      # 抓全台
```

API：`https://apiservice.mol.gov.tw/OdService/rest/datastore/A17000000J-030190-lfV`

### 2. API 回傳格式

回傳 `success`、`updateTime`、`result.records`；collector 保留勞動部原始欄位：

```json
{
  "success": true,
  "updateTime": "20260831T...",
  "result": {
    "resource_id": "A17000000J-030190-lfV",
    "records": [
      {
        "訓練單位名稱": "中華民國全競利促進協會",
        "縣市別辦訓地": "新北市",
        "課程代碼": "172991",
        "課程名稱": "新多益聽力與閱讀能力培訓班",
        "訓練時數": "47",
        "訓練人次": "22",
        "每人訓練費用": "9180",
        "開訓日期": "20260823",
        "結訓日期": "20261018"
      }
    ]
  }
}
```

目前資料只有 `縣市別辦訓地`，因此 collector 只能產出「新北市」縣市層級，不能拆成新北市 29 區；若需要區級資料，需另找含地址或訓練區域的資料源。

### 3. 前 5 筆資料

以下為 API 實測 `fetch_training_numbers()` 結果：87 筆，`訓練人次` 加總 2,104。

| 訓練單位名稱 | 課程代碼 | 課程名稱 | 訓練人次 | 開訓日期 | 結訓日期 |
|---|---:|---|---:|---|---|
| 中華民國全競利促進協會 | 172991 | 新多益聽力與閱讀能力培訓班 | 22 | 20260823 | 20261018 |
| 中華民國幸福城市營造發展協會 | 173075 | 貴金屬成型銼焊與精緻飾品設計實務班 | 25 | 20260825 | 20261013 |
| 中華民國幸福城市營造發展協會 | 173092 | 永生花藝與香氛石文創商品設計實務班 | 20 | 20260830 | 20261108 |
| 中華民國指甲彩繪美容職業工會聯合會 | 173309 | 沙龍凝膠彩繪美甲設計班 | 25 | 20260823 | 20261129 |
| 中華民國勞動災害防止協會附設台北職業訓練中心 | 172979 | 甲種職業安全衛生業務主管教育訓練班 | 16 | 20260903 | 20260929 |

## 10. birth_nums.py

### 1. 怎麼 call API

使用 101883 的戶政司 ODRP056 API，預設抓新北市並依 `totalPage` 分頁：

```python
from collectors.birth_nums import aggregate_young_births, fetch_birth_numbers

records = fetch_birth_numbers("114")       # 預設只保留新北市各區
young_births = aggregate_young_births(records)
records = fetch_birth_numbers("114", county=None)  # 抓全台
```

API：`https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP056/{yyy}`

### 2. API 回傳格式

API 回傳 `responseCode`、`totalPage`、`pageDataSize` 與 `responseData`。每筆資料包含統計年度、區域、生母單一年齡、出生者性別與出生數；collector 保留原始欄位與字串值。

```json
{
  "responseCode": "OD-0101-S",
  "responseMessage": "處理完成",
  "totalPage": "14",
  "totalDataSize": "27232",
  "page": "1",
  "pageDataSize": "2000",
  "responseData": [
    {
      "statistic_yyy": "114",
      "according": "按發生日期分",
      "site_id": "新北市板橋區",
      "mother_age": "18歲",
      "birth_sex": "男",
      "birth_count": "2"
    }
  ]
}
```

`aggregate_young_births()` 會精準篩選生母 `18歲` 至 `35歲`，再依 `site_id` 加總男、女出生數；若 API 提供 `總計`／`合計`性別列，則優先使用該列，避免重複計算。資料口徑為「按發生日期分」，不再使用 32945 或 102762 的五歲年齡組資料。

資料品質檢查包含：確認 API 成功碼、所有分頁的年度一致、必要欄位存在、出生數為非負整數，以及同一區域／年齡／性別不重複。

### 3. 前 5 筆資料

以下為 ODRP056/114 第一頁實測前 5 筆：

| 統計年度 | 區域 | 生母年齡 | 出生者性別 | 出生數 |
|---:|---|---|---|---:|
| 114 | 新北市板橋區 | 未滿15歲 | 男 | 0 |
| 114 | 新北市板橋區 | 15歲 | 男 | 0 |
| 114 | 新北市板橋區 | 16歲 | 男 | 0 |
| 114 | 新北市板橋區 | 17歲 | 男 | 0 |
| 114 | 新北市板橋區 | 18歲 | 男 | 2 |

## 11. marriage_nums.py

### 1. 怎麼 call API

使用 32970 的戶政司 ODRP003 API。API 是月資料，collector 會自動呼叫指定民國年度的 12 個月份；預設抓新北市：

```python
from collectors.marriage_nums import aggregate_marriage_pairs, fetch_marriage_numbers

records = fetch_marriage_numbers("114")
annual_pairs = aggregate_marriage_pairs(records)  # 依新北市各區加總

# 指定單一行政區；county=None 可抓全台
records = fetch_marriage_numbers("114", town="板橋區")
```

API：`https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP003/{yyymm}`

### 2. API 回傳格式

API 回傳 `responseCode`、`totalPage`、`pageDataSize` 與 `responseData`。資料粒度是村里，collector 保留所有原始欄位；`aggregate_marriage_pairs()` 再將每月村里 `marry_pair` 彙整為年度區級結婚對數。

```json
{
  "responseCode": "OD-0101-S",
  "responseMessage": "處理完成",
  "totalPage": "4",
  "totalDataSize": "7851",
  "page": "1",
  "pageDataSize": "2000",
  "responseData": [
    {
      "statistic_yyymm": "10601",
      "site_id": "新北市板橋區",
      "village": "留侯里",
      "marry_pair": "2",
      "divorce_pair": "2"
    }
  ]
}
```

資料是一般人口的結婚對數，不是青年專屬結婚數；只能作為生育前導背景指標，不宜直接當作 E1 青年結婚數。

### 3. 前 5 筆資料

以下為 ODRP003/10601 第一頁實測前 5 筆：

| 統計年月 | 區域 | 村里 | 結婚對數 | 離婚對數 |
|---:|---|---|---:|---:|
| 10601 | 新北市板橋區 | 留侯里 | 2 | 2 |
| 10601 | 新北市板橋區 | 流芳里 | 0 | 1 |
| 10601 | 新北市板橋區 | 赤松里 | 0 | 0 |
| 10601 | 新北市板橋區 | 黃石里 | 1 | 0 |
| 10601 | 新北市板橋區 | 挹秀里 | 1 | 0 |

## 12. job_vacancy.py

### 1. 怎麼 call API

```python
from collectors.job_vacancy import (
    count_job_vacancies_by_district,
    fetch_new_taipei_job_vacancies,
    sum_job_person_by_district,
)

# 預設依郵遞區號抓新北市 29 區
records = fetch_new_taipei_job_vacancies()
vacancy_counts = count_job_vacancies_by_district(records)
position_counts = sum_job_person_by_district(records)
```

單一行政區 API：

```text
https://free.taiwanjobs.gov.tw/webservice_taipei/webservice.ashx?city=31&zipno=220&count=1000&T=CSV
```

`city=31` 是新北市，`zipno` 使用 3 碼郵遞區號，`count` 最多 1,000；collector 會依查詢郵遞區號加入 `query_zipno` 與 `district`。

### 2. API 回傳格式

API 回傳 CSV。欄位名稱實際為「代碼＋中文說明」，例如：

```csv
"OCCU_DESC（職務名稱）","JOB_PERSON（雇用人數）","CITYNAME（工作地點）",...
```

collector 保留所有原始欄位，並補上：

- `query_zipno`：本次查詢使用的郵遞區號
- `district`：郵遞區號對應的行政區
- `query_truncated`：回傳筆數達到 `count` 時為 `true`，表示可能超過 API 上限

職缺筆數使用 API 回傳筆數；`JOB_PERSON` 加總則代表職缺名額。每萬名青年職缺數為「區域職缺筆數 ÷ 區域 18–35 歲人口 × 10,000」。

### 3. 前 5 筆資料

以下為 `fetch_job_vacancies("220", district="板橋區", count=5)` 的 live 回傳前 5 筆（2026-08-31）：

| 職務名稱 | 雇用人數 | 工作地點 | 應徵截止日期 | 職缺更新日期 |
|---|---:|---|---|---|
| 資訊安全管理顧問 | 1 | 新北市板橋區 | 20261231 | 20260828 |
| 資訊安全程式設計顧問 | 1 | 新北市板橋區 | 20261231 | 20260828 |
| 資安管理助理顧問 | 1 | 新北市板橋區 | 20261231 | 20260828 |
| 【台北】地區專員 | 1 | 新北市板橋區 | 額滿為止 | 20260824 |
| 【台北】專案部專員 | 1 | 新北市板橋區 | 額滿為止 | 20260824 |

這次查詢設定 `count=5`，因此 5 筆資料的 `query_truncated` 會是 `true`；正式計算應使用 `count=1000` 並監控是否達到上限。

44062 是目前刊登中的職缺清單，API 沒有 `year`、`yyyymm` 或歷史日期查詢參數，無法直接取得前幾年的逐筆職缺資料；若要建立歷史趨勢，需從現在開始定期保存快照。

## 13. talent_demand.py

### 1. 怎麼 call API

使用勞動部資料集 146549 的 JSON resource `A17000000J-030281-nQF`：

```python
from collectors.talent_demand import fetch_talent_demand

# 抓取 API 提供的全部歷史統計期
records = fetch_talent_demand()

# 只抓指定統計期
records_102 = fetch_talent_demand("102年")
```

API：

```text
https://apiservice.mol.gov.tw/OdService/rest/datastore/A17000000J-030281-nQF
```

collector 使用 `limit`／`offset` 自動分頁，預設每頁 100 筆；可用 `period` 指定 `統計期`。資料是全國／職業別，不提供新北市 29 區篩選。

### 2. API 回傳格式

API 回傳 `success`、`updateTime` 與 `result.records`。目前實際回應可能沒有 `result.total`，collector 會以短頁或空頁停止分頁；原始欄位與數值字串會保留：

```json
{
  "success": true,
  "updateTime": "20260616T104021",
  "result": {
    "resource_id": "A17000000J-030281-nQF",
    "records": [
      {
        "統計期": "102年",
        "職業別": "專業人員",
        "新登記求才人數（人次）": "118899",
        "新登記求才僱用人數（人次）": "20222",
        "有效求才僱用人數（人次）": "58297"
      }
    ]
  }
}
```

### 3. 前 5 筆資料

以 `page_size=1000` 實際呼叫 collector 共取得 117 筆；以下為 `limit=5&offset=0` 的 API 前 5 筆：

| 統計期 | 職業別 | 新登記求才人數 | 新登記求才僱用人數 | 有效求才僱用人數 |
|---|---|---:|---:|---:|
| 102年 | 民意代表、主管及經理人員 | 14989 | 2457 | 7243 |
| 102年 | 專業人員 | 118899 | 20222 | 58297 |
| 102年 | 技術員及助理專業人員 | 367366 | 90907 | 219061 |
| 102年 | 事務支援人員 | 100277 | 25018 | 56095 |
| 102年 | 服務及銷售工作人員 | 273045 | 59743 | 170511 |

此資料可用於全國職業別的歷史趨勢；若要分析新北市 29 區，仍需使用 `job_vacancy.py` 保存每日職缺快照或另找具區域欄位的資料源。

## 14. wage.py

### 1. 怎麼取得資料

`wage.py` 會先 GET [主計總處表6下載頁](https://www.stat.gov.tw/News_Content.aspx?n=4580&s=232642)，動態找到最新的 XLSX；找不到或解析失敗時改用 ODS。這是年度檔案下載，不是 REST API。

```python
from collectors.wage import fetch_wage

records = fetch_wage()                    # 預設新北市、最新工作表
records = fetch_wage(county=None)         # 全台
records = fetch_wage(year="112年")        # 指定歷史年度
```

檔案以 SHA-256 快取；檔案雜湊未變更時不重新解析 XLSX／ODS。

### 2. 回傳格式

```json
{
  "records": [
    {
      "資料年度": "113年",
      "縣市別": "新北市",
      "統計方式": "平均數",
      "年齡別": "未滿25歲",
      "薪資": 48.3,
      "單位": "萬元",
      "原始欄位": "平均數／未滿25歲"
    }
  ],
  "metadata": {
    "fetched_at": "2026-09-01T06:15:28+00:00",
    "published_year": "113年",
    "source_url": "官方表6 XLSX 連結",
    "file_hash": "sha256:..."
  }
}
```

### 3. 前 5 筆資料

113年 XLSX 實際呼叫結果（新北市共 16 筆）：

| 資料年度 | 縣市別 | 統計方式 | 年齡別 | 薪資 | 單位 |
|---|---|---|---|---:|---|
| 113年 | 新北市 | 平均數 | 總計 | 71.1 | 萬元 |
| 113年 | 新北市 | 平均數 | 未滿30歲 | 56.7 | 萬元 |
| 113年 | 新北市 | 平均數 | 未滿25歲 | 48.3 | 萬元 |
| 113年 | 新北市 | 平均數 | 25-29歲 | 59.9 | 萬元 |
| 113年 | 新北市 | 平均數 | 30-39歲 | 69 | 萬元 |

資料目前只有縣市層級、年度資料，無法取得新北市 29 區薪資；官方也沒有精確的 18–35 歲分組，因此 collector 保留官方年齡組，不自行估算。

## 15. job_vacancy_salary.py

### 1. 怎麼 call API

此 collector 重用 `job_vacancy.py`，依新北市 29 區郵遞區號呼叫台灣就業通 CSV，再在本地篩選 `SALARYCD=月薪`：

```python
from collectors.job_vacancy_salary import (
    fetch_job_posted_salaries,
    summarize_posted_salary_by_district,
)

# 預設抓新北市 29 區，每區最多 1,000 筆
records = fetch_job_posted_salaries(count=1000)
summary = summarize_posted_salary_by_district(records)

# 測試單一行政區
records = fetch_job_posted_salaries(
    zip_codes={"板橋區": "220"},
    count=10,
)
```

單一行政區 API 格式：

```text
https://free.taiwanjobs.gov.tw/webservice_taipei/webservice.ashx?city=31&zipno=220&count=1000&T=CSV
```

### 2. 回傳格式

API 原始格式為 CSV；collector 保留原始欄位，並加入：

```json
{
  "CITYNAME（工作地點）": "新北市板橋區",
  "SALARYCD（核薪方式）": "月薪",
  "NT_L（薪資範圍下限）": "35000",
  "NT_U（薪資範圍上限）": "40000",
  "district": "板橋區",
  "query_zipno": "220",
  "query_truncated": false,
  "salary_type": "月薪",
  "salary_lower": 35000,
  "salary_upper": 40000,
  "salary_midpoint": 37500,
  "salary_estimate_type": "range_midpoint",
  "snapshot_fetched_at": "2026-09-01T00:00:00+00:00"
}
```

`salary_midpoint` 只有在 `NT_L` 與 `NT_U` 都有數字時才計算；單邊薪資會保留，但不納入區級中位數。`query_truncated=true` 表示該區原始回應可能達到 1,000 筆上限。

### 3. 前 5 筆資料

板橋區 `count=10` 實際呼叫結果：原始職缺 10 筆，篩選月薪後 8 筆。

| 工作地點 | 核薪方式 | 薪資下限 | 薪資上限 | 薪資中點 | 估計類型 |
|---|---|---:|---:|---:|---|
| 新北市板橋區 | 月薪 | 35000 | 40000 | 37500 | range_midpoint |
| 新北市板橋區 | 月薪 | 32000 | 35000 | 33500 | range_midpoint |
| 新北市板橋區 | 月薪 | 33000 | 38000 | 35500 | range_midpoint |
| 新北市板橋區 | 月薪 | 32000 | 37000 | 34500 | range_midpoint |
| 新北市板橋區 | 月薪 | 46000 | 空值 | 空值 | lower_bound |

此資料是目前刊登中的職缺快照，沒有 `year`／`yyyymm` 歷史查詢參數；若要做趨勢，需定期保存 `snapshot_fetched_at`。職缺資料沒有年齡欄位，不等同於 `wage.py` 的青年實際薪資。

## 16. rental_price.py

### 1. 怎麼 call API

預設使用新北市資料開放平台 CSV API，保留完整資料；可依區篩選。預設只保留住宅租賃，排除車位、土地、店面與辦公室類型。

```python
from collectors.rental_price import fetch_rental_prices

records = fetch_rental_prices()                 # 新北市住宅租賃
records = fetch_rental_prices(district="板橋區")
records = fetch_rental_prices(residential_only=False)  # 含非住宅資料
records = fetch_rental_prices(source_format="json")   # JSON 格式
```

CSV API：

```text
https://data.ntpc.gov.tw/api/datasets/18d62577-1d5f-4967-ab9c-d71faba8cde1/csv/file
```

同資料集的 JSON endpoint 目前實測回傳 30 筆，CSV endpoint 實測回傳 45,932 筆，因此預設使用 CSV，避免把部分資料當成完整樣本。

### 2. 回傳格式

回傳 `list[dict]`，保留原始 `district`、`rps01`～`rps34` 欄位，並加入單筆標準化欄位：

```json
{
  "district": "土城區",
  "rps01": "租賃房屋",
  "rps07_yyymmddroc": "1140219",
  "rps15_area": "85.8",
  "rps22_amountsunitdollars": "23000",
  "rps23_amountsunitdollars": "268",
  "rps29": "整棟(戶)出租",
  "rental_date": "1140219",
  "rental_period": "11402",
  "rent_total": 23000,
  "building_area_sqm": 85.8,
  "rent_per_sqm": 268,
  "rent_per_ping": 885.95038,
  "rental_type": "整戶",
  "snapshot_fetched_at": "2026-09-01T07:21:42+00:00"
}
```

缺漏或「面議」的數值欄位會保留原始值，標準化數值為 `None`；`rent_per_ping` 是單筆換算，不是區級統計。租金中位數、租金／坪中位數、YoY、有效樣本數、缺漏數與極端值數均留到 `analytics` 計算。

### 3. 前 5 筆資料

本次以 CSV 實際呼叫，住宅篩選後取得 41,177 筆、涵蓋 27 區；以下為前 5 筆：

| 區域 | 租賃類型 | 租賃年月日 | 建物面積（平方公尺） | 租金總額 | 租金／平方公尺 | 租金／坪 |
|---|---|---:|---:|---:|---:|---:|
| 土城區 | 整戶 | 1140219 | 85.8 | 23000 | 268 | 885.95038 |
| 板橋區 | 整戶 | 1140221 | 274.35 | 70000 | 255 | 842.975175 |
| 板橋區 | 整戶 | 1140211 | 109.51 | 18000 | 164 | 542.14874 |
| 板橋區 | 整戶 | 1140215 | 98.02 | 24000 | 245 | 809.917325 |
| 土城區 | 整戶 | 1140215 | 61.55 | 21000 | 341 | 1127.272685 |

此資料是定期更新的租賃交易快照；collector 不產生區級彙總或 YoY。若需歷史趨勢，應定期保存每次 `snapshot_fetched_at` 與原始資料。

## 17. house_price.py

### 1. 怎麼 call API

預設使用新北市資料開放平台 CSV API，資料已包含 `district`，不需逐區呼叫。預設只保留住宅買賣，排除土地、車位、純建物、店面與辦公用途。

```python
from collectors.house_price import fetch_house_prices

records = fetch_house_prices()                      # 新北市住宅買賣
records = fetch_house_prices(district="板橋區")
records = fetch_house_prices(residential_only=False)  # 含非住宅交易
records = fetch_house_prices(source_format="json")   # JSON 格式
```

CSV API：

```text
https://data.ntpc.gov.tw/api/datasets/acce802d-58cc-4dff-9e7a-9ecc517f78be/csv/file
```

### 2. 回傳格式

回傳 `list[dict]`，保留原始 `district`、`rps01`～`rps32` 欄位，並加入單筆標準化欄位：

```json
{
  "district": "板橋區",
  "rps01": "房地(土地+建物)",
  "rps07_yyymmddroc": "1140521",
  "rps15_area": "104.73",
  "rps21_amountsunitdollars": "4200000",
  "rps22_amountsunitdollars": "40103",
  "transaction_date": "1140521",
  "transaction_period": "11405",
  "total_price": 4200000,
  "building_area_sqm": 104.73,
  "price_per_sqm": 40103,
  "price_per_ping": 132571.895855,
  "transaction_type": "房地(土地+建物)",
  "snapshot_fetched_at": "2026-09-01T07:30:00+00:00"
}
```

缺漏或「面議」的數值欄位會保留原始值，標準化數值為 `None`；`price_per_ping` 是單筆換算，不是區級統計。房價中位數、房價／m² 中位數、成長率、有效樣本數、缺漏數與極端值數均留到 `analytics` 計算。

### 3. 前 5 筆資料

本次以 CSV 實際呼叫，住宅篩選後取得 43,092 筆、涵蓋 28 區；以下為前 5 筆：

| 區域 | 交易標的 | 交易年月日 | 建物面積（平方公尺） | 總價 | 單價／平方公尺 | 單價／坪 |
|---|---|---:|---:|---:|---:|---:|
| 板橋區 | 房地(土地+建物) | 1140521 | 104.73 | 4200000 | 40103 | 132571.895855 |
| 板橋區 | 房地(土地+建物) | 1140513 | 45.63 | 7450000 | 163270 | 539735.51695 |
| 新莊區 | 房地(土地+建物)+車位 | 1140507 | 130.68 | 16300000 | 124732 | 412337.17462 |
| 三芝區 | 房地(土地+建物) | 1140519 | 52.85 | 3200000 | 60549 | 200161.975965 |
| 淡水區 | 房地(土地+建物)+車位 | 1140510 | 178.3 | 15500000 | 86932 | 287378.50162 |

此資料是定期更新的買賣交易快照；collector 不產生區級彙總、房價中位數或成長率。若需歷史趨勢，應定期保存每次 `snapshot_fetched_at` 與原始資料。

## youth_budget.py

### 1. 怎麼 call 官方預算來源

`youth_budgets` 從新北市政府青年局的預算公告列表動態發現年度文件，再進入詳情頁下載 PDF；不硬編碼單一檔案 URL。collector 只解析 PDF 中的「計畫及預算統計表」。

```python
from collectors.youth_budget import fetch_youth_budgets

# 列表頁上所有符合規則的 ROC 年度與版本
payload = fetch_youth_budgets()

# 僅驗證指定年度；測試時可注入 open_url，不會呼叫 live source
payload = fetch_youth_budgets(years=("115", "116"))
```

列表來源：

```text
https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=108
```

文件標題中的 `預算案` 對應 `proposed_budget`；`法定版` 與 `法定預算` 對應 `legal_budget`。同年度不同版本以 `document_id` 與 PDF SHA-256 共存，不互相覆蓋。

### 2. 回傳格式與保存規則

`fetch_youth_budgets()` 回傳 `CollectedPayload`：`records` 保存來源字串、`metadata.documents` 保存公告／詳情／PDF URL、日期、版本、頁碼與 hash，`artifacts` 保存 PDF bytes。pipeline 再將 PDF 寫到：

```text
data/raw/youth_budgets/artifacts/{roc_year}_{status}_{sha256_prefix}.pdf
```

每筆 raw row 至少包含 `budget_year_roc`、`document_status`、`row_type`、`business_plan`、`work_plan`、`budget_amount`、`ratio_percent`、`source_page_number`、`source_document_url`、`source_pdf_sha256` 與 `document_id`。`budget_amount`、`ratio_percent` 保留來源字串，型別驗證交由 transform。

目前 parser 以 `pypdf` 搜尋表格標題與欄位，不固定第 28 頁；找不到標題／header、非 PDF、超過 50 MB、數值格式錯誤或重複 total row 時會記錄失敗。測試使用 fake HTML／PDF response；live source 僅作手動 smoke check。
