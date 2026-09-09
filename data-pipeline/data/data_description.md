# Data Pipeline 資料說明

本文件依據 `data/curated/` 內的既有處理結果，以及 2026-09-09 `11201`～`11601` range pipeline output 撰寫，涵蓋目前已串接的 18 個既有 canonical datasets，並補充本次新增的 `babysitting_places` collector／transform 契約。範例值直接取自 generated JSON，沒有自行編造或重新計算；新資料集首次 live 執行後才會產生最新 curated snapshot。

> 範例只展示標準化後較重要的欄位。完整來源內容仍保存在各筆資料的 `raw_record`、`raw_records`、`overview_raw_record` 或 `detail_raw_records`，因內容很大，不在本文件重複展開。

## 目前資料完整度

- 目前 18 個既有 canonical datasets 都有至少一份實際 curated 輸出；`youth_budgets` 的 range 執行產生 1 份 `all` curated 輸出。
- `babysitting_places` 已加入 collector、transform 與 pipeline registry；2026-09-09 live smoke 取得私托 261 筆、公托 130 筆，共 391 筆，391 筆均通過 transform，來源本身沒有歷史年度參數。
- 2026-09-04 的 TDX 執行成功取得 `bus_stops`、`railway_stops`、`bike_stops`。
- 2026-09-09 的 `11201`～`11601` range 執行結果為 102 組成功、28 組來源無資料、1 組傳輸失敗；唯一失敗的是 `population` 的 `11206`，原因為 HTTP 回應中途截斷 (`IncompleteRead`)。
- `data/quality/collection_range.json` 記錄本次 range 執行結果；`data/quality/dataset_index.json` 只列本次成功的 execution units，因此不包含失敗的 `population/11206`，也不包含本次未使用 `--include-tdx` 的 TDX 資料。歷史期間仍需參考下列各資料夾。
- 資料來源沒有提供的期間不會以 0 補值；缺失欄位一律保留為 JSON `null`。

## 共同資料結構

每筆 curated record 都有下列共同 Keys：

| Key | 說明 |
|---|---|
| `dataset` | canonical 資料集名稱 |
| `source` | 資料來源識別名稱 |
| `source_record_id` | 可穩定辨識來源資料的 ID |
| `geo_level` | 地理粒度：`district`、`county`、`national` 或 `organization` |
| `district_id` | 新北市行政區代碼；無可靠區級資料時為 `null` |
| `district_name` | 新北市行政區名稱；無可靠區級資料時為 `null` |
| `period_start` | 資料代表期間起日 |
| `period_end` | 資料代表期間迄日 |
| `period_type` | `day`、`month`、`year` 或 `snapshot` |
| `metric_id` | 指標名稱；單筆明細型資料可為 `null` |
| `value` | 指標值；單筆明細型資料可為 `null` |
| `unit` | `value` 的單位；單筆明細型資料可為 `null` |
| `age_scope` | 年齡口徑，例如 `derived_18_35`、`exact_18_35`、`all_ages` |
| `age_min` | 年齡下限；沒有精確年齡口徑時為 `null` |
| `age_max` | 年齡上限；沒有精確年齡口徑時為 `null` |
| `youth_eligibility` | `eligible`、`proxy_only` 或 `context_only` |
| `fetched_at` | pipeline 取得資料的時間 |
| `quality_flags` | 該筆資料的品質警告陣列 |

18–35 歲核心分析只能使用 `youth_eligibility=eligible`。`proxy_only` 只能作近似參考，`context_only` 只能作青年生活環境背景。

## 資料集總覽

| Dataset | 統計內容 | 實際可用期間 | 地理粒度 | 18–35 歲用途 |
|---|---|---|---|---|
| `population` | 總人口與 18–35 歲人口 | 2018-01～2026-07，缺 2024-08 | 新北市 29 區 | 青年人口可直接使用 |
| `movement` | 遷入、遷出與淨遷徙 | 2018-01～2026-07，缺 2024-08 | 新北市 29 區 | 背景指標 |
| `births` | 生母 18–35 歲出生數 | 2019～2025 | 新北市 29 區 | 可直接使用 |
| `marriages` | 全年結婚對數 | 2017 | 新北市 29 區 | 背景指標 |
| `house_prices` | 房屋實價登錄交易 | 2013-03-24～2026-06-26 | 28 區 | 背景指標 |
| `rentals` | 租賃實價登錄交易 | 2025-02-11～2026-06-10 | 27 區 | 背景指標 |
| `job_vacancies` | 台灣就業通職缺 | 2026-09-03 快照 | 區／市 | 背景指標 |
| `job_vacancy_salaries` | 有可解析薪資的職缺 | 2026-09-03 快照 | 區／市 | 背景指標 |
| `wages` | 新北市官方年齡組薪資 | 2019～2024 | 新北市整體 | 年齡組 proxy |
| `college_majors` | 新北市大專校院科系、學生、教師 | 學年度 105～114 | 新北市整體 | 背景指標 |
| `graduate_majors` | 全國科系畢業人數 | 學年度 106～114 | 全國 | 背景指標 |
| `vt_courses` | 公共職訓課程區域數量 | 2026-09-01 取得的快照 | 2 區 | 背景指標 |
| `training_numbers` | 新北市訓練課程、人數與費用 | 2026-08-14～2027-01-16 | 新北市整體 | 背景指標 |
| `talent_demand` | 全國職類人才需求與僱用 | 2013～2025 | 全國 | 背景指標 |
| `youth_budgets` | 青年局年度預算「計畫及預算統計表」 | ROC 112、113 法定預算；ROC 114、115 法定版；ROC 116 預算案 | organization | 背景指標 |
| `bus_stops` | TDX 公車站點與業者 | 2026-09-03 快照 | 新北市 29 區／未對應 | 背景指標 |
| `railway_stops` | 臺鐵、高鐵、捷運及輕軌站點 | 2026-09-03 取得的快照 | 新北市 18 區 | 背景指標 |
| `bike_stops` | YouBike 靜態站點與容量 | 2026-09-04 快照 | 新北市 29 區／未對應 | 背景指標 |
| `babysitting_places` | 私立托嬰機構與公共托育中心名冊 | 最新年度 snapshot | 新北市 29 區／未對應 | 背景指標 |

