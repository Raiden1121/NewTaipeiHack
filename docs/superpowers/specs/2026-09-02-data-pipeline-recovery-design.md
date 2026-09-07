# Data Pipeline Recovery and Source-Aware Scheduling Design

## Goal

修正歷史資料執行中的 timeout、查無資料、來源欄位差異與錯誤期間標記，並讓重跑只處理失敗、缺漏或需要重新 transform 的資料，不重新下載已可安全重用的 raw data。

## Confirmed Root Causes

1. `run_period_range()` 對每個月份執行所有 collectors，沒有區分 monthly、annual、snapshot 與 all-available sources。
2. timeout 由各 collector 包裝成自己的 exception，pipeline 沒有 transient-error retry。
3. 戶政 API 的 `OD-0102-S / 查無資料`、薪資來源缺少指定年份，目前都被列為 error。
4. TaiwanJobs 可能回傳 `新北市不限`，目前 district validation 將合法的 county-level row 當成錯誤。
5. ODRP056 的 113 年 response 使用中文欄位，其他已檢查年份使用 canonical English 欄位。
6. 目前房價、租金、訓練與人才需求的相同快照被寫到多個 requested month，不能視為每月歷史資料。

## Dataset Period Strategies

每個 `CollectorSpec` 新增 `period_strategy`：

| Strategy | Datasets | Execution key | Output partition |
|---|---|---|---|
| `monthly` | population, movement | ROC `yyyMM` | `{dataset}/{yyyMM}.json` |
| `annual` | births, marriages, wages, college_majors, graduate_majors | ROC `yyy` | `{dataset}/{yyy}.json` |
| `snapshot` | house_prices, rentals, job_vacancies, job_vacancy_salaries, vt_courses, training_numbers, TDX | one current fetch | `{dataset}/latest.json` |
| `all_available` | talent_demand | one full-resource fetch | `{dataset}/all.json` |

歷史範圍執行時：

- monthly collectors 逐月執行。
- annual collectors 每個 ROC 年只執行一次。
- snapshot collectors 只執行一次，不標成歷史月份。
- all-available collectors 只執行一次，record 使用來源本身的 `period_start/period_end`。

## Recovery and Resume

新增 CLI 行為：

```bash
python src/run_pipeline.py \
  --start-period 10501 \
  --end-period 11507 \
  --output-dir data \
  --resume \
  --strict
```

`--resume` 決策順序：

1. 讀取 collection report 與 authoritative output index。
2. `ok` 且 schema/transform version 相同、輸出存在：直接標記 `reused_output`。
3. raw 存在但 transform version 不同：不下載，標記 `reused_raw`，重新 transform。
4. `error`、output 缺失或 raw 不可用：重新 collect，標記 `retried` 或 `downloaded`。
5. `skipped/no_data`：預設保留 skipped；使用 `--force` 才重新查詢。
6. `--force` 忽略既有狀態，重新下載指定範圍。

舊 report 沒有 schema version，視為 legacy。monthly/annual 資料優先重用既有 raw；snapshot 從既有 raw 中選最新一份；沒有 raw 的失敗資料才重新下載。

## Retry Policy

- 僅 retry transient network timeout，不 retry schema、validation、no-data 或 unsupported-year errors。
- 最多 3 次 attempts，backoff 為 1 秒、2 秒。
- 每次 retry 在 terminal 顯示 dataset、period、attempt 與原因。
- 最後仍失敗才寫入 `status=error`，report 記錄 `attempts=3`。

## No-Data Contract

新增共用 `CollectorNoDataError`，以下情況使用此類型：

- 戶政 API 回傳 `OD-0102-S / 查無資料`。
- annual collector 因任一必要月份無資料而無法建立完整年度。
- 官方薪資 workbook 不包含指定年份。

Pipeline 將其轉為：

```json
{
  "status": "skipped",
  "reason": "no_data",
  "source_message": "..."
}
```

No-data 不計入 `errors`，也不造成 `--strict` 非零 exit code。

## Source-Specific Fixes

### Births

ODRP056 record 同時接受以下 aliases，保留來源原始欄位並新增 canonical 欄位：

| Canonical | Chinese alias |
|---|---|
| `statistic_yyy` | `統計年度` |
| `according` | `按照別` |
| `site_id` | `區域別` |
| `mother_age` | `生母年齡` |
| `birth_sex` | `出生者性別` |
| `birth_count` | `嬰兒出生數` |

### TaiwanJobs

- 混合回應中的已知外縣市或其他新北市行政區資料：排除該列，不得改標成 query district，並記錄 filtered count／warning。
- 整份回應皆不符合 query district，或 `CITYNAME` 為空白、亂碼、未知格式：維持 validation error。
- `新北市不限`／新北市 city-wide rows：保留為 `geo_level=county`、`district_id=null`。
- county-level rows 在跨郵遞區號查詢後依來源欄位建立穩定 key 去重，不分配到任一行政區。

### Wages

- 找不到指定年份時立即拋出 `CollectorNoDataError`，不再嘗試其他格式後混入 ODS repetition error。
- 保留官方 age groups 與 `proxy_only` 規則。

## Authoritative Outputs

新增 `data/quality/dataset_index.json`，列出 analytics 應讀取的有效 curated files、dataset、period strategy、source period 與 transform version。

既有重複輸出不自動刪除，避免破壞使用者資料；它們不會出現在新的 authoritative index，因此 analytics 不應讀取。之後如需清除 legacy files，另行提供明確的 non-default cleanup command。

## Reports and Terminal Progress

每個 execution unit 記錄：

```text
dataset
execution_key
period_strategy
status
attempts
downloaded
reused_raw
reused_output
rows_in
rows_out
rows_rejected
source_message
```

Terminal 顯示 collect、retry、reuse、transform、skip、output 與 error。

## Tests

所有測試使用 fake responses，不呼叫 live API：

- timeout 前兩次失敗、第三次成功。
- 非 timeout validation error 不 retry。
- timeout 三次後 report 為 error 並記錄 attempts。
- `OD-0102-S` 與 unsupported wage year 為 skipped/no_data。
- ODRP056 中文／英文欄位都能轉成相同 canonical records。
- `新北市不限` 保留為 county level 並跨 zip 去重。
- 混合回應中的 district mismatch 被排除並留下 warning；整份 mismatch 仍被拒絕。
- monthly、annual、snapshot、all-available 執行次數正確。
- `--resume` 重用 output、重用 raw、只重抓 failed/missing。
- legacy reports 不被誤判成新版有效 output。
- dataset index 不包含舊的重複 snapshot outputs。
- 完整 collector tests、transform tests、`py_compile` 與 `git diff --check`。

## Migration Sequence

1. 新增 error taxonomy 與 timeout retry。
2. 修正 births、TaiwanJobs、wages。
3. 新增 period strategy 與 execution units。
4. 新增 resume/raw reuse 與 dataset index。
5. 使用既有 raw 重建可重用資料。
6. 僅重新下載沒有 raw 的 error/missing units。
7. 檢查新 report，確認 timeout、error、skipped 與 authoritative outputs。
