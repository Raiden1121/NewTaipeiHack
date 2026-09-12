# Analytics 指標盤點：計算方式、資料改動規則與缺漏清單

盤點對象：`data-pipeline/src/analytics/`（16 檔、5,398 行）與 `data-pipeline/data/`。
盤點時間：2026-09-12。方法：閱讀全部 analytics 模組 + 實際重跑 7 個 metric + 執行 56 個 analytics 相關測試 + 逐一比對 curated / quality / analytics 產物。

> 重跑是在備份後於 `--output-dir data` 實測，測完已完整還原，工作目錄維持乾淨（`git status` 無變更）。

---

## 〇、修復進度（2026-09-12 更新）

第二至四節是**盤點當下**的狀態記錄。階段一與階段二的修復已完成，以下項目的現況已與盤點時不同：

| 盤點時的問題 | 現況 | 做法 |
|---|---|---|
| `youth_topic_weight`／`youth_keyword_frequency` CLI 崩潰 | ✅ 已解 | `dataset_index.json` 重建；7 個 metric 全部可跑 |
| `youth_topic_weight` 的 `join_input_rows: 0` | ✅ 已解 | **0 → 22,782**；年度從 `[110,112,114]` 變成 `[109…115]` |
| `join_proposals` 2025 只有 19 筆、2026 只有 3 筆 | ✅ 已解 | collector 改為由當年往回推年度直接構造 URL；curated **9,703 → 22,782 筆** |
| `join_proposals` 約 7% 提案年度為 null | ✅ 已解 | 修正 `_first_value` 讓 `提送日期: '無'` 這個 sentinel 不再擋住 `publishDate` fallback |
| `youth_grants` ROC 111 短報 24% | ✅ 已解 | 修正 PDF 折行合併與 recipient marker 誤判；**24 列/1,194 → 74 列/1,577 千元**，與 PDF「青年局小計」對帳一致 |
| `youth_grants` 全年與第一季畫在同一條線 | ✅ 已解 | 新增 `coverage_scope`；trend 只保留同口徑的 112–115，111 移入 `coverage.excluded_years` |
| 選舉 103／107 參選率全為 null | ✅ 已解 | `population/10312` 接入官方單一年齡歷史 archive；`10312/10712/11112` 年末 anchor 固定保留。三屆參選率與 YRR 均有值。 |
| V1 里長整列被標 `unavailable` | ✅ 已解 | 拆成 `counts_status` 與 `status`。**青年里長占比三屆都有值：103 = 1.84%、107 = 1.36%、111 = 3.00%**，29 區齊全 |
| `bus_stops` 走 legacy 平面檔 | ✅ 已解 | `sourcePeriods.bus_stops` 從 `legacy_flat_snapshot` 變 `11509` |
| `college_majors` 406 讓 retention 全域停擺 | ✅ 已解 | 參照表抓取加上針對暫時性 HTTP 狀態的重試；該 unit 現為 `no_data`，retention 恢復執行 |
| retention 可能靜默抹掉 index entry | ✅ 已解 | `_prune_dataset_index` 不再丟棄它不認識的條目 |
| 缺值沒有可解釋的原因 | ✅ 已解 | 新增 `config/data_gaps.json` 與 `analytics/data_gaps.py`；quality 產出 `source_limitations`，每個 reason code 都有實測依據 |

**仍維持原判斷（來源端拿不到）**：ODRP014 的 ROC 103 月份（但 `population/10312` 已由官方歷史 archive 補入）、`wages` 114、`youth_budgets` 110/111 法定預算與 111/112 決算、`youth_grants` 的行政區、`vt_courses` 僅兩區、`training_numbers`／`talent_demand` 無區級。詳見 §4.2 與 `config/data_gaps.json`。

**未動（階段三）**：會議紀錄拆場次與關鍵字表、`--period` 模式修正、YOI 口徑。

`published snapshot` 整併已完成：目前由 `dev-full-20260912` 統一提供 homepage
與六個分析；詳見 §4.5。以下 §1–§4 的盤點數字仍保留作為修復前的歷史紀錄。

測試：**411 passed**（盤點時 386）。

---

## 一、結論摘要

### 1.1 指標是否都算好了？—— 5 個好了、2 個算不出來、2 個內容過期

