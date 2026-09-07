# Population Collector Design

## Goal

在 `data-pipeline` 建立第一個人口資料 collector，從戶政司新版 `ODRP014` API 取得指定民國年月的新北市村里人口原始資料，供後續 transform 與 analytics 使用。

## Scope

- API endpoint：`https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP014/{yyyymm}`
- `yyyymm` 為必填的民國年月字串，例如 `11507`。
- 預設查詢 `COUNTY=新北市`。
- 支援選擇性 `TOWN` 篩選。
- 自動依 API 回傳的 `totalPage` 逐頁抓取並合併 `responseData`。
- 保留 API 原始村里層級欄位與字串值；不在 collector 中計算 18–35 歲或 29 區指標。
- 不在 collector 內寫入檔案；儲存與 curated transformation 由後續 pipeline layer 負責。

## Public Interface

```python
def fetch_population(
    yyyymm: str,
    county: str = "新北市",
    town: str | None = None,
) -> list[dict[str, str]]:
    """Fetch population records from ODRP014."""
```

輸出是村里層級 `responseData` 的合併結果。欄位包含 `statistic_yyymm`、`district_code`、`site_id`、`village`、`household_no`、`people_total`、男女總人口，以及 `people_age_000_m` 至 `people_age_100up_f` 等欄位。

## Request Flow

1. 驗證 `yyyymm` 為 5 位數民國年月，月份為 `01` 至 `12`。
2. 建立 `PAGE`、`COUNTY`、可選 `TOWN` query parameters。
3. 呼叫 ODRP014 第一頁。
4. 驗證 HTTP 成功、JSON 格式、`responseCode == "OD-0101-S"`。
5. 讀取 `totalPage`，依序取得剩餘頁面。
6. 合併每頁 `responseData` 並回傳。

API 的篩選回應可能仍將 `totalDataSize` 顯示為未篩選的全量筆數，因此分頁控制以 `totalPage` 為準，不以 `totalDataSize` 推算篩選後資料量。

## Error Handling

所有可預期的 collector 錯誤統一拋出 `PopulationCollectorError`，包含：

- `yyyymm` 格式錯誤。
- HTTP error 或 request timeout。
- response 無法解析為 JSON。
- API 回傳非成功 `responseCode`。
- 回應缺少必要的 `responseData` 或分頁欄位。

第一版不做大量並發請求。每個月份按頁序列抓取，timeout 固定，後續若需要排程 retry 再由 pipeline runner 統一處理。

## Documentation

`data-pipeline/src/collectors/data.md` 需說明：

- ODRP014 的來源與完整請求範例。
- `yyyymm`、`COUNTY`、`TOWN` 參數意義。
- API response envelope 與 `responseData` 欄位結構。
- 11507 新北市查詢的 5 筆實際資料範例。
- 單一年齡男女欄位如何供後續 18–35 歲計算使用。
- API 分頁、原始字串值與 `totalDataSize` 篩選後仍可能為全量值等注意事項。

## Verification Criteria

- 使用 `11507` 與預設新北市參數時，collector 可取得 1,039 筆村里資料與 29 個行政區。
- 使用 `town="板橋區"` 時，collector 可取得板橋區資料。
- 多頁回應會完整合併，且不重複或遺漏頁面。
- 非成功 API response、錯誤年月與網路錯誤會轉換為 `PopulationCollectorError`。
- 文件中的範例可對應實際 API response 欄位。

## Out of Scope

- 18–35 歲人口彙總。
- 青年人口年增率、cohort retention signal、A2/B2/B3/B4 指標。
- Raw／Curated 檔案格式與儲存位置。
- Backend API、Frontend 查詢與 AWS 排程。