## 1. `population`：人口資料

### 資料名稱與統計內容

內政部戶政 ODRP014 村里戶數及單一年齡人口。transform 將村里資料彙總成行政區月份，保留全體人口，並加總 18～35 歲男性、女性及總人口。

### 處理後 Keys

共同 Keys，加上：

- `source_record_ids`：被彙總的村里來源 ID。
- `raw_records`：被彙總的原始村里資料。
- `metric_id` 可為 `people_total`、`youth_18_35_male`、`youth_18_35_female`、`youth_18_35_total`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_scope | youth_eligibility |
|---|---|---|---:|---|---|---|
| 板橋區 | 2026-07-01 | people_total | 548271 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | youth_18_35_male | 54892 | people | derived_18_35 | eligible |
| 板橋區 | 2026-07-01 | youth_18_35_female | 51581 | people | derived_18_35 | eligible |
| 板橋區 | 2026-07-01 | youth_18_35_total | 106473 | people | derived_18_35 | eligible |
| 三重區 | 2026-07-01 | people_total | 382569 | people | all_ages | context_only |

### 其他說明

- 代表檔：`data/curated/population.json`；歷史檔在 `data/curated/population/{yyyMM}.json`。
- 可用民國年月為 10701～11507，共 102 個月，11308 缺資料；10501～10612 來源查無資料。
- 每月 29 區，最新檔 116 筆，即 29 區 × 4 個指標。

## 2. `movement`：人口遷徙資料

### 資料名稱與統計內容

內政部戶政 ODRP011 村里遷入遷出資料。transform 彙總至行政區月份，保存遷入、遷出來源／去向、性別、總遷入、總遷出與淨遷徙等 59 個指標。

### 處理後 Keys

共同 Keys，加上 `source_record_ids`、`raw_records`。實際遷徙分類放在 `metric_id`，例如 `in_total_m`、`out_total_f`、`movement_in_total`、`movement_out_total`、`net_movement_total`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_scope | youth_eligibility |
|---|---|---|---:|---|---|---|
| 板橋區 | 2026-07-01 | in_foreign_f | 62 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_foreign_m | 40 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_fu_f | 11 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_fu_m | 11 | people | all_ages | context_only |
| 板橋區 | 2026-07-01 | in_kh_f | 22 | people | all_ages | context_only |

### 其他說明

- 代表檔：`data/curated/movement.json`；歷史檔在 `data/curated/movement/{yyyMM}.json`。
- 可用民國年月為 10701～11507，共 102 個月，11308 缺資料；10501～10612 來源查無資料。
- 最新月份 1,711 筆，即 29 區 × 59 個指標。
- 原始資料沒有年齡欄位，只能作青年環境背景，不能視為 18–35 歲遷徙。

## 3. `births`：18–35 歲生母出生數

### 資料名稱與統計內容

內政部戶政 ODRP056 出生統計。只加總生母年齡 18～35 歲，並彙總為行政區年度出生數。

### 處理後 Keys

共同 Keys，加上：

- `according`：統計依據，例如「按發生日期分」。
- `raw_records`：該區年度被彙總的來源列。
- `metric_id` 固定為 `births_mother_age_18_35`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_min | age_max | youth_eligibility |
|---|---|---|---:|---|---:|---:|---|
| 板橋區 | 2025-01-01 | births_mother_age_18_35 | 1293 | births | 18 | 35 | eligible |
| 三重區 | 2025-01-01 | births_mother_age_18_35 | 921 | births | 18 | 35 | eligible |
| 中和區 | 2025-01-01 | births_mother_age_18_35 | 878 | births | 18 | 35 | eligible |
| 永和區 | 2025-01-01 | births_mother_age_18_35 | 327 | births | 18 | 35 | eligible |
| 新莊區 | 2025-01-01 | births_mother_age_18_35 | 1200 | births | 18 | 35 | eligible |

### 其他說明

