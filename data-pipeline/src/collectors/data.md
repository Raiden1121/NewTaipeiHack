# 資料說明

## 1. population_collector.py

使用戶政司新版人口資料 API `ODRP014`：

```text
https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/{yyyymm}
```

### API 呼叫方式

```python
from collectors.population_collector import fetch_population

records = fetch_population("11507")
```

`yyyymm` 是必填的民國年月，格式為 5 位數，例如：

- `11507`：民國 115 年 7 月
- 不使用 `202607` 這種西元年月格式

函式介面：

```python
fetch_population(
    yyyymm: str,
    county: str | None = "新北市",
    town: str | None = None,
) -> list[dict[str, str]]
```

預設會呼叫：

```text
GET https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/11507
    ?PAGE=1
    &COUNTY=新北市
```

指定行政區時：

```python
records = fetch_population("11507", town="板橋區")
```

實際 query parameters 為 `PAGE=1&COUNTY=新北市&TOWN=板橋區`。

抓取全台資料時將 `county` 設為 `None`，省略 `COUNTY` 參數：

```python
records = fetch_population("11507", county=None)
```

collector 只回傳全台或新北的村里原始資料；全台與新北的 18–35 歲人口比較，交由後續 transform 依單一年齡欄位彙總。

### API 回應格式

戶政司 API 回傳一個 response envelope：

```json
{
  "responseCode": "OD-0101-S",
  "responseMessage": "處理完成",
  "totalPage": "1",
  "totalDataSize": "7781",
  "page": "1",
  "pageDataSize": "1039",
  "responseData": [
    {
      "statistic_yyymm": "11507",
      "district_code": "65000010001",
      "site_id": "新北市板橋區",
      "village": "留侯里",
      "household_no": "733",
      "people_total": "1613",
      "people_total_m": "776",
      "people_total_f": "837",
      "people_age_018_m": "3",
      "people_age_018_f": "7"
    }
  ]
}
```

`fetch_population()` 會：

1. 驗證 `responseCode == "OD-0101-S"`。
2. 依 `totalPage` 逐頁呼叫 API。
3. 合併所有頁面的 `responseData`。
4. 只回傳村里記錄 list，不回傳外層 envelope。

API 原始值保留為字串，例如人口數要在後續 transform layer 使用 `int(value)` 轉換。

### 11507 新北市資料範例

以下是呼叫 `fetch_population("11507")` 取得的前 5 筆資料。完整記錄還包含 0 歲至 99 歲，以及 100 歲以上的男女單一年齡欄位。

| 統計年月 | 區域代碼    | 行政區       | 村里   | 戶數 | 人口數 |  男 |  女 | 18歲男 | 18歲女 | 35歲男 | 35歲女 |
| -------- | ----------- | ------------ | ------ | ---: | -----: | --: | --: | -----: | -----: | -----: | -----: |
| 11507    | 65000010001 | 新北市板橋區 | 留侯里 |  733 |   1613 | 776 | 837 |      3 |      7 |      8 |     12 |
| 11507    | 65000010002 | 新北市板橋區 | 流芳里 |  657 |   1430 | 644 | 786 |      2 |      5 |      5 |      9 |
| 11507    | 65000010003 | 新北市板橋區 | 赤松里 |  538 |   1083 | 497 | 586 |      6 |      1 |      7 |      5 |
| 11507    | 65000010004 | 新北市板橋區 | 黃石里 |  551 |   1267 | 610 | 657 |      2 |      5 |      8 |     16 |
| 11507    | 65000010005 | 新北市板橋區 | 挹秀里 |  875 |   1911 | 935 | 976 |      9 |      8 |     12 |     13 |

主要欄位：

| 欄位                                    | 說明                             |
| --------------------------------------- | -------------------------------- |
| `statistic_yyymm`                       | 統計年月，民國年月               |
| `district_code`                         | 村里區域代碼，作為後續穩定識別值 |
| `site_id`                               | 行政區名稱，例如 `新北市板橋區`  |
| `village`                               | 村里名稱                         |
| `household_no`                          | 戶數                             |
| `people_total`                          | 總人口數                         |
| `people_total_m` / `people_total_f`     | 男／女總人口數                   |
| `people_age_018_m` / `people_age_018_f` | 18 歲男／女人口數                |
| `people_age_035_m` / `people_age_035_f` | 35 歲男／女人口數                |