| Metric | CLI 可執行 | 輸出檔存在 | 內容是否為最新 code 產出 | 狀態 |
|---|---|---|---|---|
| `homepage` | ✅ | ✅ | ❌ **過期** | 可跑但檔案是舊版 |
| `employment` | ✅ | ✅ | ✅ 一致 | OK |
| `fertility` | ✅ | ✅ | ✅ 一致 | OK |
| `policy_support` | ✅ | ✅ | ✅ 一致 | OK |
| `youth_participation` | ✅ | ✅ | ❌ **過期** | 可跑但檔案是舊版 |
| `youth_topic_weight` | ❌ **失敗** | ⚠️ 舊降級檔 | ❌ | **壞掉** |
| `youth_keyword_frequency` | ❌ **失敗** | ⚠️ 舊檔 | ❌ | **壞掉** |

程式碼本身健康：`test_homepage_analytics` 等 14 個測試檔共 **56 tests passed**。問題全部出在資料與索引，不在計算邏輯。

### 1.2 三個必須先修的問題

**(A) `dataset_index.json` 少了 6 個資料集，導致 2 個指標直接崩潰**

```
ValueError: dataset 'join_proposals' is not present in dataset index
  at src/analytics/io.py:35  ← load_curated_dataset()
  by src/run_analytics.py:224
```

`data/quality/dataset_index.json` 目前只列 20 個資料集。curated 目錄裡有、但 index 裡沒有的：

| 資料集 | curated 實際檔案 | 後果 |
|---|---|---|
| `join_proposals` | `all.json`（9,703 筆） | **`youth_topic_weight`、`youth_keyword_frequency` CLI 直接 raise** |
| `youth_council_minutes` | `all.json`（55 筆） | 同上 |
| `bus_stops` | `bus_stops.json`（平面舊檔，2026-09-04） | homepage 走 legacy fallback，`source_period` 被標成 `legacy_flat_snapshot` |
| `movement` | 68 個月分割 + 平面檔 | 無 analytics 消費（見 §4.4） |
| `graduate_majors` | 66 個期間檔 | 無 analytics 消費 |
| `marriages` | **目錄是空的** | 無資料也無指標 |