- 歷史檔在 `data/curated/births/{ROC-year}.json`。
- 實際可用民國 108～114 年，每年 29 區；105～107 與 115 年來源查無資料。
- 這是精確包含 18 與 35 歲的 `eligible` 核心青年資料。

## 4. `marriages`：結婚對數

### 資料名稱與統計內容

內政部戶政 ODRP003 結婚登記資料。transform 將村里月份加總成行政區年度結婚對數。

### 處理後 Keys

共同 Keys，加上 `raw_records`；`metric_id` 固定為 `marriage_pairs_total`。

### 前五筆實際資料

| district_name | period_start | metric_id | value | unit | age_scope | youth_eligibility |
|---|---|---|---:|---|---|---|
| 板橋區 | 2017-01-01 | marriage_pairs_total | 3495 | pairs | all_ages | context_only |
| 三重區 | 2017-01-01 | marriage_pairs_total | 2455 | pairs | all_ages | context_only |
| 中和區 | 2017-01-01 | marriage_pairs_total | 2544 | pairs | all_ages | context_only |
| 永和區 | 2017-01-01 | marriage_pairs_total | 1286 | pairs | all_ages | context_only |
| 新莊區 | 2017-01-01 | marriage_pairs_total | 2728 | pairs | all_ages | context_only |

### 其他說明

- 實際檔案：`data/curated/marriages/106.json`，共 29 區。
- 目前只有民國 106 年完整；105、107～115 年來源月份不完整或查無資料。
- 沒有配偶年齡欄位，因此不能當成 18–35 歲結婚資料。

## 5. `house_prices`：房屋實價登錄

### 資料名稱與統計內容

新北市不動產實價登錄買賣交易。保留每筆交易價格、建物面積、每平方公尺與每坪單價，不在 transform 計算中位數或 YoY。

### 處理後 Keys

共同 Keys，加上：`total_price`、`total_price_unit`、`building_area`、`building_area_unit`、`price_per_sqm`、`price_per_sqm_unit`、`price_per_ping`、`price_per_ping_unit`、`transaction_type`、`snapshot_fetched_at`、`raw_record`。

### 前五筆實際資料

| district_name | period_start | total_price | building_area | price_per_ping | transaction_type |
|---|---|---:|---:|---:|---|
| 板橋區 | 2025-05-21 | 4200000 | 104.73 | 132571.895855 | 房地(土地+建物) |
| 板橋區 | 2025-05-13 | 7450000 | 45.63 | 539735.5169500001 | 房地(土地+建物) |
| 新莊區 | 2025-05-07 | 16300000 | 130.68 | 412337.17462 | 房地(土地+建物)+車位 |
| 三芝區 | 2025-05-19 | 3200000 | 52.85 | 200161.97596500002 | 房地(土地+建物) |
| 淡水區 | 2025-05-10 | 15500000 | 178.3 | 287378.50162 | 房地(土地+建物)+車位 |

### 其他說明

- 實際檔案：`data/curated/house_prices.json`，43,092 筆。
- 交易日期涵蓋 2013-03-24～2026-06-26，共 28 區，來源沒有平溪區交易。
- 3 筆來源單價為 0，`price_per_ping` 保留為 `null`，不以 0 代替。
- 無年齡欄位，只能作青年居住成本背景。

## 6. `rentals`：租賃實價登錄

### 資料名稱與統計內容

新北市租賃實價登錄。保留單筆租金、面積、每平方公尺／每坪租金與出租型態。

### 處理後 Keys

共同 Keys，加上：`rent_total`、`rent_total_unit`、`building_area`、`building_area_unit`、`rent_per_sqm`、`rent_per_sqm_unit`、`rent_per_ping`、`rent_per_ping_unit`、`rent_per_sqm_source`、`rental_type`、`snapshot_fetched_at`、`raw_record`。

### 前五筆實際資料

| district_name | period_start | rent_total | building_area | rent_per_ping | rental_type |
|---|---|---:|---:|---:|---|
| 土城區 | 2025-02-19 | 23000 | 85.8 | 885.95038 | 整戶 |
| 板橋區 | 2025-02-21 | 70000 | 274.35 | 842.975175 | 整戶 |
| 板橋區 | 2025-02-11 | 18000 | 109.51 | 542.1487400000001 | 整戶 |
| 板橋區 | 2025-02-15 | 24000 | 98.02 | 809.917325 | 整戶 |
| 土城區 | 2025-02-15 | 21000 | 61.55 | 1127.2726850000001 | 整戶 |

### 其他說明

- 實際檔案：`data/curated/rentals.json`，41,177 筆。
- 交易日期涵蓋 2025-02-11～2026-06-10，共 27 區，來源沒有坪林區、平溪區資料。
- 無年齡欄位，只能作青年租屋環境背景。

## 7. `job_vacancies`：職缺快照

### 資料名稱與統計內容

台灣就業通新北市職缺。保留每筆職缺需求人數、薪資上下限、薪資單位、截止日期及查詢品質標記。

### 處理後 Keys

