# 主頁（首頁）參數分析、指數公式設計與資料源對應 (v8 最終版)

> 本文件依據最新的前端 React 元件架構（`features/home`），嚴格對齊 Notion MD 公式定義，並完整對應 `data_description.md` 中實際可用的 18 個資料集。
> 所有計算皆由 Backend 完成後才拋給 Frontend 顯示。

---

## 一、前端元件與參數對應表

首頁分為 **4 大 Section**，對應 5 個核心 Component。

> **資料源編號說明**：A = 全站底層、C = 青年就業五面向、E = 生育、F = 施政協助（對應 Notion 編號）

### Section 1：青年就業與發展機會 (`KpiSummaryRow.tsx`)

| UI 顯示項目            | 對應欄位                      | 資料源                      | 計算邏輯                                                              |
| ---------------------- | ----------------------------- | --------------------------- | --------------------------------------------------------------------- |
| 全台 18–35 歲青年人口  | `NATIONAL_YOUTH_POPULATION`   | **A1** `population`         | 加總全國各縣市 `youth_18_35_total`；若無全國資料則放常數 4,820,000    |
| 新北市青年佔總人口比例 | `CITY_YOUTH_POPULATION_SHARE` | **A1** `population`         | `youth_18_35_total`（新北市合計）÷ `people_total`（新北市合計）× 100% |
| 青年人口年增率 (YoY)   | `YOUTH_POPULATION_YOY`        | **A1** `population`（跨年） | (今年新北市 `youth_18_35_total` − 去年) ÷ 去年 × 100%                 |

---

### Section 2：29 區青年機會指數地圖與排行表 (`DistrictChoroplethMap.tsx` & `DistrictHighlightsTable.tsx`)

| UI 顯示項目             | 對應欄位             | 資料源                                   | 計算邏輯                                       |
| ----------------------- | -------------------- | ---------------------------------------- | ---------------------------------------------- |
| 地圖顏色 / 機會指數     | `opportunityIndex`   | **A1, C1.1–C2.3, C4.1, C4.2, C5.1–C5.3** | YOI 公式（詳見第二節），輸出 0–100             |
| 留才風險 (地圖 Tooltip) | `retentionRiskLevel` | 衍生自 `opportunityIndex`                | 直接對應 YOI 的 Q1/Q3 四分位切分（詳見第二節） |

> ⚠️ **備註：機會指數 YoY/Delta 欄位已移除。**
> 原因：我們的 `job_vacancies`、`rentals` 均為**單一快照**，沒有歷年區級資料，無法計算 YOI 的年度趨勢。前端排行表中的「增減」欄位應由後端在補齊多年快照後再接入，目前先移除或顯示「—」。

---

### Section 3：青年參政與生育概況 (`ParticipationOverviewCard.tsx` & `FertilityOverviewCard.tsx`)

| UI 顯示項目        | 對應欄位                          | 資料源                                        | 計算邏輯                                                                                                                                                                      |
| ------------------ | --------------------------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 青年參選率         | `youthParticipationIndex`         | **D**（選舉資料，待補）+ **A1**               | (該區 18–35 歲候選人數 ÷ 該區全體候選人數) × 100%                                                                                                                             |
| 整體服務涵蓋率     | `serviceCoverageRate`（新增欄位） | **D4**（據點座標）+ **A1**（里級）+里界多邊形 | 圓形 buffer（直線距離）＋ 面積比例分攤（詳見下方說明）                                                                                                                        |
| 平均生育率（全市） | `fertilityRate`                   | **E1** `births` + **A1** `population`         | 新北市 `births_mother_age_18_35` 加總 ÷ 新北市 `youth_18_35_female` 加總 × 1000‰ (這個部分會因為點選上面地圖而算出各地區的平均生育率，右邊那塊顯示全市平均讓他們知道量化差異) |
| 對全市平均比       | `fertilityVsCityAvg`（新增欄位）  | 衍生自上兩項                                  | 各區 `fertilityRate` ÷ 全市平均 `fertilityRate` × 100%（後端計算後回傳）                                                                                                      |