單一年齡欄位命名規則為：

```text
people_age_{三位數年齡}_{m 或 f}
```

100 歲以上使用 `people_age_100up_m` 與 `people_age_100up_f`。

### 後續 18–35 歲計算

collector 只保留村里原始資料，不在這裡計算指標。後續 transform layer 應先依 `district_code` 分組；以下範例假設 `records` 已經是單一行政區的村里資料，再加總：

```python
male_18_35 = sum(
    int(record[f"people_age_{age:03d}_m"])
    for record in records
    for age in range(18, 36)
)

female_18_35 = sum(
    int(record[f"people_age_{age:03d}_f"])
    for record in records
    for age in range(18, 36)
)
```

年增率應比較相同月份，例如 `11507` 與 `11407`；留存訊號則需要連續月份資料。

### 分頁與資料量注意事項

- API 的單頁大小目前為最多 2,000 筆。
- 全台 `11507` 約 7,781 筆，會分成 4 頁。
- 加上 `COUNTY=新北市` 後約 1,039 筆，為 1 頁，包含 29 個行政區。
- collector 會按頁順序請求，不做大量並發。
- 篩選後 API 的 `totalDataSize` 可能仍顯示全量 7,781，實際資料筆數應以 `responseData` 或 `pageDataSize` 為準。
- 網路、HTTP、JSON 或 API 回應錯誤會統一拋出 `PopulationCollectorError`。
- collector 不寫入檔案；Raw／Curated 儲存由後續 pipeline layer 負責。

## 2. moving_in.py

### 資料來源與呼叫方式

遷入／遷出 collector 使用戶政司新版 `ODRP011`「遷入遷出統計表」：

```text
https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP011/{yyyymm}
```

參考資料集：[戶籍動態](https://data.gov.tw/dataset/124872)。該資料集是新北市年度區級摘要；本 collector 改用 `ODRP011` 取得較細的鄉鎮市區／村里層級資料。`ODRP012` 是出生、死亡、婚姻等動態統計，不是本資料使用的 API。

```python
from collectors.moving_in import fetch_moving

records = fetch_moving("11507")
records = fetch_moving("11507", town="板橋區")
```

`yyyymm` 使用 5 位數民國年月，例如 `11507`。預設呼叫新北市，API query 為：

```text
PAGE=1&COUNTY=新北市
```

指定行政區時會加上：

```text
TOWN=板橋區
```

collector 會依 `totalPage` 逐頁呼叫，最後回傳合併後的 `responseData` 村里記錄；原始數值保留為字串，不在 collector 內做區級加總。

### 回傳資料範例

```json
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
  "in_tp_f": "0",
  "out_tp_m": "2",
  "out_tp_f": "0"
}
```

主要欄位：

| 欄位 | 說明 |
|---|---|
| `in_total_m` / `in_total_f` | 遷入男／女人數 |
| `out_total_m` / `out_total_f` | 遷出男／女人數 |
| `in_tp_*`、`in_ntp_*`、`in_ty_*` 等 | 遷入來源：臺北市、新北市、桃園市等 |
| `out_tp_*`、`out_ntp_*`、`out_ty_*` 等 | 遷出去向：臺北市、新北市、桃園市等 |
| `in_foreign_*` / `out_foreign_*` | 國外遷入／遷出 |
| `in_other_town_*` / `out_other_town_*` | 同縣市其他鄉鎮市區遷入／遷出 |
| `site_id` | 鄉鎮市區名稱，區級統計時使用此欄位分組 |
| `village` | 村里名稱 |

`*_m` 為男性、`*_f` 為女性。若要以區為單位，應在後續 transform layer 依 `district_code` 或 `site_id` 分組後加總；collector 保留較細的村里資料，方便之後選擇區級或村里級呈現。