共同 Keys，加上：`position_count`、`position_count_unit`、`closing_date`、`salary_type`、`salary_lower`、`salary_upper`、`salary_midpoint`、`salary_unit`、`salary_estimate_type`、`snapshot_fetched_at`、`query_truncated`、`county_name`、`raw_record`。

### 前五筆實際資料

| district_name | position_count | salary_type | salary_lower | salary_upper | salary_unit | closing_date |
|---|---:|---|---:|---:|---|---|
| 板橋區 | 5 | 月薪 | 36500 | 38000 | TWD_per_month | null |
| 板橋區 | 10 | 月薪 | 35000 | null | TWD_per_month | null |
| 板橋區 | 10 | 時薪 | 201 | null | null | null |
| 板橋區 | 5 | 月薪 | 30500 | 34000 | TWD_per_month | null |
| 板橋區 | 1 | 月薪 | 33000 | 38000 | TWD_per_month | null |

### 其他說明

- 實際檔案：`data/curated/job_vacancies.json`，3,660 筆；快照日期為 2026-09-03。
- 3,618 筆為區級、42 筆只能可靠標準化到新北市 county 層級。
- 目前 3,660 筆 `closing_date` 全為 `null`，但 raw 有截止日期欄位，屬待修正的 transform 欄位對應問題。
- 260 筆沒有薪資下限、1,140 筆沒有薪資上限；單邊薪資不會猜測另一端。

## 8. `job_vacancy_salaries`：具薪資職缺快照

### 資料名稱與統計內容

從台灣就業通職缺中保留具可解析薪資的職缺，方便分析職缺薪資範圍，但不在 transform 計算統計量。

### 處理後 Keys

Keys 與 `job_vacancies` 相同：共同 Keys，加上 `position_count`、`position_count_unit`、`closing_date`、`salary_type`、`salary_lower`、`salary_upper`、`salary_midpoint`、`salary_unit`、`salary_estimate_type`、`snapshot_fetched_at`、`query_truncated`、`county_name`、`raw_record`。

### 前五筆實際資料

| district_name | position_count | salary_type | salary_lower | salary_upper | salary_unit | closing_date |
|---|---:|---|---:|---:|---|---|
| 板橋區 | 5 | 月薪 | 36500 | 38000 | TWD_per_month | null |
| 板橋區 | 10 | 月薪 | 35000 | null | TWD_per_month | null |
| 板橋區 | 5 | 月薪 | 30500 | 34000 | TWD_per_month | null |
| 板橋區 | 1 | 月薪 | 33000 | 38000 | TWD_per_month | null |
| 板橋區 | 3 | 月薪 | 29500 | null | TWD_per_month | null |

### 其他說明

- 實際檔案：`data/curated/job_vacancy_salaries.json`，2,893 筆；快照日期為 2026-09-03。
- 2,886 筆為區級、7 筆為 county 層級；769 筆只有薪資下限。
- `closing_date` 目前同樣全部為 `null`，需先修正後才能分析職缺有效期限。

## 9. `wages`：新北市年齡組薪資

### 資料名稱與統計內容

官方表 6 的新北市年度薪資資料。保留官方年齡組及統計方式，不將「未滿 25 歲」「25–29 歲」「30–39 歲」拼成虛假的 18–35 歲數值。

### 處理後 Keys

共同 Keys，加上：`county_name`、`official_age_group`、`statistic_method`、`raw_record`。

### 前五筆實際資料

| period_start | county_name | official_age_group | statistic_method | value | unit | youth_eligibility |
|---|---|---|---|---:|---|---|
| 2024-01-01 | 新北市 | 總計 | 平均數 | 71.1 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 未滿30歲 | 平均數 | 56.7 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 未滿25歲 | 平均數 | 48.3 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 25-29歲 | 平均數 | 59.9 | 萬元 | proxy_only |
| 2024-01-01 | 新北市 | 30-39歲 | 平均數 | 69 | 萬元 | proxy_only |

### 其他說明

- 歷史檔在 `data/curated/wages/{ROC-year}.json`。
- 實際可用民國 108～113 年，即 2019～2024；105～107、114、115 年來源無資料。
- 粒度只有新北市整體，不能推估 29 區差異；全部標記為 `proxy_only`。

## 10. `college_majors`：新北市大專校院科系

### 資料名稱與統計內容

教育部資料集 9621 與 9622。以學年度、學校、科系、日／進修、等級與體系配對，保留學生、教師、上學年度畢業生及男女／年級學生明細。

### 處理後 Keys

共同 Keys，加上：`county_name`、`academic_year`、`school_code`、`school_name`、`department_code`、`department_name`、`student_count`、`teacher_count`、`previous_graduate_count`、`detail_student_count`、`male_student_count`、`female_student_count`、`detail_counts`、`overview_raw_record`、`detail_raw_record`、`detail_raw_records`。

### 前五筆實際資料