#### 📝 服務涵蓋率詳細計算方式

- **定義**：各服務據點 2.5 公里服務半徑內涵蓋之青年人口比例。
- **計算方法**（不做「整里進/出」的二元判定）：
  1. 對每個服務據點以半徑 `r=2.5km` 畫圓，取所有圓的聯集 `B`。
  2. 對每個里 `v`，計算里多邊形與 B 的交集面積比例 `f_v = area(polygon_v ∩ B) / area(polygon_v)`。_(需在等面積投影如 EPSG:3826 下計算)_
  3. 該里「被涵蓋的青年人口」= `f_v × youth_18_35(v)`（假設青年在里內均勻分布）。
  4. 匯總到區：`服務涵蓋率(區) = Σ_v [ f_v × youth_18_35(v) ] ÷ Σ_v youth_18_35(v)`
- **資料阻塞點**：需取得青年局據點清單進行 geocoding (D4)，且需新增里級人口輸出與里界 GeoJSON。

> ✅ **`births` 資料確認**：`metric_id = births_mother_age_18_35`，即「生母 18–35 歲的出生數」，2019–2025 年共 29 區，`youth_eligibility = eligible`，可直接使用。
>
> ⚠️ **資料缺口**：
>
> - **青年參選率**：需要各屆選舉候選人年齡與行政區資料（D），目前 Pipeline 無此資料。
> - **服務涵蓋率**：需要青創基地完整地址清單（D4），目前 Pipeline 無此資料。
> - 以上兩項建議前端先顯示「資料補充中」，待後端補上後再接入。

---

### Section 4：施政協助 (`PolicySupportPanel.tsx`)

| UI 顯示項目          | 對應欄位                          | 資料源                             | 計算邏輯                                                                                           |
| -------------------- | --------------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------- |
| 青年局年度預算折線圖 | `budgetTrend`（新增欄位，為陣列） | **F1** `youth_budgets`             | 取各年 `row_type = total` 的 `value`（單位：千元），組成時間序列。現有 ROC 112–116 年共 5 個資料點 |
| 青年總預算（當年）   | `TOTAL_BUDGET`                    | **F1** `youth_budgets`             | 取最新年度 `row_type = total` 的 `value`                                                           |
| 預算 YoY             | `BUDGET_YOY`                      | **F1** `youth_budgets`（跨年）     | `(今年 total value − 去年 total value) ÷ 去年 total value × 100%`                                  |
| 預算執行率           | `BUDGET_EXECUTION_RATE`           | **F1** `youth_budgets`（待補決算） | `決算執行數 ÷ 法定預算數 × 100%`                                                                   |

> ⚠️ **備註：執行率資料待補**
> 目前 `youth_budgets` 的 `document_status` 只有 `legal_budget`（法定預算）與 `proposed_budget`（預算案），**沒有決算數 (`final_settlement`)**。
> 需請後端工程師至青年局官網「統計專區」→「預決算公告」補抓決算 PDF，讓 pipeline 輸出 `document_status = final_settlement` 的 row，才能計算執行率。
> **補抓完成前，前端此欄位顯示「資料補充中」。**
>
> ⚠️ **備註：達成率欄位已移除**
> 原因：18 個資料集中均無「政策 KPI 目標數」或「KPI 達成數」，無法計算。不以無資料支撐的公式顯示任何數值。

---

## 二、核心指數公式設計（Backend 需實作）

### 1. 青年機會指數 Youth Opportunity Index（YOI）

> 產生 `districts.csv` 的 `opportunityIndex`。範圍 **0–100**。

#### 加權合成公式

```text
YOI = 0.25·S_job + 0.25·S_salary + 0.05·S_talent + 0.25·S_housing + 0.20·S_transport
```