為什麼 `youth_participation` 沒炸？因為它走 `HomepageInputResolver.all_available()`，那條路徑在 index 查不到時會 fallback 去直接讀 `curated/{dataset}/all.json`（[input_resolver.py:84-108](data-pipeline/src/analytics/input_resolver.py#L84-L108)）。`run_analytics.py` 的 topic/keyword 分支則是直接呼叫 `load_curated_dataset()`，沒有 fallback，所以硬失敗。

這也表示：**`youth_participation` 目前是靠一條「相容用」的非授權路徑在讀資料**，而 `data-pipeline.md` 明訂「analytics 應只讀這份 index」。

**(B) `data/analytics/youth_topic_weight/all.json` 是 join 資料讀不到時的降級結果**

`quality/analytics_youth_topic_weight.json` 寫著 `join_input_rows: 0`，輸出裡 22 個議題每年的 `join_mentions` 全是 0、`join_support_score` 全是 0.0。等於文字雲權重**只由 55 筆會議紀錄決定**，9,703 筆 join 提案（其中 1,538 筆 `youth_topic_proxy=true`）完全沒進計算。

對照 `youth_keyword_frequency`（2026-09-11 01:55 產出，當時還讀得到）：`join_input_rows: 9703`。兩個指標的口徑目前不一致。

**(C) `homepage` / `youth_participation` 的現存 JSON 是舊 code 產出**

重跑後與現存檔不一致（`employment`/`fertility`/`policy_support` 則完全一致）。輸入 row_count 逐一比對後完全相同，所以**差異來自 code 改過而輸出沒重跑**：

| 變動 | 舊檔 | 重跑後 |
|---|---|---|
| `excluded.job_vacancy_salaries` | `midpoint_rows` | 改名 `complete_midpoint_rows`，新增 `complete_salary_position_count: 8335`、`unmapped_district_rows: 7` |
| `excluded.job_vacancies` | 不存在 | 新增（`total_position_count: 14350`、`unmapped_district_rows: 44`） |
| `high_salary_ratio` | 以「職缺筆數」為分母 | 改以 `position_count` 加權 |
| 連帶影響 | — | **29 區的 `yoiComponents.salary` 與 `opportunityIndex` 全部改變，4 區 `retentionRiskLevel` 改變** |
| `service_coverage.districts[]` / `villages[]` | 只有 `covered_youth`/`youth_population` | 新增泛用欄位 `covered_population`/`target_population` |
| 選舉 103／107 年 `youth_candidacy_rate` | 有值（例 0.2232） | **全部變 `null`**（見 §4.1 第 2 項） |

最後一項是**資料退化**，不是 code 改進：舊檔有值是因為當時 curated 還留著 103／107 年的 population，現在 `curated/population` 只剩 `11001`–`11507`。

---

## 二、指標怎麼算

共 7 個 metric、由 `src/run_analytics.py --metric <name>` 驅動。時間與權重政策集中在 `config/homepage_analytics.json`：

```json
{ "annual_years_roc": [110,111,112,113,114],
  "population_reference_year_roc": 114,
  "election_years_roc": [103,107,111],
  "service_radius_m": 2500,
  "normalization": { "method": "min_max", "constant_value": 50 },
  "yoi_weights": { "job":0.25, "salary":0.25, "talent":0.15, "housing":0.20, "transport":0.15 } }
```

### 2.1 共用數學工具（`homepage_math.py`）

| 函式 | 公式 | 用途 |
|---|---|---|
| `normalize_minmax` | `(x-min)/(max-min)×100`，不做 P5/P95 截斷；`inverse=True` 取 `100-x` | 所有現行 YOI 分項、FaFI 分項 |
| `shannon_entropy` | `-Σ pᵢ log₂ pᵢ`（pᵢ = 該職類職缺數／總職缺數） | 職業多樣性 |
| `weighted_score` | `Σ(wᵢ·xᵢ)/Σwᵢ`，**只累加有值的項目**（null 不計入分母） | 五大分項與 YOI 合成 |
| `calculate_quartile_risk` | `≤Q1 → high`、`≥Q3 → low`、其餘 `medium`、null → `unavailable` | 留才風險分級 |
| `calculate_ols_regression` | 純 Python OLS，回傳 `slope`/`intercept`/`r_squared`/`sample_size`；有效點 <2 或 `ss_xx≈0` 時全部回 null | 三張散布圖的趨勢線 |

共同原則：**Min-Max 上下界相等時全部給 `constant_value=50`；缺值一律 `null`，絕不補 0。**

### 2.2 `homepage` —— 青年機會指數 YOI（29 區）

輸入 19 個資料集。核心是把目前使用的原始欄位正規化後，兩層加權合成；舊版
全區相同或房價推算欄位仍保留在 payload 供相容性與散點圖使用，但不再參與 YOI。

**第 1 層：目前使用的原始指標與相容性欄位**

| 欄位 | 算法 | 方向 |
|---|---|---|
| `vacancies_per_km2` | 區內 `position_count` 加總 ÷ 該區面積(km²) | 正；S_job 使用 |
| `vacancies_per_10k_youth` | 區內 `position_count` 加總 ÷ 該區 18–35 人口 × 10,000 | 正；相容性欄位，不進 S_job |
| `occupation_shannon_index` | 區內職類 position_count 分布的 Shannon 熵 | 正 |
| `talent_demand_yoy` | 全國 `new_demand_count` 年度總和的 YoY %（**29 區同值**） | 相容性／背景欄位，不進 S_job |
| `salary_median` | 區內職缺薪資中位數（用上下界中點，未收縮） | 正；相容性／查核 |
| `salary_sample_size` | 可計算完整薪資中點的資料列數 | 查核欄位 |
| `salary_median_shrunk` | `(n×salary_median + 30×全市中位數)/(n+30)` | 正；S_salary 使用 |
| `high_salary_ratio` | 中點 > 全市中位數 ×1.5 的職缺 `position_count` ÷ 區內總 position_count | 正 |
| `adjusted_youth_wage` | 官方 25–29 歲平均薪資 × 房價比例的代理值 | 相容性／散點圖欄位，不進 S_salary |
| `youth_ratio` | 區內 18–35 歲人口 ÷ 區內總人口 × 100% | 正；S_talent 使用 |
| `youth_yoy` | ROC 114 對 ROC 113 的青年人口 YoY（各年取最新月份） | 正；S_talent 使用 |
| `college_student_density` | 區內大專學生數 ÷ 行政區面積(km²) | 正；S_talent 使用，學校所在地 proxy |
| `vt_course_count` | 職訓課程數；**缺區用觀測最小值補**並記 proxy | 相容性／背景欄位，不進 S_talent |
| `training_people_per_10k_youth` | 全市受訓人次 ÷ 全市青年 × 10,000（**29 區同值**） | 相容性／背景欄位，不進 S_talent |
| `rent_median` | 區內租金總額中位數；缺區用全市最小值補 | **逆** |
| `house_price_median` | 區內**住宅用**每坪房價中位數；平溪區無住宅交易時改用全類型並記 proxy | **逆** |
| `rent_wage_ratio` | `rent_median ÷ salary_median` | **逆** |
| `bus_stops_per_10k_youth` | 區內公車站數 ÷ 青年 × 10,000 | 正 |
| `railway_stop_density` | 區內軌道站數 ÷ 面積 | 正 |
| `bike_stop_density` | 區內 YouBike 站數 ÷ 面積 | 正 |

面積由 `village_boundaries` 的 EPSG:3826 polygon 面積 ÷ 1,000,000 求得（km²）。

**第 2 層：五大分項（各自 `weighted_score`）**

```
job       = 0.60 職缺密度_per_km2 + 0.40 職業多樣性
salary    = 0.60 職缺刊登薪資中位數 + 0.40 高薪職缺比例
talent    = 0.40 青年人口佔比 + 0.40 青年人口 YoY + 0.20 大專學生數密度
housing   = 0.35 租金(逆) + 0.35 房價(逆) + 0.30 租金薪資比(逆)
transport = 0.35 公車 + 0.40 軌道 + 0.25 YouBike
```

**第 3 層：**先計算
`YOI_raw = weighted_score(五大分項, yoi_weights)`，再對全部 29 區的
`YOI_raw` 做純 Min-Max norm 產生 `opportunityIndex`；最後依公開分數四分位切
`retentionRiskLevel`。輸出另保留 `yoiRaw` 供查核。

**其他 homepage 區塊**

- `kpi.cityYouthPopulation`：114 年最後一個有資料月份的 29 區 `youth_18_35_total` 加總；`YoY` 對 113 年同口徑。`nationalYouthPopulation` 是**寫死常數 4,820,000**，已標 `proxy`。
- `annual.population`：每個 ROC 年取「該年最後一個有資料的月份」為年值。
- `annual.fertility`：`18–35 歲母親生育數 ÷ 該年 18–35 歲女性「月平均」人口 × 1000`（分母 = 該年各月加總 ÷ 有資料月數）；`fertilityVsCityAvg = 區 ÷ 全市 × 100`。
- `annual.budget_trend` / `budget_execution`：法定預算與決算**分開**。`execution_rate = realized_amount ÷ 法定預算 × 100`，且單位不同時先換算（`TWD_thousand → TWD` 乘 1000），單位不相容則回 null 並記 `incompatible_budget_units`。
- `elections`：見 §2.5。
- `service_coverage`：見 §2.3。

### 2.3 服務可及性（`service_coverage.py`，homepage 與 youth_participation 共用）

1. 取 `geocode_status == "matched"` 的服務點，座標統一轉 EPSG:3826（TWD97，公尺）。
2. 每點做 `radius_m` 緩衝區，全部 `unary_union` 成一個覆蓋面。
3. 對每個里：`ratio = (覆蓋面 ∩ 里界).area / 里界.area`，clip 到 [0,1]。
4. `covered_population = ratio × 該里目標人口`（**假設人口在里內均勻分布**，已記為 `village_area_uniformity_assumption` proxy）。
5. 全市 `value = Σcovered ÷ Σtarget × 100`；區級同理。

半徑：青年服務據點 **2,500 m**、托育據點 **1,000 m**。
狀態：有排除點或有 blocking reason → `partial`；里界與里人口 join 不齊 → `incomplete_village_population_coverage`。

### 2.4 `fertility`

- `calculate_annual_fertility_metrics`：以 §2.2 的生育率為底，補上 `youthRatio`（18–35 ÷ 總人口 × 100）、`availableMonths`、`coverageRatio = 月數/12`。**必須 12 個月齊全且該區有生育數**才算 `observed`。
- `daycareCoverage`：`calculate_population_service_coverage`，半徑 1,000 m，目標人口欄位改成 `youth_18_35_female`，來源 `babysitting_places`。
- **FaFI（家庭友善指數）**：`daycareCoverage` 與 `salaryMedian` 各自用純 Min-Max 正規化，再與 homepage 的 `score_housing` 依設定權重平均——有正權重的任一項為 null 就整個 FaFI 為 null（`_weighted_if_complete`）。薪資是 `salary_median_shrunk`，再依四分位切 `low/medium/high`。
- 散布圖：x = `opportunityIndex`，y = `fertilityRate`，附 OLS。

### 2.5 選舉指標（`elections.py` + `youth_participation.py`）

年齡判定順序：`election_date − birth_date`（精確到月日）→ `election_date.year − (birth_year_roc + 1911)` → `source_age_numeric`。青年定義 **18 ≤ age ≤ 35**。

| 指標 | 粒度 | 公式 | 分母 |
|---|---|---|---|
| T1 `youth_candidacy_rate` | 選舉區（議員） | 青年參選人數 ÷ 全市青年人口 × 100,000 | 全市（議員選區跨行政區，不可切區） |
| V1 `youth_candidacy_rate` | 行政區（里長） | 青年參選人數 ÷ 該區青年人口 × 100,000 | 該區 |
| V1 `ratio` | 行政區 | 青年當選 ÷ 該區總當選席次 × 100 | — |
| V1 **YRR** | 行政區 | `(青年當選席次比) ÷ (青年人口占比)` | — |

YRR 分母用**人口占比**而非選舉人名冊，已明確標記 `age_specific_election_register_unavailable_population_share_used`（本次共 87 筆 proxy）。

### 2.6 `youth_participation` 其餘區塊

- **提案漏斗**：以 `(meeting_id, item_no, normalize_topic_text(topic))` 去重後，數 stage 1 identified / 2 discussed / 3 resolved。**stage 4 tracked、5 implemented 永遠寫死 `null`**，並固定帶 `youth_proposal_tracker_unavailable`——這是刻意的設計，不是 bug。
- **補助分布**：依 ROC 年與 `district_id` 加總 `amount_twd_thousand`；有任何一筆區別解析不出就整體 `partial`。
- **預算執行**：直接複用 §2.2 的 `calculate_budget_series`。
- **議題**：內嵌呼叫 `calculate_youth_topic_weights` 與 `calculate_youth_keyword_frequency`（先用 `annual_years_roc` 過濾年度），另有兩個獨立 metric 寫出 standalone 檔。

### 2.7 `employment`

不自己算 YOI，直接投影 homepage 的五個分項分數，另加兩張散布圖：

- 圖一：x = **知識型職缺比例** = 學歷要求含「大學/專科/學士/碩士/博士」的職缺 `position_count` ÷ 區內總 position_count × 100；y = `adjusted_youth_wage`（萬元/年）。
- 圖二：x = 月薪（年薪 ÷ 12，萬元）；y = 每坪房價（TWD ÷ 10,000 → 萬元）。

兩張皆附 OLS。**注意 x 軸是職缺端的學歷要求，不是居住人口教育程度**（程式碼與輸出 `note` 都有標註）。

### 2.8 `policy_support`

口徑比 homepage 更嚴，刻意只吃兩條線：

- `wageTrend`（ROC 108–113）：**只取**新北市 × `official_age_group == "25-29歲"` × `statistic_method == "平均數"`。中位數與其他年齡組完全不進 trend，也不進 YoY。
- `populationTrend`（ROC 111–115）：固定取**每年 7 月**快照的 29 區 `youth_18_35_total` 加總；**只要 29 區沒到齊就整年給 null**，避免區數不全被誤讀成人口下降。
- `currentWageGrowth` / `currentPopGrowth` = 各 trend 最後一個非 null 的 YoY。

### 2.9 `youth_topic_weight`（22 個固定議題）

```
raw_score = w_join·(join_support/年度max) + w_minutes·(minutes_mentions/年度max)
          + w_resolved·[已決議] + w_escalated·[提送大會]
其中 join_support = Σ over 提案 (1 + ln(1 + endorsement_count))
```

量化：`weight = clamp(1,5, floor(1 + 4·raw/年度max + 0.5))`，再套兩條硬規則——**有會議訊號則 `weight ≥ 3`；`escalated` 強制 `weight = 5`**。join 端只採 `youth_topic_proxy == true` 的提案，同一筆提案對同一議題只計一次。

### 2.10 `youth_keyword_frequency`（不限議題的動態關鍵字）

`jieba` 斷詞（未安裝時退回明確標記的 fallback tokenizer）+ 動態停用詞 + 政策詞典。

```
raw_score      = 資料訊號（join / 會議 / resolved / escalated）+ frequency_weight · log(term_frequency)
ranking_score  = raw_score + policy_relevance_bonus · policy_relevance
weight         = clamp(1,5, floor(1 + 4·ranking_score/max + 0.5))，同樣套 ≥3 / =5 硬規則
```

候選詞門檻：至少出現在 `min_document_frequency` 份文件；詞典外的三字以上複合詞需有議題文字證據或跨來源證據；二字詞門檻更高。設定在 `config/youth_keyword_config.json` 與四個詞表檔。

---

## 三、資料怎麼改動

### 3.1 Transform 層（`src/transform/`，見 `transform.md`）

- **統一 envelope**：每筆 curated record 都有 `dataset`/`source`/`source_record_id`/`geo_level`/`district_id`/`district_name`/`period_start`/`period_end`/`period_type`/`metric_id`/`value`/`unit`/`age_scope`/`age_min`/`age_max`/`youth_eligibility`/`fetched_at`/`quality_flags`，原始欄位另存 `raw_record`，不覆寫。
- **年齡口徑**：只有能證明涵蓋 18–35（含端點）的才標 `eligible`；官方年齡組保留原分組標 `official_age_group_proxy` / `proxy_only`；無年齡欄位標 `not_age_specific` / `context_only`。
- **不補值**：缺失一律 JSON `null`，禁止用 0 代替。
- **不拆區**：縣市／全國粒度維持 `county` / `national`，不人工拆成 29 區；對不到行政區時 `district_id = null`，**不得用最近行政區頂替**。
- **例外**：`college_majors` 以教育部校址對照表映射學校所在區（代表校址不是學生居住地），對不到保留 null。
- **名稱正規化**：`moving_in → movement`、`job_vacancy_salary → job_vacancy_salaries`、`bus_stop → bus_stops`。
- **輸出分區**：`monthly → {dataset}/{yyyMM}.json`、`annual → {dataset}/{yyy}.json`、`snapshot → latest.json`、`all_available → all.json`；index 寫 `quality/dataset_index.json`。

### 3.2 Analytics 層對資料做的改動

**單位換算**

| 欄位 | 來源單位 | 輸出單位 |
|---|---|---|
| `adjusted_youth_wage` | 萬元／年 | 保持萬元／年 |
| `estimated_monthly_wage` | — | ÷ 12 → 萬元／月 |
| `house_price_median_wan` | TWD／坪 | ÷ 10,000 → 萬元／坪 |
| 預算執行率分母 | `TWD_thousand` | × 1000 → `TWD`，單位不相容則整項 null |

**代理（proxy）與補值** —— 全部寫進 `quality/analytics_*.json` 的 `proxy_usage`

| 項目 | 做法 | 本次筆數 |
|---|---|---|
| 青年薪資 | 官方 25–29 歲取代 18–35 | 1 |
| `vt_course_count` | 缺區補「觀測最小值」 | **29** |
| `rent_median` | 缺區補全市最小值 | 依資料 |
| `house_price_median` | 缺區補住宅類最小值；平溪區改用全類型 | 依資料 |
| 全國青年人口 | 寫死 4,820,000 | 1 |
| YRR 分母 | 人口占比取代選舉人名冊 | **87** |
| 里內人口分布 | 假設均勻，按面積比例分攤 | 全里 |

**排除（exclusion）** —— 寫進 `quality` 的 `excluded`

| 資料集 | 總筆數 | 排除 | 原因 |
|---|---|---|---|
| `bus_stops` | 32,994 | 4,149 | 對不到行政區 |
| `job_vacancy_salaries` | 3,111 | 841 | 薪資上下界不完整，無法取中點 |
| `job_vacancies` | 3,944 | 44 | 對不到行政區 |
| `babysitting_places` | 391 | 171 | `geocode_status != matched` |
| `bike_stops` | 1,606 | 5 | 對不到行政區 |

**正規化**：所有現行 YOI／FaFI 跨區比較欄位一律以純 Min-Max 線性映射到 0–100，不再做 P5/P95 clip；逆向欄位（租金、房價、租金薪資比）取 `100 − x`。

**輸出邊界**：`published_snapshot.py` 會遞迴檢查 payload，**禁止 `raw_record` / `raw_records` 進入 public 產物**；`policy_support` 另有 `_strip_raw_fields()`。所有寫檔走 `atomic_json_write`。

---

## 四、缺少哪些資料

### 4.1 阻斷級（有指標直接算不出來 / 整片是 null）

**1. `join_proposals` 與 `youth_council_minutes` 不在 `dataset_index.json`**
`youth_topic_weight`、`youth_keyword_frequency` 兩個 CLI 直接 raise。現存的 `analytics/youth_topic_weight/all.json` 是 join 讀不到時的降級結果（`join_input_rows: 0`）。
→ 需重跑 pipeline 讓這兩個 `all_available` 資料集進 index（或補 index entry）。

**2. `population` 的 ODRP014 歷史邊界與選舉 anchor**
ODRP014 實測 `10301`–`10612` 全部回 `OD-0102-S`，所以它本身仍不能提供 ROC 103 月份。但 `population/10312` 現已接入內政部官方單一年齡 archive；`10712`、`11112` 則由原本的 ODRP014 來源提供，並由 retention 固定保留。官方 archive 的 10312 讀入 1,032 個村里、29 區，總人口 `3,966,818`，18–35 歲人口 `1,086,392`，與 103 年人口年報總人口交叉核對一致。

重跑 `youth_participation` 後：

```
city_councilor_t1_citywide 3 列 → 103／107／111 全部有值
borough_chief_v1         87 列 → 103／107／111 各 29 區全部有值
elections.blocking_reasons → []
```

這只解決選舉所需的年末分母；沒有用 10312 估算 103 年其他月份，也沒有把人口跨年借用。

**3. `youth_grants` 全部 110 筆 `district_id` 皆為 `null`**
落在 110–114 年的 83 筆全部無法解析行政區 → `grants.by_district` 是**空物件 `{}`**，`district_resolved_row_count: 0`。年度總額算得出（111: 1,194 / 112: 47 / 113: 37 / 114: 69 千元），但**「各區青年補助分布」這個指標完全做不出來**。
另：111 年 1,194 與其餘年度 37–69 的量級差 20 倍以上，建議一併查核來源解析是否正確。

### 4.2 降級級（算得出來但精度或覆蓋不足）

| # | 缺口 | 現況 | 影響 |
|---|---|---|---|
| 4 | `youth_budgets` 缺 ROC 110、111 | 只有 112–116（31 筆） | `budgetTrend` 110/111 為 `unavailable`，112 年因無前值而 YoY = null |
| 5 | 決算（`final_settlement`）只有 113 年 | 114/115 只有 `legal_budget` | `executionRate` 只有 113 算得出；homepage `policy.executionRate = null`、`executionFailure: final_settlement_unavailable` |
| 6 | `wages` 缺 ROC 114 | 只有 108–113 | 薪資 proxy 停在 113 年；且只有 county 級、只有官方年齡組，非精確 18–35 |
| 7 | `vt_courses` 只有 **2 個區** | 五股區 32、泰山區 42 | **27 區用觀測最小值 32 補**；目前只保留作背景欄位，不再影響 `S_talent` |
| 8 | `training_numbers` 87 筆全是 `geo_level: county` | `district_id` 全 null | `training_people_per_10k_youth` **29 區同值**；目前只保留作背景欄位，不再影響 `S_talent` |
| 9 | `talent_demand` 45 筆全是 `geo_level: national` | `district_id` 全 null | `talent_demand_yoy` **29 區同值**；目前只保留作背景欄位，不再影響 `S_job` |
| 10 | `youth_service_points` 只有 **9 點** | 皆 `geocode matched` | `serviceCoverageRate = 49.2%`、`status: partial` |
| 11 | `population_villages` 114 年缺 **7 個里** | 里界 1,039 / 里人口 1,032 | homepage 與 fertility 都掛 `incomplete_village_population_coverage` blocking |
| 12 | `babysitting_places` 391 筆只有 220 筆 geocode 成功 | 排除 171 筆（43.7%） | 托育覆蓋率低估，`daycareCoverage` 連帶把 FAFI 壓成 `partial` |
| 13 | `youth_council_minutes` 只有 55 筆、3 個年度 | 110(1)／112(35)／114(19) | 提案漏斗年度稀疏 |
| 14 | 會議紀錄解析品質差 | **50/55 筆 `manual_review_required`**、`resolved` 僅 5 筆、`escalated` 0 筆 | 漏斗 stage 3 只有 5、`escalated` 硬規則（weight=5）從未觸發 |
| 15 | `join_proposals` 近年幾近空白 | 2021:3082、2022:1516、2023:2356、2024:2727、**2025:19、2026:3** | ROC 114/115 的議題權重幾乎沒有 join 訊號 |
| 16 | 提案追蹤資料集不存在 | 無此 dataset | 漏斗 **stage 4 tracked / 5 implemented 永遠 null**（設計如此，需新資料源才能解） |
| 17 | 全國青年人口無資料源 | 寫死 4,820,000 | `kpi.nationalYouthPopulation` 標 `proxy` |
| 18 | `bus_stops` 走 legacy 平面檔 | `curated/bus_stops.json`（2026-09-04），不在 index | `source_period` 標 `legacy_flat_snapshot`，且 4,149 筆對不到區 |

**缺的 7 個里**（里界有、114 年里人口沒有，多為新設里）：

| village_code | 行政區 | 里名 |
|---|---|---|
| 65000100043 | 淡水區 | 新崁里 |
| 65000100044 | 淡水區 | 新市里 |
| 65000150021 | 五股區 | 芳洲里 |
| 65000170018 | 林口區 | 新林里 |
| 65000170019 | 林口區 | 力行里 |
| 65000170020 | 林口區 | 頭湖里 |
| 65000170021 | 林口區 | 文湖里 |

### 4.3 資料品質（quarantine）

| 資料集 | 進入 quarantine 的筆數 |
|---|---|
| `village_boundaries` | **6,651** |
| `join_proposals` | 819 |
| `youth_council_minutes` | 3 |

`village_boundaries` 最終只有 1,039 筆進 curated，被隔離 6,651 筆，比例偏高，值得回頭看 transform 的隔離條件。

### 4.4 收了資料但沒有任何指標消費

`movement`（68 個月分割）、`graduate_majors`（66 個期間檔）、`marriages`（**curated 目錄是空的**）在 `src/analytics/` 全域搜尋無任何引用。要嘛補指標，要嘛從 refresh profile 移除以節省抓取成本。

### 4.5 發布架構（已修正）

`data/analytics/published/current.json` 現在指向 `dev-full-20260912`。該完整
snapshot 同時包含 homepage、`employment`、`fertility`、`participation`、
`policy_support`、`topic_weight` 與 `keyword_frequency`，Backend 只要沿著
`current.json` → `manifest.json` 就能取得同一次產出的所有公開資料。

`run_analytics.py --metric all --publish` 會先完成七個輸出與 manifest，再最後
更新 `current.json`。個別 metric 的 `--publish` 只會寫候選／歷史 snapshot，
不會覆寫完整 release 指標；既有 `dev-*` 目錄保留作為歷史版本，不在讀取時拼接。

---

## 五、建議修復順序

1. **重跑 pipeline 把 6 個資料集寫回 `dataset_index.json`**（尤其 `join_proposals`、`youth_council_minutes`、`bus_stops`）→ 解掉 §4.1-1，並讓 `youth_participation` 回到授權讀取路徑。
2. **補入 `population/10312` 官方歷史 archive 並保留 10312／10712／11112 anchors** → 已完成；重跑後三個選舉年都有分母。
3. **修 `youth_grants` 的行政區解析** → 解鎖各區補助分布。
4. 補 `youth_budgets` 110–111 與 114/115 決算、`wages` 114。
5. 若要擴充背景分析，再補 `vt_courses`、`training_numbers`、`talent_demand` 的區級來源；目前 YOI 已改用 `population` 與最新學年度 `college_majors`，不受上述全區常數欄位影響。
6. 補 7 個新設里的 114 年里人口；改善 `babysitting_places` geocoding（目前只成功 56%）。
7. 完整 release 已改為由單一 `dev-full-*` snapshot 帶齊所有 analyses；後續由 Backend／DynamoDB loader 讀取該 manifest contract。
8. 處理 `movement` / `graduate_majors` / `marriages`：補指標或停止抓取。

---

## 附：實測指令

```bash
cd data-pipeline

# 逐一重算七個 analytics metric
for m in homepage employment fertility policy_support youth_participation \
         youth_topic_weight youth_keyword_frequency; do
  PYTHONPATH=src .venv/bin/python src/run_analytics.py \
    --metric "$m" --output-dir data --config-dir config
done

# 測試（data-pipeline 全部 411 passed）
PYTHONPATH=src .venv/bin/python -m pytest tests/test_*analytics*.py \
  tests/test_elections.py tests/test_homepage*.py tests/test_service_coverage.py \
  tests/test_youth_*.py -q

# 檢查 index 與 curated 的落差
python3 -c "
import json, os
idx = json.load(open('data/quality/dataset_index.json'))['datasets']
for name in sorted(os.listdir('data/curated')):
    if name.replace('.json','') not in idx: print('NOT IN INDEX:', name)
"
```