| school_name | department_name | student_count | teacher_count | previous_graduate_count | detail_student_count | male_student_count | female_student_count |
|---|---|---:|---:|---:|---:|---:|---:|
| 國立臺北大學 | 歷史學系 | 28 | 0 | 4 | 28 | 19 | 9 |
| 國立臺北大學 | 歷史學系 | 182 | 14 | 32 | 182 | 85 | 97 |
| 國立臺北大學 | 民俗藝術與文化資產研究所 | 40 | 5 | 3 | 40 | 19 | 21 |
| 國立臺北大學 | 應用外語學系 | 243 | 12 | 51 | 243 | 73 | 170 |
| 國立臺北大學 | 創新華語文教學學士學位學程 | 35 | 2 | 0 | 35 | 10 | 25 |

### 其他說明

- 歷史檔在 `data/curated/college_majors/{academic-year}.json`。
- 學年度 105～114 可用；115 尚無資料。資料是學校所在地為新北市的 county 粒度，不是學生戶籍行政區。
- 學年度 105～112 沒有 detail 資料。114 年 919 筆中，101 筆 overview 無法配到 detail、8 筆 detail 無法配到 overview；分析男女或年級前應檢查 `quality_flags`。

## 11. `graduate_majors`：全國科系畢業人數

### 資料名稱與統計內容

教育部資料集 9620，依學年度、學門分類與科系統計男女及總畢業人數。

### 處理後 Keys

共同 Keys，加上：`academic_year`、`classification_code`、`classification_name`、`department_name`、`graduate_male_count`、`graduate_female_count`、`graduate_count`、`raw_record`。

### 前五筆實際資料

| academic_year | classification_name | department_name | graduate_male_count | graduate_female_count | graduate_count |
|---|---|---|---:|---:|---:|
| 114 | 綜合教育細學類 | 人文社會學院教育經營碩士在職專班 | 1 | 11 | 12 |
| 114 | 綜合教育細學類 | 人文社會學院教育經營碩士班 | 0 | 2 | 2 |
| 114 | 綜合教育細學類 | 文教事業經營研究所 | 2 | 9 | 11 |
| 114 | 綜合教育細學類 | 文教事業經營研究所 | 5 | 13 | 18 |
| 114 | 綜合教育細學類 | 文教事業經營碩士在職學位學程 | 0 | 4 | 4 |

### 其他說明

- 歷史檔在 `data/curated/graduate_majors/{academic-year}.json`。
- 學年度 106～114 可用；105、115 無資料。114 年代表檔共 5,391 筆。
- 來源沒有縣市欄位，因此是全國資料，不能直接代表新北市青年畢業供給。

## 12. `vt_courses`：公共職業訓練課程數

### 資料名稱與統計內容

勞動部公共職訓課程。transform 依行政區去重課程 ID，產生各區不重複課程數。

### 處理後 Keys

共同 Keys，加上：`course_ids`、`raw_records`；`metric_id` 固定為 `distinct_course_count`。

### 實際資料

此資料處理後只有 2 筆，因此列出全部資料：

| district_name | metric_id | value | unit | course_ids（前 3 個） |
|---|---|---:|---|---|
| 五股區 | distinct_course_count | 32 | courses | 156211, 156212, 156243 ...(+29) |
| 泰山區 | distinct_course_count | 42 | courses | 156309, 156311, 156357 ...(+39) |

### 其他說明

- 實際檔案：`data/curated/vt_courses.json`；2026-09-01 取得 74 筆 raw，彙總成五股、泰山 2 筆。
- raw 有「訓練期間」，但目前 curated 的 `period_start`、`period_end`、`period_type` 都是 `null`，屬待補的期間標準化問題。

## 13. `training_numbers`：訓練課程、人數與費用

### 資料名稱與統計內容

勞動部新北市訓練課程資料，保留課程代碼、名稱、訓練期間、時數、訓練人數與每人費用。

### 處理後 Keys

共同 Keys，加上：`county_name`、`course_code`、`course_name`、`training_hours`、`training_hours_unit`、`training_people`、`training_people_unit`、`fee_per_person`、`fee_per_person_unit`、`raw_record`。

### 前五筆實際資料

| county_name | period_start | period_end | course_code | course_name | training_hours | training_people | fee_per_person |
|---|---|---|---|---|---:|---:|---:|
| 新北市 | 2026-08-23 | 2026-10-18 | 172991 | 新多益聽力與閱讀能力培訓班 | 47 | 22 | 9180 |
| 新北市 | 2026-08-25 | 2026-10-13 | 173075 | 貴金屬成型銼焊與精緻飾品設計實務班 | 54 | 25 | 11800 |
| 新北市 | 2026-08-30 | 2026-11-08 | 173092 | 永生花藝與香氛石文創商品設計實務班 | 54 | 20 | 10000 |
| 新北市 | 2026-08-23 | 2026-11-29 | 173309 | 沙龍凝膠彩繪美甲設計班 | 77 | 25 | 17800 |
| 新北市 | 2026-09-03 | 2026-09-29 | 172979 | 甲種職業安全衛生業務主管教育訓練班 | 42 | 16 | 8000 |

### 其他說明

- 實際檔案：`data/curated/training_numbers.json`，87 筆。
- 課程期間涵蓋 2026-08-14～2027-01-16。
- 只有新北市 county 粒度，沒有可靠行政區，也沒有年齡欄位。