_(人才面向 S_talent 權重僅 0.05，原因：`college_majors` 為學校所在地而非學生戶籍地，會集中在淡水、新莊、三峽、板橋少數幾區，其餘區為 0，不具區分力)_

#### 標準化函數

所有子數值在加權前先做 **Min-Max 標準化（截斷 P5/P95 極端值）**：

```text
x_clipped = clip(x, P5, P95)
norm(x)   = (x_clipped - min(x_clipped)) / (max(x_clipped) - min(x_clipped)) × 100
norm_inv(x) = 100 - norm(x)   ← 反向指標用（數值越高，分數越低）
```

若 max = min（29 區值相同），則 norm = 50。

---

#### S₁：工作機會（S_job）

```text
S_job = 0.50 × norm(每萬青年職缺數)
      + 0.30 × norm(職業多樣性 Shannon Index)
      + 0.20 × norm(人才需求趨勢 YoY)
```

| 元素             | 計算方式                                                                | 資料源                                         | 說明                                                                                                                 |
| ---------------- | ----------------------------------------------------------------------- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| 每萬青年職缺數   | `(該區職缺總數 ÷ 該區 youth_18_35_total) × 10,000`                      | **C1.1** `job_vacancies` ÷ **A1** `population` | 使用 `position_count` 加總；只用 `geo_level=district` 的筆數                                                         |
| 職業多樣性       | `H = −Σ pᵢ·ln(pᵢ)`，pᵢ = 職業類別 i 的職缺占比（依 raw 的職業類別欄位） | **C1.2** `job_vacancies`                       | Shannon Entropy，越高代表職業越多樣                                                                                  |
| 人才需求趨勢 YoY | `(本年 new_demand_count − 上年) ÷ 上年 × 100%`                          | **C1.3** `talent_demand`                       | ⚠️ 此資料為**全國**粒度，29 區共用同一值，差異來自其他兩項；待補區級資料(若沒有可刪除這塊，比例改成剩下兩項0.6及0.4) |

---

#### S₂：薪資水準（S_salary）

```text
S_salary = 0.40 × norm(職缺刊登薪資中位數)
         + 0.30 × norm(高薪職缺比例)
         + 0.30 × norm(各區調整後青年薪資_估算值)
```

| 元素               | 計算方式                                                 | 資料源                            | 說明                                             |
| ------------------ | -------------------------------------------------------- | --------------------------------- | ------------------------------------------------ |
| 職缺薪資中位數     | 各區有薪資職缺的 `salary_midpoint` 中位數                | **C2.2** `job_vacancy_salaries`   | 需過濾 `salary_midpoint` 為 null 的單邊薪資資料  |
| 高薪職缺比例       | `薪資 > 全市中位數 × 1.5 的職缺數 ÷ 該區總職缺數`        | **C2.3**（衍生自 **C2.2**）       | 全市中位數以 `job_vacancy_salaries` 全部筆數計算 |
| 各區調整後青年薪資 | **以房價做空間分布代理**，估算各區實際薪資（見下方邏輯） | **C2.1** `wages` + `house_prices` | 解決官方薪資僅到縣市層級的問題                   |

#### 📝 各區調整後青年薪資 推算邏輯 (以房價做代理)

經濟學上薪資與房價高度正相關。我們使用時間跨度長、穩定的房價資料來反推各區薪資：
_(註：此處推算薪資時，使用_*「所有種類」*_的平均房價數據，包含住宅用與工業用，以全面反映地方經濟能量。)_

1. **計算房價相對指數**：`price_ratio(d, year) = MEDIAN(house_prices[d, year]) / MEDIAN(house_prices[全市, year])`
2. **分配縣市級薪資到區**：`estimated_wage(d, year) = wages[新北市, year, 25-29歲] × price_ratio(d, year)`
3. _(可選驗證)_：計算 `CORR(estimated_wage(d), MEDIAN(job_vacancy_salaries[d]))`，若 `R² > 0.7` 則分配可信。

---

#### S₃：人才發展（S_talent）

