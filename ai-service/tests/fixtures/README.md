# Test fixtures

## `data-pipeline-data/`

**這些不是手寫的。** 是從 data-pipeline 真的跑出來的輸出裁下來的切片：

```bash
cd data-pipeline
python src/run_pipeline.py --period 11507 --output-dir data
```

裁切內容：

| dataset | 保留筆數 | 為什麼選它 |
|---|---|---|
| `population` | 8 | long-form（`metric_id` + `value` 有值），且是唯一 `youth_eligibility=eligible` 的青年核心資料 |
| `job_vacancies` | 6 | wide-form（`metric_id` 與 `value` 都是 null，數值在 `position_count`、`salary_lower` 等欄位），含 `query_district_mismatch_filtered` 品質旗標 |
| `youth_budgets` | 3 | `geo_level=organization`、`district_name=null`，用來擋住「選了行政區就把機關層級資料濾掉」這個 bug |
| `training_numbers` | 2 | `geo_level=county`，另一種非行政區層級 |

`dataset_index.json` 額外保留了 `house_prices` 的條目，但**故意沒有複製它的 curated 檔案** ——
用來覆蓋「index 指到不存在的檔案」這條路徑。

## `data-pipeline-data/analytics/published/test-snapshot/`

**也不是手寫的。** 是從真實的 analytics published snapshot（`dev-full-20260912`）
裁下來的切片，裁切腳本的規則是：

| 處理 | 內容 |
|---|---|
| 行政區 | 只留 `65000010`（板橋區）與 `65000020`（三重區），含以行政區代碼為 key 的物件 |
| `villages` | 截到 4 筆 |
| `keywords` | 截到 30 筆（大於 25 筆上限，所以截斷邏輯測得到） |
| `topics` | 截到 6 筆 |
| `city_councilor_t1` | 截到 3 筆 |
| `borough_chief_v1` | 截到 6 筆 |
| `manifest.json` | 沿用真實形狀，只把 `snapshot_id` 換成 `test-snapshot` |

留兩個行政區而不是一個，是因為有測試要驗「選了板橋區，三重區要被濾掉，
但全市／機關層級要留著」—— 只有一區的話這個條件永遠成立，測不到東西。

### 刻意保留的東西

- **`villages`、`normalizedInputs`、`points` 都留著**（只截短）。有測試在驗它們
  不會進 evidence，fixture 裡直接刪掉的話那些測試就等於什麼都沒驗。
- **`district_details.json` 留著，而且仍列在 `manifest.artifacts` 裡**。
  它與 `dashboard_overview.json` 的 districts 是同一批數值，程式刻意跳過它；
  manifest 不列它的話，「跳過」這件事就驗不到。
- **`keyword_frequency` 與 `topic_weight` 保留多個年度**，這樣「只取最新一年」
  才有東西可以取捨。

### 要重新產生

重跑 data-pipeline 的 analytics 發布流程，然後照上表裁切，並把 `snapshot_id`
換成 `test-snapshot`（`current.json` 也要跟著指過去）。

### 為什麼要用真實切片而不是手寫 fixture

之前的 fixture 是照文件想像手寫的，19 個測試全綠，但證明不了跟 pipeline 相容 ——
等於自己出題自己批改。換成真實輸出之後立刻抓到兩個假設錯誤：

1. 11 個 dataset 裡有 7 個的 `metric_id` 和 `value` **全是 null**，數值散在 dataset 專屬欄位
2. `dataset_index.json` 的 `datasets` 是物件不是陣列，欄位叫 `path` 不是 `curated_path`，而且**沒有 `status` 欄位**

### 唯一的人工改動

`population` 與 `movement` 的 record 帶有 `raw_records` 與 `source_record_ids`，
一筆會匯總約 1000 筆來源資料，8 筆未裁切就是 **7.4 MB**。所以這兩個欄位被截短
（`raw_records` 留 2 筆、`source_record_ids` 留 5 筆），檔案降到 127 KB。

**欄位本身刻意保留著** —— 因為有測試在驗「這些 blob 不會進到 prompt」，
如果 fixture 裡直接把欄位刪掉，那個測試就等於什麼都沒驗到。

### 要重新產生

重跑上面的 pipeline 指令，然後照上表裁切。不要手改這些檔案的欄位內容 ——
一旦手改，它們就退化成「照想像寫的 fixture」，失去存在意義。