## 14. `talent_demand`：人才需求與僱用

### 資料名稱與統計內容

勞動部全國職類人才需求資料，按年度及職類保存新增需求、新僱用及有效僱用人次。

### 處理後 Keys

共同 Keys，加上：`occupation`、`new_demand_count`、`new_hired_count`、`valid_hired_count`、`count_unit`、`raw_record`。

### 前五筆實際資料

| period_start | occupation | new_demand_count | new_hired_count | valid_hired_count | count_unit |
|---|---|---:|---:|---:|---|
| 2013-01-01 | 民意代表、主管及經理人員 | 14989 | 2457 | 7243 | person_times |
| 2013-01-01 | 專業人員 | 118899 | 20222 | 58297 | person_times |
| 2013-01-01 | 技術員及助理專業人員 | 367366 | 90907 | 219061 | person_times |
| 2013-01-01 | 事務支援人員 | 100277 | 25018 | 56095 | person_times |
| 2013-01-01 | 服務及銷售工作人員 | 273045 | 59743 | 170511 | person_times |

### 其他說明

- 實際檔案：`data/curated/talent_demand.json`，117 筆，涵蓋 2013～2025。
- 來源是全國資料，不是新北市或 29 區資料，也沒有年齡欄位。

## 15. `bus_stops`：TDX 公車站點

### 資料名稱與統計內容

TDX 新北市公車站點，合併 Stop 與 StopOfRoute 的營運業者，並用座標對應新北市行政區。

### 處理後 Keys

共同 Keys，加上：`station_id`、`source_station_id`、`name_zh`、`name_en`、`latitude`、`longitude`、`operators`、`raw_record`。

### 前五筆實際資料

| station_id | name_zh | district_name | latitude | longitude | operators |
|---|---|---|---:|---:|---|
| NWT10353 | 管理中心 | 新莊區 | 25.063771 | 121.457635 | 三重客運 |
| NWT10354 | 標準廠房 | 新莊區 | 25.06504 | 121.456024 | 三重客運 |
| NWT10355 | 五權三五工路口 | 五股區 | 25.065315 | 121.453673 | 三重客運 |
| NWT10356 | 勞工活動中心 | 新莊區 | 25.06236578 | 121.450092 | 三重客運 |
| NWT10357 | 工商展覽中心 | 五股區 | 25.065092 | 121.449031 | 三重客運 |

### 其他說明

- 實際檔案：`data/curated/bus_stops.json`，32,994 筆；快照日期 2026-09-03。
- 28,845 筆可映射到 29 區，4,149 筆座標無法可靠映射，保留 `district_id=null`，不以最近行政區猜測。
- 無年齡欄位，只能作交通可及性背景資料。

## 16. `railway_stops`：TDX 軌道站點

### 資料名稱與統計內容

TDX 臺鐵、高鐵、捷運與新北輕軌站點，保留軌道系統、運具類型及所屬路線，並以座標對應行政區。

### 處理後 Keys

共同 Keys，加上：`station_id`、`source_station_id`、`name_zh`、`name_en`、`latitude`、`longitude`、`rail_system`、`transport_type`、`line_ids`、`line_nos`、`raw_record`。

### 前五筆實際資料

| station_id | name_zh | district_name | latitude | longitude | rail_system | line_ids |
|---|---|---|---:|---:|---|---|
| TRA-0950 | 五堵 | 汐止區 | 25.07799 | 121.66758 | TRA | WL |
| TRA-0960 | 汐止 | 汐止區 | 25.0679 | 121.66113 | TRA | WL |
| TRA-0970 | 汐科 | 汐止區 | 25.06406 | 121.65233 | TRA | WL |
| TRA-1020 | 板橋 | 板橋區 | 25.01434 | 121.46377 | TRA | WL |
| TRA-1030 | 浮洲 | 板橋區 | 25.00419 | 121.44477 | TRA | WL |

### 其他說明

- 實際檔案：`data/curated/railway_stops.json`，104 筆，全部成功映射，分布於 18 個行政區。
- 本次取得時間為 2026-09-03；個別來源列的更新日期介於 2023-08-03～2026-09-03。
- 無年齡欄位，只能作交通環境背景。

## 17. `bike_stops`：TDX YouBike 站點

### 資料名稱與統計內容

TDX 新北市 YouBike 靜態站點，保留站點名稱、座標與容量。collector 可選擇合併即時可借／可還數量，但本次執行只抓靜態站點。

### 處理後 Keys

共同 Keys，加上：`station_id`、`source_station_id`、`name_zh`、`name_en`、`latitude`、`longitude`、`capacity`、`availability`、`available_rent_bikes`、`available_return_bikes`、`static_data`、`raw_record`。

### 前五筆實際資料