```text
S_talent = 0.30 × norm(大專學生數密度)
         + 0.35 × norm(職訓課程數)
         + 0.35 × norm(訓練人次_每萬青年)
```

| 元素            | 計算方式                                                            | 資料源                               | 說明                                                                                                 |
| --------------- | ------------------------------------------------------------------- | ------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| 大專學生數密度  | `該區 student_count 加總 ÷ 該區面積 km²`                            | **C3.1** `college_majors`            | ⚠️ 縣市級（學校所在地），全部集中在少數區；其餘區為 0。故 S_talent 權重已降至 0.05                   |
| 職訓課程數      | 該區 `distinct_course_count`                                        | **C3.3** `vt_courses`                | ⚠️ 目前只有五股（32）、泰山（42）兩區有資料，其他 27 區均為 null → 建議先對這 27 區給予全市最低值 32 |
| 訓練人次/萬青年 | `(新北市 training_people 加總 ÷ 新北市 youth_18_35_total) × 10,000` | **C3.4** `training_numbers` ÷ **A1** | ⚠️ 縣市級，無法拆到區；29 區共用同一值                                                               |

---

#### S₄：居住負擔（S_housing）— **反向指標**

```text
S_housing = 0.35 × norm_inv(租金中位數)
          + 0.35 × norm_inv(房價中位數_per_ping)
          + 0.30 × norm_inv(租金薪資比)
```

| 元素               | 計算方式                                      | 資料源                  | 說明                                                                                            |
| ------------------ | --------------------------------------------- | ----------------------- | ----------------------------------------------------------------------------------------------- |
| 租金中位數         | 各區所有 `rent_total` 的中位數                | **C4.1** `rentals`      | ⚠️ 缺坪林、平溪兩區；這兩區給予 29 區最低租金值                                                 |
| 房價中位數（每坪） | 各區「**限定住宅用**」`price_per_ping` 中位數 | **C4.2** `house_prices` | ⚠️ 為反映真實居住負擔，**排除工業用房價**。例外：平溪因缺乏住宅專門數據，特例使用「所有」房價。 |
| 租金薪資比         | `各區租金中位數 ÷ 各區職缺薪資中位數（C2.2）` | **C4.3**（衍生）        | 衡量租屋對薪資的壓力                                                                            |

---

#### S₅：交通可及（S_transport）

```text
S_transport = 0.35 × norm(每萬青年公車站數)
            + 0.40 × norm(軌道站點密度)
            + 0.25 × norm(公共自行車站點密度)
```

| 元素               | 計算方式                                                  | 資料源                            | 說明                                                  |
| ------------------ | --------------------------------------------------------- | --------------------------------- | ----------------------------------------------------- |
| 每萬青年公車站數   | `(各區 bus_stops 筆數 ÷ 該區 youth_18_35_total) × 10,000` | **C5.1** `bus_stops` ÷ **A1**     | 28,845 筆可映射到區；4,149 筆 `district_id=null` 排除 |
| 軌道站點密度       | `各區 railway_stops 筆數 ÷ 該區面積 km²`                  | **C5.2** `railway_stops` ÷ **A4** | 目前只有 18 區有站點；其餘 11 區給值 0                |
| 公共自行車站點密度 | `各區 bike_stops 筆數 ÷ 該區面積 km²`                     | **C5.3** `bike_stops` ÷ **A4**    | 1,595 筆可映射；5 筆 `district_id=null` 排除          |

> ⚠️ **A4（各區面積）**：`data_description.md` 中無此資料集。建議從 GeoJSON 地圖邊界（新北市 29 區界線，已在前端 `useNewTaipeiTopology` 使用）計算各區面積 km²，或直接使用內政部公告的行政區面積查詢表。

---

### 2. 留才風險評級（Retention Risk Level）

> 產生 `districts.csv` 的 `retentionRiskLevel`。

**採用最簡化方法：直接對 YOI 值做四分位切分**。
機會越高的行政區，留才風險越低；不需額外的複合公式。