| station_id | name_zh | district_name | latitude | longitude | capacity | available_rent_bikes | available_return_bikes |
|---|---|---|---:|---:|---:|---|---|
| NWT500201001 | YouBike2.0_下庄市場 | 八里區 | 25.14678 | 121.3999 | 20 | null | null |
| NWT500201002 | YouBike2.0_八里行政中心 | 八里區 | 25.15397 | 121.40721 | 20 | null | null |
| NWT500201003 | YouBike2.0_八里中庄市場綜合大樓 | 八里區 | 25.15993 | 121.41407 | 28 | null | null |
| NWT500201004 | YouBike2.0_大崁國小 | 八里區 | 25.16064 | 121.41938 | 20 | null | null |
| NWT500201006 | YouBike2.0_龍形停車場 | 八里區 | 25.13041 | 121.4513 | 40 | null | null |

### 其他說明

- 實際檔案：`data/curated/bike_stops.json`，1,600 筆；快照日期為 2026-09-04。
- 1,595 筆可映射到 29 區，5 筆座標無法可靠映射並保留 `district_id=null`。
- 本次未啟用 `include_availability=True`，因此 `availability`、`available_rent_bikes`、`available_return_bikes` 為 `null`；這不是即時可借／可還資料。

## 18. `youth_budgets`：青年局年度預算

### 資料名稱與統計內容

資料來自新北市政府青年局官方預算公告列表，collector 動態追蹤詳情 URL，下載 PDF 後只抽取「計畫及預算統計表」。2026-09-09 的實際 range output 發現 5 份文件、5 個 PDF artifact、20 筆 raw row 與 20 筆 curated row，且沒有文件解析失敗：

| budget_year_roc | document_status | document_status_label | published_date | updated_date | source_page_number | row_count |
|---|---|---|---|---|---:|---:|
| 116 | `proposed_budget` | 預算案 | 115-09-01 | 115-09-01 | 28 | 4 |
| 115 | `legal_budget` | 法定版 | 114-09-30 | 115-02-09 | 28 | 4 |
| 114 | `legal_budget` | 法定版 | 113-08-29 | 114-02-10 | 26 | 4 |
| 113 | `legal_budget` | 法定預算 | 113-01-29 | 113-01-29 | 27 | 4 |
| 112 | `legal_budget` | 法定預算 | 113-10-11 | 113-10-11 | 25 | 4 |

### 實際 curated rows

| budget_year_roc | document_status | row_type | business_plan | value | budget_ratio_percent | period_start |
|---|---|---|---|---:|---:|---|
| 116 | proposed_budget | total | 新北市政府青年局合計 | 220101 | 100.00 | 2027-01-01 |
| 116 | proposed_budget | detail | 一般行政 | 60280 | 27.39 | 2027-01-01 |
| 116 | proposed_budget | detail | 青年發展業務 | 159521 | 72.47 | 2027-01-01 |
| 116 | proposed_budget | detail | 第一預備金 | 300 | 0.14 | 2027-01-01 |
| 115 | legal_budget | total | 新北市政府青年局合計 | 213022 | 100.00 | 2026-01-01 |
| 115 | legal_budget | detail | 一般行政 | 56819 | 26.67 | 2026-01-01 |
| 115 | legal_budget | detail | 青年發展業務 | 155903 | 73.19 | 2026-01-01 |
| 115 | legal_budget | detail | 第一預備金 | 300 | 0.14 | 2026-01-01 |
| 114 | legal_budget | total | 新北市政府青年局合計 | 196153 | 100.00 | 2025-01-01 |
| 114 | legal_budget | detail | 一般行政 | 52645 | 26.84 | 2025-01-01 |
| 114 | legal_budget | detail | 青年發展業務 | 143208 | 73.01 | 2025-01-01 |
| 114 | legal_budget | detail | 第一預備金 | 300 | 0.15 | 2025-01-01 |
| 113 | legal_budget | total | 新北市政府青年局合計 | 158650 | 100.00 | 2024-01-01 |
| 113 | legal_budget | detail | 一般行政 | 51228 | 32.29 | 2024-01-01 |
| 113 | legal_budget | detail | 青年發展業務 | 107122 | 67.52 | 2024-01-01 |
| 113 | legal_budget | detail | 第一預備金 | 300 | 0.19 | 2024-01-01 |
| 112 | legal_budget | total | 新北市政府青年局合計 | 149029 | 100.00 | 2023-01-01 |
| 112 | legal_budget | detail | 一般行政 | 51291 | 34.42 | 2023-01-01 |
| 112 | legal_budget | detail | 青年發展業務 | 97438 | 65.38 | 2023-01-01 |
| 112 | legal_budget | detail | 第一預備金 | 300 | 0.20 | 2023-01-01 |

### 其他說明

- curated output：`curated/youth_budgets/all.json`；raw envelope 的 `documents` 有 5 筆、`source_artifacts` 有 5 筆，PDF 存在 `raw/youth_budgets/artifacts/`。
- `value` 單位為 `TWD_thousand`，保留來源千元，不換算成元；`budget_ratio_percent` 是來源提供的比率，不由 pipeline 重算。
- 所有 curated rows 的 `geo_level` 是 `organization`，`district_id` 與 `district_name` 是 JSON `null`，`youth_eligibility` 是 `context_only`；不可拆配到新北市 29 區，也不是精確 18–35 歲指標。
- 列表頁目前可發現的文件不代表歷史年度完整性；若要追蹤新版本，應重新執行 collector 並保留新的 raw snapshot 與 PDF hash。