```text
計算所有 29 區的 opportunityIndex 清單，取：
  Q1 = 第 25 百分位數
  Q3 = 第 75 百分位數

若 opportunityIndex >= Q3 → retentionRiskLevel = 'low'
若 opportunityIndex <= Q1 → retentionRiskLevel = 'high'
否則                      → retentionRiskLevel = 'medium'
```

---

## 三、Backend API 資料計算 Pseudocode

```python
def generate_homepage_data(snapshot_date, year):
    """
    產生首頁所需的全部資料。
    snapshot_date: 職缺/交通快照日期（目前只有 2026-09-03）
    year: 主要統計年份（建議用最新完整年）
    """

    # ── 拉取原始資料 ──────────────────────────────────────────
    pop      = db.get("population", year)          # A1
    pop_prev = db.get("population", year - 1)       # A1 上一年
    births   = db.get("births", year)              # E1
    vacancies        = db.get("job_vacancies")      # C1.1
    vacancy_salaries = db.get("job_vacancy_salaries") # C2.2
    wages    = db.get("wages", year)               # C2.1
    houses   = db.get("house_prices")              # C4.2
    rentals  = db.get("rentals")                   # C4.1
    talent   = db.get("talent_demand", year)       # C1.3（全國）
    college  = db.get("college_majors", year)      # C3.1（縣市）
    vt       = db.get("vt_courses")                # C3.3（只有五股、泰山）
    training = db.get("training_numbers")          # C3.4（縣市）
    bus      = db.get("bus_stops")                 # C5.1
    rail     = db.get("railway_stops")             # C5.2
    bike     = db.get("bike_stops")                # C5.3
    budgets  = db.get("youth_budgets")             # F1
    district_areas = get_district_areas_from_geojson() # A4（由 GeoJSON 計算）

    # ── Section 1：全市 KPI ───────────────────────────────────
    city_youth_now  = sum(pop[d].youth_18_35_total for d in ALL_29_DISTRICTS)
    city_youth_prev = sum(pop_prev[d].youth_18_35_total for d in ALL_29_DISTRICTS)
    city_total_pop  = sum(pop[d].people_total for d in ALL_29_DISTRICTS)

    kpi = {
        "nationalYouthPop": NATIONAL_CONST or sum_from_all_counties(pop),
        "cityYouthShare":   city_youth_now / city_total_pop * 100,
        "youthPopYoY":      (city_youth_now - city_youth_prev) / city_youth_prev * 100,
    }

    # ── 預計算全市中位數（薪資用）────────────────────────────
    all_salary_midpoints = [v.salary_midpoint for v in vacancy_salaries if v.salary_midpoint]
    city_salary_median   = median(all_salary_midpoints)
    high_salary_threshold = city_salary_median * 1.5

    # ── 薪資代理計算 (利用房價) ──────────────────────────────
    # 注意：推算薪資使用「全部種類」的房價
    all_house_median = median([h.price_per_ping for h in houses if h.price_per_ping])
    city_base_wage = wages["25-29"].value

    estimated_wages = {}
    for d in ALL_29_DISTRICTS:
        d_houses_all = [h.price_per_ping for h in houses if h.district_id == d and h.price_per_ping]
        if d_houses_all:
            price_ratio = median(d_houses_all) / all_house_median
            estimated_wages[d] = city_base_wage * price_ratio
        else:
            estimated_wages[d] = city_base_wage  # Fallback

    # ── 全國人才需求趨勢 YoY（全國共用）─────────────────────
    talent_now  = sum(t.new_demand_count for t in talent[year])
    talent_prev = sum(t.new_demand_count for t in talent[year-1])
    talent_yoy  = (talent_now - talent_prev) / talent_prev * 100

    # ── Section 2：29 區迴圈 ─────────────────────────────────
    raw_scores = []  # 暫存各子指標原始值，用於後續 norm

    for d in ALL_29_DISTRICTS:
        area = district_areas[d]
        pop_youth = pop[d].youth_18_35_total

        # S_job 原始值
        vac_count    = sum(v.position_count for v in vacancies if v.district_id == d)
        per_10k_vac  = (vac_count / pop_youth) * 10000 if pop_youth else 0
        shannon      = calc_shannon_entropy(vacancies, d)  # pᵢ = 各職業類別占比

        # S_salary 原始值
        d_salaries   = [v.salary_midpoint for v in vacancy_salaries
                        if v.district_id == d and v.salary_midpoint]
        salary_median = median(d_salaries) if d_salaries else 0
        high_sal_ratio = len([s for s in d_salaries if s > high_salary_threshold]) / len(d_salaries) if d_salaries else 0
        adj_youth_wage = estimated_wages[d] # 來自上述代理計算

        # S_talent 原始值（縣市或缺值共用）
        college_density = sum(c.student_count for c in college) / area  # 縣市共用學生總數
        vt_courses   = vt.get(d, {"distinct_course_count": 32}).distinct_course_count  # 缺值給最低值 32
        train_per_10k = (sum(t.training_people for t in training) / city_youth_now) * 10000  # 縣市共用

        # S_housing 原始值
        rent_med   = median([r.rent_total for r in rentals if r.district_id == d]) if has_data(rentals, d) else city_min_rent

        # 居住負擔限定「住宅用」(平溪例外)
        d_houses_res = [h.price_per_ping for h in houses if h.district_id == d and h.price_per_ping and h.transaction_type == '住宅用']
        if not d_houses_res and d == '平溪區':
            d_houses_res = [h.price_per_ping for h in houses if h.district_id == d and h.price_per_ping] # 降級使用全部
        house_med = median(d_houses_res) if d_houses_res else city_min_house_res

        rent_wage_ratio = rent_med / salary_median if salary_median else 0

        # S_transport 原始值
        bus_count  = len([b for b in bus  if b.district_id == d])
        rail_count = len([r for r in rail if r.district_id == d])
        bike_count = len([b for b in bike if b.district_id == d])
        bus_per_10k      = (bus_count / pop_youth) * 10000 if pop_youth else 0
        rail_density     = rail_count / area if area else 0
        bike_density     = bike_count / area if area else 0

        raw_scores.append({
            "id": d,
            "per_10k_vac":    per_10k_vac,
            "shannon":         shannon,
            "talent_yoy":      talent_yoy,     # 全國共用
            "salary_median":   salary_median,
            "high_sal_ratio":  high_sal_ratio,
            "adj_youth_wage":  adj_youth_wage,  # 來自代理計算
            "college_density": college_density, # 縣市共用
            "vt_courses":      vt_courses,
            "train_per_10k":   train_per_10k,  # 縣市共用
            "rent_med":        rent_med,
            "house_med":       house_med,
            "rent_wage_ratio": rent_wage_ratio,
            "bus_per_10k":     bus_per_10k,
            "rail_density":    rail_density,
            "bike_density":    bike_density,
        })

    # ── 對所有區做 Min-Max 標準化（先截斷 P5/P95）──────────
    def normalize_col(col):   return [minmax_with_clip(v[col]) for v in raw_scores]
    def normalize_inv(col):   return [100 - v for v in normalize_col(col)]

    # ── 計算 YOI 並決定留才風險 ──────────────────────────────
    districts_result = []
    yoi_list = []

    for i, d_raw in enumerate(raw_scores):
        s_job     = (0.50 * norm_per_10k_vac[i]
                   + 0.30 * norm_shannon[i]
                   + 0.20 * norm_talent_yoy[i])
        s_salary  = (0.40 * norm_salary_median[i]
                   + 0.30 * norm_high_sal_ratio[i]
                   + 0.30 * norm_adj_youth_wage[i])
        s_talent  = (0.30 * norm_college_density[i]
                   + 0.35 * norm_vt_courses[i]
                   + 0.35 * norm_train_per_10k[i])
        s_housing = (0.35 * norm_inv_rent_med[i]
                   + 0.35 * norm_inv_house_med[i]
                   + 0.30 * norm_inv_rent_wage_ratio[i])
        s_transport = (0.35 * norm_bus_per_10k[i]
                     + 0.40 * norm_rail_density[i]
                     + 0.25 * norm_bike_density[i])

        yoi = (0.25*s_job + 0.25*s_salary + 0.05*s_talent
             + 0.25*s_housing + 0.20*s_transport)
        yoi_list.append(yoi)

    # 計算 Q1/Q3 做留才風險分級
    q1 = percentile(yoi_list, 25)
    q3 = percentile(yoi_list, 75)

    # ── Section 3：生育率 ─────────────────────────────────────
    city_births   = sum(b.value for b in births)
    city_female   = sum(pop[d].youth_18_35_female for d in ALL_29_DISTRICTS)
    city_fert_avg = (city_births / city_female) * 1000

    # ── Section 4：施政預算折線圖 ────────────────────────────
    budget_trend = [
        {"year": row.budget_year_roc, "value_thousand": row.value}
        for row in budgets if row.row_type == "total"
    ]  # ROC 112–116 年各 1 筆

    # 計算預算 YoY（最新年 vs 前一年）
    sorted_budgets = sorted(budget_trend, key=lambda x: x["year"])
    budget_yoy = (
        (sorted_budgets[-1]["value_thousand"] - sorted_budgets[-2]["value_thousand"])
        / sorted_budgets[-2]["value_thousand"] * 100
    ) if len(sorted_budgets) >= 2 else None

    # ── 組合最終輸出 ──────────────────────────────────────────
    for i, d in enumerate(ALL_29_DISTRICTS):
        yoi = round(yoi_list[i], 1)
        districts_result.append({
            "id":                   d,
            "name":                 district_names[d],
            "opportunityIndex":     yoi,
            "retentionRiskLevel":   "low" if yoi >= q3 else ("high" if yoi <= q1 else "medium"),
            # delta（YoY）：目前無歷年資料，後端補齊多年快照後再接入
            # "delta": None,
            "youthParticipationIndex": None,  # 待補選舉資料
            # 服務涵蓋率 (需有里級人口及 GeoJSON 計算面積交集)
            # f_v = polygon_v.intersection(B).area / polygon_v.area
            # cov_rate = sum(f_v * pop_v) / pop_district
            "serviceCoverageRate":     calculate_areal_interpolation_coverage(d),
            "fertilityRate":        (births_by_district[d] / pop[d].youth_18_35_female) * 1000,
            "fertilityVsCityAvg":   ((births_by_district[d] / pop[d].youth_18_35_female) * 1000) / city_fert_avg * 100,
        })

    return {
        "kpi":      kpi,
        "districts": districts_result,
        "policy": {
            "budgetTrend":          budget_trend,
            "currentBudget":        sorted_budgets[-1]["value_thousand"],
            "budgetYoY":            budget_yoy,
            "executionRate":        None,  # ⚠️ 決算 PDF 待後端補抓後再計算
        }
    }
```

---

## 四、後端補抓清單（Pending Actions）

| 項目                | 說明                                                                                            | 影響欄位                       |
| ------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------ |
| 🔴 決算 PDF         | 至青年局「統計專區→預決算公告」補抓決算版 PDF，pipeline 輸出 `document_status=final_settlement` | `BUDGET_EXECUTION_RATE`        |
| 🔴 選舉候選人資料   | 中選會各屆候選人名冊（含年齡或出生年）                                                          | `youthParticipationIndex`      |
| 🔴 青創基地地址清單 | 新北市青年局 D4 據點清單，地理編碼後計算緩衝區                                                  | `serviceCoverageRate`          |
| 🟡 各區面積 (A4)    | 由 GeoJSON 計算或從內政部行政區面積表取得                                                       | S_talent、S_transport 密度計算 |