## 19. `babysitting_places`：私托與公托名冊

### 資料名稱與統計內容

資料來自新北市政府資料開放平台的「新北市私立托嬰機構名冊」與「新北市公共托育中心名冊」。兩個來源都標示為每年更新；collector 每次執行都抓取兩個 JSON endpoint，使用 `page`／`size` 分頁取得完整名冊，再合併為同一個 canonical dataset，並以 `care_type` 區分 `private` 與 `public`。未帶分頁參數的 endpoint 只提供 30 筆預覽，不能直接當成完整資料。

### 處理後 Keys

共同 Keys，加上：

- `care_type`：`private` 或 `public`。
- `facility_name`：私托使用來源 `title`，公托使用來源 `name`。
- `operator_name`：公托使用來源 `unit`；私托沒有此欄位時為 `null`。
- `county_name`、`county_code`：來源縣市欄位。
- `source_district_name`、`source_district_code`：來源 `area`／`town` 與 `areacode`。
- `address`、`phone`：來源地址與聯絡電話。
- `capacity`：私托來源 `person` 解析後的可收托人數；公托來源沒有此欄位時為 `null`。
- `capacity_unit`：有 `capacity` 時為 `child_slots`，缺失時為 `null`。
- `source_dataset_id`、`source_row_id`：來源資料集與來源序號。
- `raw_record`：未覆寫的來源列與 collector 加入的來源類型標記。

### 前五筆實際資料

| care_type | facility_name | district_name | address | phone | capacity | capacity_unit |
|---|---|---|---|---|---:|---|
| private | 茵幼爾股份有限公司附設新北市私立寶貝媽咪托嬰中心 | 板橋區 | 莊敬路46號2樓 | (02)82529955 | 90 | child_slots |
| private | 新北市私立卡爾威特托嬰中心 | 板橋區 | 板新路101號1樓、107號2樓 | (02)89518905 | 140 | child_slots |
| private | 新北市私立捧馨園托嬰中心 | 板橋區 | 四川路1段151號 | (02)29563008 | 25 | child_slots |
| private | 新北市私立喜閱寶寶托嬰中心 | 板橋區 | 廣和街61號1.2樓 | (02)89516588 | 30 | child_slots |
| private | 新北市私立卡爾威特托嬰中心亞東園 | 板橋區 | 南雅南路2段144巷66號 | (02)89664098 | 32 | child_slots |

### 其他說明

- 實際檔案：`data/curated/babysitting_places/latest.json`，391 筆；私托 261 筆、公托 130 筆；快照日期為 2026-09-09。
- 來源 API：私托 <https://data.ntpc.gov.tw/api/datasets/69cecdb0-7796-48df-84e5-99e4f1274245/json>；公托 <https://data.ntpc.gov.tw/api/datasets/b3faf2aa-e96b-4f2f-b647-da47dc094860/json>。
- 完整查詢使用 `?page=0&size=1000`，collector 會持續分頁直到取得完整名冊。
- 官方資料頁：<https://data.ntpc.gov.tw/datasets/69cecdb0-7796-48df-84e5-99e4f1274245>、<https://data.ntpc.gov.tw/datasets/b3faf2aa-e96b-4f2f-b647-da47dc094860>。
- 此資料集是 `snapshot` source strategy，不把目前名冊複製成過去年度。輸出位置為 `data/raw/babysitting_places/`、`data/curated/babysitting_places/latest.json`、`data/quality/babysitting_places/latest.json` 與 `data/quarantine/babysitting_places/latest.json`。
- 執行命令：`PYTHONPATH=src .venv/bin/python src/run_pipeline.py --refresh-profile monthly --datasets babysitting_places --output-dir data`。此命令只更新 `babysitting_places`。
- `areacode` 優先用來對應 `config/districts.json`；無法可靠對應時保留 `district_id=null`，不使用最近行政區猜測。
- `capacity` 只代表來源列提供的私托可收托人數；公托沒有此欄位時保留為 `null`，不補成 0。
- 資料沒有年齡欄位，因此 `age_scope=not_age_specific`、`youth_eligibility=context_only`，只能作托育資源背景，不是 18–35 歲核心指標。
- 公托與私托的定義、欄位與更新內容由來源機關維護；兩者可以分別統計，也可以用 `care_type` 做資源比較。
- 若需行政區托育據點數、私托容量總和或人均資源，應在 `analytics/` 依可靠 `district_id` 計算；collector 與 transform 只保存單一機構資料。

## 使用建議

1. Analytics 應先按 `youth_eligibility` 篩選：核心青年指標只用 `eligible`。
2. 區級比較只能使用 `geo_level=district` 且 `district_id` 不為 `null` 的資料。
3. `county` 或 `national` 資料與行政區資料並用時，必須標示為 proxy 或背景比較。
4. 房價、租金、職缺與交通目前都是明細／快照；中位數、YoY、密度或綜合指數應在 `analytics/` 計算。
5. 在修正 authoritative index 前，不能只讀最新 `dataset_index.json` 來判斷完整歷史資料範圍。
