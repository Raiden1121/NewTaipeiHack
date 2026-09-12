# API Contract — 前端五大板塊 ↔ Backend Read API

本文件把 **frontend 五個頁面的每一個區塊**，逐一綁定到 **data-pipeline 已發布的 analytics snapshot** 與 **Backend read API** 的實際欄位，並標明每個區塊目前有沒有真實資料可串。

目的是讓三方有同一份參照：前端知道該接哪個欄位、後端知道該回傳什麼、資料端知道還缺什麼。

---

## 0. 權威來源與邊界

### 0.1 本文件不重新發明 API

Backend API 的形狀（endpoint、envelope、錯誤碼）已由下列文件定義，**以該文件為準**：

- `docs/superpowers/specs/2026-09-10-backend-read-api-design.md`（branch `origin/datapipeline`）

> ⚠️ 該檔目前含**未解決的 git merge conflict 標記**（`<<<<<<< ours` / `>>>>>>> theirs`），共 4 處。合併前請先解掉，否則 shared types 會依據錯誤內容產生。兩邊的實質差異只有兩點：(a) 是否明訂「API 對外只用 ISO period，ROC 只留在 pipeline metadata」、(b) 是否有 `backend/src/http/types.ts`。建議都採 `ours` 版本。

本文件負責的是那份 spec 沒有寫的部分：**哪個 UI 區塊吃哪個欄位、以及該欄位現在有沒有值**。

### 0.2 各模組邊界

| 模組 | 負責 | 不負責 |
|---|---|---|
| `data-pipeline` | 抓取、清理、指標計算、產出 published snapshot | HTTP、request 驗證 |
| `backend` | 讀 snapshot、驗證參數、組 response、錯誤處理 | ETL、指標計算、AI |
| `ai-service` | 政策問答、RAG、Bedrock | 統計指標 |
| `frontend` | 只做呈現 | 抓 open data、算指數、ETL |

指標一律由 `data-pipeline/src/analytics/` 算完才發布。Backend 在 request 期間**不做任何計算**，前端也不做。

### 0.3 資料現況基準

本文件所有「現況」欄位，比對的是這份實際產出：

```
data-pipeline/data/analytics/published/dev-homepage-20260911/
├── manifest.json
├── dashboard_overview.json      (578 KB)
└── district_details.json        (147 KB)
```

- `snapshot_id`: `dev-homepage-20260911`
- `generated_at`: `2026-09-11T13:12:09Z`
- `calculation_version`: `1`
- `time_policy.annual_years_roc`: `[110, 111, 112, 113, 114]`
- `time_policy.election_years_roc`: `[103, 107, 111]`
- 29 區齊全，`districts[]` 內**沒有任何 null 欄位**

---

## 1. 基礎約定

### 1.1 Endpoints

| Endpoint | 用途 | 本文件涵蓋的區塊 |
|---|---|---|
| `GET /api/v1/health` | manifest 是否可讀 | — |
| `GET /api/v1/catalog` | snapshot、資料期間、粒度、品質 | 各頁「資料期間」註腳 |
| `GET /api/v1/dashboard/overview` | 首頁 KPI + 29 區摘要 + 年度序列 | 主頁、就業地圖、參政地圖、生育地圖、預算 |
| `GET /api/v1/districts/{districtId}` | 單區完整指標 | 就業雷達圖、生育核心指標、參政 KPI |
| `GET /api/v1/analyses/{analysisId}` | 預先算好的分析（散佈圖、文字雲等） | 見 §6 |

查詢參數 allowlist：`period=latest|YYYY|YYYY-MM`、`timeframe=recent_3y|historical_10y`，兩者不可並用。`districtId` 必須是 29 區之一。

### 1.2 Response envelope

```json
{
  "data": { },
  "meta": {
    "api_version": "v1",
    "snapshot_id": "dev-homepage-20260911",
    "generated_at": "2026-09-11T13:12:09Z",
    "as_of": null,
    "warnings": ["incomplete_village_population_coverage"]
  }
}
```

一次 response 只能使用同一個 snapshot，不可混用不同版本的資料。

### 1.3 缺值與狀態

- **缺值一律 `null`，絕不用 `0` 代替。** 前端必須對每個數值欄位做 null 防呆。
- `status` 三態：`available` / `partial` / `unavailable`。
- **「資源存在但沒有資料」回 `200` + `unavailable`，不是 `404`。** 404 只用在 districtId / analysisId 本身不存在。
- pipeline 端另有 `quality_status`：`observed` / `partial` / `unavailable`。

`dashboard_overview` 頂層提供一組區塊級旗標，前端可直接據此決定顯示數字還是「資料待補」：

```jsonc
"availability": {
  "opportunityIndex":        "available",
  "fertility":               "available",
  "youthParticipationIndex": "available",
  "serviceCoverage":         "partial",
  "budget":                  "partial"
}
```

### 1.4 錯誤

```json
{ "error": { "code": "INVALID_QUERY", "message": "...", "details": [] }, "request_id": "..." }
```

| HTTP | code |
|---|---|
| 400 | `INVALID_QUERY` |
| 404 | `DISTRICT_NOT_FOUND` / `ANALYSIS_NOT_FOUND` |
| 503 | `SNAPSHOT_UNAVAILABLE` |
| 500 | `INTERNAL_ERROR` |

response 不得包含 `raw_record`、`raw_records`、本地路徑或 stack trace。`published_snapshot.py` 已在發布時強制擋掉前兩者。

---

## 2. 命名映射（重要）

`shared.md` 明文警告過這個問題，而它**已經發生了**：同一個概念目前有三套名字。

| 概念 | pipeline 實際輸出 | frontend 現有型別 | 分析文件寫的 |
|---|---|---|---|
| 行政區代碼 | `district_id` | `id` | `id` |
| 行政區名稱 | `district_name` | `name` | `name` |
| 工作機會子分數 | `yoiComponents.job` | （無） | `score_job` |
| 薪資子分數 | `yoiComponents.salary` | （無） | `score_salary` |
| 人才子分數 | `yoiComponents.talent` | （無） | `score_talent` |
| 居住友善子分數 | `yoiComponents.housing` | （無） | `score_housing` |
| 交通子分數 | `yoiComponents.transport` | （無） | `score_transport` |
| 青年參選率 | `youthCandidacyRatePer100k` | `youthParticipationIndex` | `youth_candidacy_rate` |

### 決議

**API 對外統一使用 pipeline 的實際輸出名稱**（`district_id`、`yoiComponents.*`、`youthCandidacyRatePer100k`），理由是那是唯一有真實產出、跑得起來的一套；文件跟前端型別去對齊它，而不是反過來要 pipeline 改名。

例外一項：`youthParticipationIndex` 這個名字**保留為 deprecated alias**，與 `youthCandidacyRatePer100k` 同值，讓前端可以分批遷移。新程式碼不得使用。

前端需要的調整：

```ts
// frontend/src/types/district.ts — 改為
export interface DistrictSummary {
  district_id: string;
  district_name: string;
  opportunityIndex: number;
  yoiComponents: { job: number; salary: number; talent: number; housing: number; transport: number };
  retentionRiskLevel: "low" | "medium" | "high";
  fertilityRate: number;
  fertilityVsCityAvg: number;
  serviceCoverageRate: number | null;
  serviceCoverageStatus: "available" | "partial" | "unavailable";
  youthCandidacyRatePer100k: number | null;
  qualityStatus: "observed" | "partial" | "unavailable";
}
```

注意 `policySupportScore` 這個欄位（目前 `districts.csv` 有、生育頁友善度面板在用）**在 pipeline 完全不存在**，不要放進契約，見 §5.4。

---

## 3. 共用資料物件

### 3.1 `districts[]`（29 筆，來自 `dashboard_overview.json`）

每筆 28 個欄位。分四組：

**原始指標（單位為實際量綱）**

| 欄位 | 單位 | 板橋區實值 |
|---|---|---|
| `youth_18_35_total` | 人 | 107970 |
| `vacancies_per_10k_youth` | 職缺/萬青年 | 99.38 |
| `occupation_shannon_index` | — | 3.59 |
| `talent_demand_yoy` | % | -6.00 |
| `salary_median` | TWD/月 | 35000 |
| `high_salary_ratio` | 比例 0–1 | 0.0378 |
| `adjusted_youth_wage` | 萬元/年 | 77.61 |
| `college_student_density` | 人/km² | 4864.50 |
| `vt_course_count` | 門 | 32 |
| `training_people_per_10k_youth` | 人次/萬青年 | 24.87 |
| `rent_median` | TWD/月 | 20000 |
| `house_price_median` | TWD/坪 | 574657.83 |
| `rent_wage_ratio` | 比例 | 0.5714 |
| `bus_stops_per_10k_youth` | 站/萬青年 | 142.35 |
| `railway_stop_density` | 站/km² | 0.5169 |
| `bike_stop_density` | 站/km² | 10.39 |

**合成指標**

| 欄位 | 型別 | 說明 | 29 區實際範圍 |
|---|---|---|---|
| `opportunityIndex` | number | YOI，`0.25·job + 0.25·salary + 0.05·talent + 0.25·housing + 0.20·transport` | **20.42 – 54.82**（中位 38.16）|
| `yoiComponents` | object | 五個 0–100 子分數 | 見下 |
| `normalizedInputs` | object | 16 個原始指標標準化後的 0–100 值，除錯用 |
| `retentionRiskLevel` | `"low"\|"medium"\|"high"` | 低 8 / 中 13 / 高 8 區 |
| `fertilityRate` | number | 育齡青年生育率 ‰ | **12.67 – 74.92**（中位 26.70）|
| `fertilityVsCityAvg` | number | 對全市平均比 % | 49.63 – 293.51 |
| `serviceCoverageRate` | number | 服務涵蓋率 % | **0 – 90.80（中位 0）** |
| `serviceCoverageStatus` | string | 目前 29 區全為 `"partial"` |
| `youthCandidacyRatePer100k` | number | 青年**里長候選人**數/十萬青年 | **0 – 64.68**（中位 6.27）|
| `youthParticipationIndex` | number | 同上，deprecated alias |
| `qualityStatus` | string | 目前 29 區全為 `"observed"` |
| `sourcePeriods` | object | 19 個資料集各自的來源期間 |

`yoiComponents` 各子分數實際範圍：

| 子分數 | min | median | max | 備註 |
|---|---|---|---|---|
| `job` | 10.00 | 44.16 | 86.29 | |
| `salary` | 0.22 | 39.49 | 91.61 | |
| `talent` | 35.00 | 35.00 | 65.00 | **變異極小**，權重已降至 0.05 |
| `housing` | 2.05 | 38.77 | 100.00 | 反向標準化，**越高代表居住越友善** |
| `transport` | 1.76 | 19.00 | 65.00 | |

`housing` 語意提醒：欄位方向已經是「越高越好」，**前端不得再反轉一次**。

### 3.2 標準化函數

```text
norm(x)     = (clip(x, P5, P95) - min) / (max - min) × 100
norm_inv(x) = 100 - norm(x)        ← housing 使用
```

---

## 4. 主頁（`/`）

`GET /api/v1/dashboard/overview`

### 4.1 KPI 三卡（`KpiSummaryRow`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 全台 18–35 歲青年人口 | `data.kpis.nationalYouthPopulation` = `4820000` | ⚠️ **硬編常數**，`nationalYouthPopulationQuality: "proxy"`。無全國人口 collector。|
| 全台佔比 | — | ❌ 前端 `20.6%` 為寫死，pipeline 無此欄位 |
| 新北市青年佔總人口比例 | `data.kpis.cityYouthPopulationShare` = `20.914` | ✅ |
| 新北市青年人口 | `data.kpis.cityYouthPopulation` = `845938` | ✅ |
| 青年人口年增率 YoY | `data.kpis.cityYouthPopulationYoY` = `-1.969` | ✅ |
| 基準年 | `data.kpis.referenceYearRoc` = `114` | ✅ |

> 前端目前 `KpiSummaryRow.tsx` 把 `cityYouthPopulation` 用 29 區加總自算。改接 API 後直接讀 `kpis`，不要自己 reduce。
>
> 全市青年人口五年趨勢（`annual.population`）：110 年 913,345 → 114 年 845,938，佔比 22.79% → 20.91%。

### 4.2 29 區機會指數地圖（`DistrictChoroplethMap`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 地圖填色 | `data.districts[].opportunityIndex` | ✅ |
| hover 卡：機會指數 | 同上 | ✅ |
| hover 卡：留才風險 | `data.districts[].retentionRiskLevel` | ✅ |

> 🔴 **著色門檻需重訂**：`lib/mapColors.ts` 的 `opportunityFillColor` 分界為 50/60/70/80，但實際值域只有 **20.42–54.82**。實測分桶：**28 區落最淺階、1 區落第二階，最深三階全空**——接上真資料後地圖會幾乎全白。建議改用分位數（Q1/median/Q3）動態分級，或由 API 在 `meta` 附上分級門檻。

### 4.3 重點行政區分析（`DistrictHighlightsTable`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 排名（依機會指數降冪） | `data.districts[]` 依 `opportunityIndex` 排序 | ✅ |
| 區名 / 分數 | `district_name` / `opportunityIndex` | ✅ |

### 4.4 青年參政概況（`ParticipationOverviewCard`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 青年參選熱度 `12.8%` | `data.elections.city_councilor_t1_citywide[]`（111 年 `youth_candidacy_rate: 1.674`）| ⚠️ 有值但**單位不同**：是「每十萬青年」不是 `%`，且只有 111 年為 `observed`，103/107 為 `unavailable` |
| 趨勢 `+1.5%` | 需 103/107 的 rate 才能比較 | ❌ 103/107 缺人口分母 |
| 整體服務涵蓋率 `68%` | `data.service_coverage.value` = `49.23` | ⚠️ `status: "partial"` |

### 4.5 青年生育與成家（`FertilityOverviewCard`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 平均生育率 `78.5‰` | `data.annual.fertility.years[-1].city.fertility_rate` = `25.53` | ✅ 有值，但佔位數字 78.5 與真值差距大 |
| 對全市平均比 `92%` | 全市卡無比較對象 | ❌ 語意不成立，此卡應改顯示 YoY |

> 全市生育率五年：110 年 39.39‰ → 114 年 25.53‰（出生數 17,645 → 10,489）。113 年 `quality_status: "partial"`。

### 4.6 施政協助 — 青年總預算（`PolicySupportPanel`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 青年總預算 `NT$ 3.24 億` | `data.policy.currentBudget` = `196153`（單位 `TWD_thousand`，即 1.96 億）| ✅ 有值；**單位是千元，前端需換算** |
| 較前年 `+8.5%` | `data.policy.budgetYoY` = `23.639` | ✅ |
| 預算執行率 `72%` | `data.policy.executionRate` = `null` | ❌ `executionFailure: "final_settlement_unavailable"` |
| 近五年趨勢 | `data.policy.budgetTrend[]` | ⚠️ 110/111 為 `null`，112–114 有值（149029 / 158650 / 196153）|

> 🔴 **同一份 payload 有兩種預算形狀**：`policy.budgetTrend[]`（`value_thousand`）與 `annual.budget_trend[]`（`legal_budget_amount` + 12 個決算欄位）內容重疊。API 對外**只暴露 `policy.*`**，`annual.budget_trend` 視為 pipeline 內部中繼，不進契約。

---

## 5. 青年就業（`/employment`）

### 5.1 機會分布地圖（`OpportunityIndexMap`）

同 §4.2，欄位一致。

### 5.2 區域詳細分析雷達圖（`DistrictDetailCard`）

`GET /api/v1/districts/{districtId}`

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 綜合分數 | `data.metrics.opportunityIndex` | ✅ |
| 工作機會 | `data.metrics.yoiComponents.job` | ✅ |
| 薪資水準 | `data.metrics.yoiComponents.salary` | ✅ |
| 人才資源 | `data.metrics.yoiComponents.talent` | ✅ 但 29 區只有 35 / 65 兩種值 |
| 居住友善度 | `data.metrics.yoiComponents.housing` | ✅ |
| 交通可及 | `data.metrics.yoiComponents.transport` | ✅ |

> 前端 `DistrictDetailCard.tsx` 目前五維是寫死的 `DIMENSIONS` 常數（82/71/80/75/79），且**不隨選取行政區變動**。接上後五個頂點順序固定為：工作機會 → 薪資水準 → 人才資源 → 居住友善度 → 交通可及（順時針）。
>
> ⚠️ 標籤用「居住友善度」不是「居住負擔」——分數越高越好。

### 5.3 跨主題比對分析（`CrossAnalysisScatter`）

`GET /api/v1/analyses/employment-scatter`

**目前 `manifest.artifacts.analyses` 是空的 `{}`，此端點尚無任何 artifact。**

> ✅ **2026-09-12 已決議**：Plot 2（`wage-housing`）Y 軸採 `docs/employment_analysis.md` 文件版定義 ——**每坪平均房價（萬元／坪）**，對應 `house_price_median_wan`。
>
> 🔴 **前端待修**：現有 `CrossAnalysisScatter.tsx` 第二張圖的 `yLabel` 仍是舊字串 **「房價所得比（倍）」**（一個完全不同的指標：房價 ÷ 所得的倍數，而非每坪金額），從未隨 `employment_analysis.md` 更新過——同一次 commit（`2b8f7e2`）只改了 Plot 1 的 X 軸標籤，Plot 2 被漏掉了。接上 API 前需把 `yLabel` 改成 `"每坪平均房價（萬元)"`，並確認 `id`/`chartTitle` 是否也要同步調整為「房價與平均薪資關聯」。

```jsonc
{
  "analysis_id": "employment-scatter",
  "geo_level": "district",
  "plots": [
    {
      "id": "knowledge-wage",
      "title": "起薪與知識型職缺密度相關性（各行政區）",
      "x_label": "知識型職缺比例（%）",
      "y_label": "估算起薪（萬元／年）",
      "points": [{ "district_id": "65000010", "district_name": "板橋區", "x": 0.0, "y": 0.0 }],
      "regression": { "slope": 0.0, "intercept": 0.0, "r_squared": 0.0 },
      "note": "X 軸為職缺要求大專以上學歷的比例，非居住人口教育程度"
    },
    {
      "id": "wage-housing",
      "title": "房價與平均薪資關聯（各行政區）",
      "x_label": "青年平均月薪（萬元）",
      "y_label": "每坪平均房價（萬元）",
      "points": [],
      "regression": { "slope": 0.0, "intercept": 0.0, "r_squared": 0.0 },
      "note": "薪資為房價代理估算值；房價僅含住宅用，平溪區例外使用全類型"
    }
  ],
  "limitations": ["job_vacancies 僅 2026-09-03 單日快照"]
}
```

| 需要的欄位 | 現況 |
|---|---|
| `knowledge_job_ratio` | ❌ 未產出。需 `job_vacancies` raw 的 `EDGRDESC` 學歷欄位，**該欄位未在 curated keys 中，需先確認 transform 有穩定輸出** |
| `estimated_wage`（年薪萬元）| ⚠️ snapshot 有 `adjusted_youth_wage`（板橋 77.61 萬/年），語意相同但名稱不同，需確認是否同一值 |
| `estimated_monthly_wage` | ❌ 未產出，可由上者 ÷12 得出 |
| `house_price_median_wan` | ⚠️ snapshot 有 `house_price_median`（元/坪），需 ÷10000 換算；且**未篩「住宅用」**，目前含土地/車位交易 |
| OLS `slope` / `intercept` / `r_squared` | ❌ 未產出 |

> 前端已移除「都會區/非都會區」分色，29 區改為統一色系，需搭配後端不再回傳 `urban` 欄位。

---

## 6. 青年參政（`/politics`）

### 6.1 參政熱點地圖 + 區域排名

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 地圖填色 / 排名數值 | `data.districts[].youthCandidacyRatePer100k` | ✅ |

**這個欄位的真實語意必須寫清楚**，前端目前誤解了：

- 它是**青年里長（V1）候選人數 ÷ 該區青年人口 × 100,000**，單位 `per_100k_youth`。
- **不是** 0–100 的「指數」，也不是市議員參選率。
- 只有 **111 年（2022）** 一屆為 `observed`；103/107 因缺當年人口分母而 `unavailable`。
- 市議員（T1）是**選區**粒度，31 筆的 `district_id` **全部為 `null`**，無法對應到 29 區，只有全市彙總（`city_councilor_t1_citywide`）可用。

> 🔴 **著色門檻需重訂**：`participationFillColor` 分界 46/54/62/70，實際值域 **0–64.68（中位 6.27）**。實測分桶：**28 區落最淺階、1 區落第三階**。

### 6.2 三大參政 KPI（`ParticipationKpiGrid`）

`GET /api/v1/districts/{districtId}`

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 服務涵蓋率 | `data.metrics.serviceCoverageRate` | ⚠️ **`partial`**。29 區中位數為 **0**，只有少數區有值（板橋 90.79、三重 86.08、中和 90.80、永和 55.13、新莊 41.55）。原因：`youth_service_points` 只有 **9 個據點**（`verified_point_count: 9`），半徑 2500m。全市值 49.23。 |
| 青年里長占比 | **未產出，但可算** | ⚠️ `data.elections.borough_chief_v1[]` 已有逐區 `youth_elected_count` 與 `elected_count`（板橋 111 年 = 3/126 = 2.38%），87 筆涵蓋 103/107/111 三屆、29 區齊全。analytics 只要加一個除法欄位即可。 |
| YRR | ❌ | 分子（青年當選席次占比）可算；分母「青年選舉人數/總選舉人數」**無資料源**，中選會選舉人年齡結構未接。若以戶政青年/成年人口比代替，須標 `is_proxy: true`。 |

`service_coverage` 物件另提供診斷欄位：`radius_m`、`verified_point_count`、`excluded_point_count`、`population_coverage_ratio`（0.9933）、`boundary_village_count`（1039）、`joined_village_count`（1032）、`blocking_reasons`。

### 6.3 資源投入與產出（`ResourceIoCharts`）

`GET /api/v1/analyses/politics-resource-io`

> 🔴 **2026-09-12 前端改版**：第一張圖已從「補助地區分布」（29 區長條圖）換成**「青年局各科別預算比例」**（4 類：綜合規劃／職涯發展／創業資源／資本門設備與投資）。原本的地區別補助缺口自然消失，但換成了新的部門別缺口，見下表。

| 圖 | 需要欄位 | 現況 |
|---|---|---|
| 青年局各科別預算比例（長條）| `budget_by_department[]`（`label`、`amount_thousand`、`share_percent`）| ❌ **無對應資料源**。`youth_budgets` 現有 `business_plan` 只有 3 類（一般行政／青年發展業務／第一預備金），**對不上前端這 4 個科別名稱**（綜合規劃／職涯發展／創業資源／資本門設備與投資）。需向青年局確認決算是否有更細的科別／計畫別拆分，或前端這 4 類本身需要重新對齊既有 3 類 |
| 年度總預算趨勢（折線）| `data.policy.budgetTrend[]` | ⚠️ 圖表軸標籤已明確標「億元」，確認就是總預算（原本「補助金額 vs 預算」的概念疑慮已解除）。但**佔位數值量級對不上**：前端寫死 110–114 為 52／60／68／82／96 億，實際 `policy.budgetTrend` 只有 112–114 有值且為 **1.49／1.59／1.96 億**，差了 40–50 倍，接上真資料後折線會幾乎貼底 |
| 青年局預算執行率（環圈）| `data.policy.executionRate` | ❌ `null`。111/112 決算 PDF 為**影像型待 OCR**；113 年決算欄位已解析但執行率未計算 |

### 6.4 青年關注議題文字雲（`YouthTopicWordCloud`）

`GET /api/v1/analyses/youth-topic-weight`（不再帶 `year` 參數，見下方決議）

⚠️ **這是最接近可用的一項**：analytics 已經跑出來了，只是沒發布進 snapshot。

> ✅ **2026-09-12 已決議**：前端已拿掉年份選擇器（`YouthTopicWordCloud.tsx` 不再有 `YEARS`/`setYear`），改為單一固定文字雲。**API 固定回傳最新一年（114）的 `topics[]`**，不需要 `year` query 參數。
>
> `youth_topic_weight/all.json` 底層仍保留 110–114 完整五年資料，這份歷史序列不丟棄——只是目前 UI 不消費，未來若要做「議題歷年變化」之類的功能可以直接復用，不需重新計算。

底層 pipeline 產出（`data-pipeline/data/analytics/youth_topic_weight/all.json`）仍是完整 5 年包：

```jsonc
{
  "metric_id": "youth_topic_weight",
  "calculation_version": "1",
  "source_datasets": ["join_proposals", "youth_council_minutes"],
  "normalization": "yearly_max",
  "years": [
    { "year_roc": 110, "topics": [
      { "label": "社會住宅", "weight": 5, "signal": "minutes",
        "join_mentions": 0, "minutes_mentions": 1,
        "resolved": true, "escalated": false,
        "join_support_score": 0.0, "raw_score": 3.0 }
    ]}
    // …110–114 共 5 筆
  ]
}
```

**API 對外回傳的形狀**（backend 從上面挑出 `year_roc === 114` 那筆，拆掉 `years` 包裝）：

```jsonc
{
  "analysis_id": "youth-topic-weight",
  "year_roc": 114,
  "topics": [
    { "label": "社會住宅", "weight": 5, "signal": "minutes",
      "join_mentions": 0, "minutes_mentions": 1,
      "resolved": true, "escalated": false }
  ]
}
```

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 議題文字 | `topics[].label`（取 `years[].year_roc === 114` 該筆）| ✅ |
| 字級（1–5）| `topics[].weight` | ✅ |
| ~~年份選擇器 110–114~~ | ~~`years[].year_roc`~~ | 🗑️ **UI 已移除**，不再需要前端切換；backend 固定取 114 |

**待辦**：把 `youth_topic_weight` 加進 `manifest.artifacts.analyses`，`publish_homepage_snapshot()` 目前只寫 `dashboard_overview` 與 `district_details`。發布時只需固定取 `years[].year_roc === 114` 那一筆的 `topics[]`，不必整包 5 年都送到前端。

> 另有 `youth_keyword_frequency/all.json`（`calculation_version: 5`），但其 top terms 是「問題／台灣／以及／工作／應該／一個」等**未濾除的常見詞**，不適合直接當文字雲。文字雲請用 `youth_topic_weight`（22 個固定議題詞），不要用 keyword_frequency。

---

## 7. 青年生育（`/fertility`）

### 7.1 生育分佈地圖（`FertilityDistributionMap`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 地圖填色 | `data.districts[].fertilityRate` | ✅ |

> 🔴 **著色門檻需重訂**：`fertilityFillColor` 分界 39/42/45/49（註解說「CSV 約落在 35–54」），但真實值域為 **12.67–74.92**，分布形狀完全不同。實測分桶：**28 區落最淺階、1 區落最深階，中間三階全空**。

### 7.2 核心生育指標（`CoreFertilityKpiPanel`）

未選取時顯示全市，選取後顯示該區。

| UI 顯示 | 全市欄位 | 各區欄位 | 現況 |
|---|---|---|---|
| 青年總生育數 | `annual.fertility.years[-1].city.births_mother_age_18_35` = `10489` | `.districts[].births_mother_age_18_35` | ✅ |
| 育齡青年生育率 | `.city.fertility_rate` = `25.53‰` | `.districts[].fertility_rate` | ✅ |
| 青年人口占比 | 由 `annual.population` 算得 `20.91%` | `annual.population.years[-1].districts[].youth_share_percent` | ✅ |
| 托育資源覆蓋率 | ❌ | ❌ | **未產出**。需以托育點位畫 1.0 km buffer × 里界面積分攤，分母為 `youth_18_35_female`。`babysitting_places` 有 391 筆名冊但**無經緯度**，須先 geocoding |
| 行內 YoY（與去年比）| `annual.fertility.years[]` 相鄰年相減 | 同 | ✅ 五年序列齊全 |
| 右側「較平均」框 | — | `districts[].fertilityVsCityAvg` | ✅ 直接可用，不需前端自算 |

> 前端 `placeholderMetrics.ts` 的 `buildFertilityMetrics()` 種子亂數在接上 API 後整檔刪除。
>
> ⚠️ 年齡口徑：前端文案若仍有「20–39 歲」須改為 **18–35 歲**，與 `births_mother_age_18_35` 對齊。

### 7.3 疊圖比較分析（`OverlayComparisonPanel`）

`GET /api/v1/analyses/fertility-overlay`

| 需要欄位 | 現況 |
|---|---|
| 散佈點 x = `opportunityIndex`、y = `fertilityRate` | ✅ **兩者都已在 `districts[]`**，前端理論上可自行配對 29 點 |
| OLS `slope` / `intercept` / `r_squared` | ❌ 未產出，須由 analytics 算（前端目前自己用最小平方法在畫，違反「前端不計算」邊界）|

> 這是五個散佈圖裡最快能上線的——只缺一條迴歸線。

### 7.4 青年成家環境友善度（`FamilyFriendlinessPanel`）

`GET /api/v1/analyses/fertility-family-friendliness`

| 需要欄位 | 現況 |
|---|---|
| `fafi_score`（0–100）| ❌ 未產出。公式 `(norm(托育覆蓋率) + yoiComponents.housing + norm(estimated_wage)) / 3` |
| `fafi_level`（分位數分級）| ❌ 未產出 |

> 🔴 前端目前**拿 `policySupportScore` 充當友善度分數**，而該欄位在 pipeline **完全不存在**，只在 `districts.csv` fixture 裡。三項輸入中 `yoiComponents.housing` ✅ 已有、托育覆蓋率 ❌、薪資 ⚠️（`adjusted_youth_wage` 可代）。
>
> ⚠️ 顏色分級要從固定門檻（>70 綠 / 50–70 黃 / <50 紅）改為吃後端傳的 `fafi_level`（依 Q1/Q3 分位數）。

---

## 8. 施政協助（`/policy-support`）

### 8.1 政策成效追蹤（`PolicyOutcomeTracker`）

`GET /api/v1/analyses/policy-outcomes`

```jsonc
{
  "analysis_id": "policy-outcomes",
  "geo_level": "county",
  "wageTrend":       [{ "year_roc": 110, "wage": null, "yoy": null, "quality_status": "observed" }],
  "populationTrend": [{ "year_roc": 110, "population": 913345, "yoy": null }],
  "currentWageGrowth": null,
  "currentPopGrowth": null,
  "desiredDirection": { "wageGrowth": "up", "populationChange": "up" }
}
```

| UI 顯示 | 需要欄位 | 現況 |
|---|---|---|
| 薪資成長率（大字 `2.8%`）| `currentWageGrowth` | ❌ 未產出。`wages` 有 110–113（四年），採 25–29 歲組；**只有新北市整體，不可拆 29 區** |
| 薪資走勢圖 | `wageTrend[]` | ❌ 未產出，但來源具備 |
| 青年人口世代變化率（大字 `-3.5%`）| `currentPopGrowth` | ⚠️ 可由 `annual.population` 算：110→114 為 913,345→845,938（−7.4%），單年 YoY −1.97% 已在 `kpis.cityYouthPopulationYoY` |
| 人口走勢圖 | `populationTrend[]` | ✅ **資料已在 `annual.population.years[]`**，只差組成陣列 |

> 基期年（110）的 YoY 必為 `null`，前端畫線與箭頭需防呆。
>
> ⚠️ 年齡口徑：前端 `metricLabel` 寫「20–35 歲人口近五年變化」，應改為 **18–35 歲**。
>
> 🔴 **新增 `desiredDirection` 欄位，原因**：`PolicyOutcomeTracker.tsx` 的 `trendColor()` 對 up/down 只有一套寫死的顏色規則，但這兩張卡的「好壞方向」相反——薪資漲是好事（`up` 該綠）、青年人口跌才是被追蹤的警訊（`down` 才是壞事，`up` 才該綠）。2026-09-12 的改動把 up/down 顏色對調了一次，套用到兩張卡上必有一張會判斷反：現況是「薪資成長 +2.8%」被畫成警示色（`text-risk-high`），看起來像壞消息。契約補一個 `desiredDirection: "up"|"down"` 每指標各自標明，前端依此決定顏色，不要用共用的 `trend` 欄位硬判。

### 8.2 AI 政策決策輔助（`PolicyDecisionAssistant`）

**不在本契約範圍。**

該區塊屬 `ai-service`，`docs/superpowers/specs/2026-09-10-backend-read-api-design.md` 已明確將 AI prompt / Bedrock / RAG / 政策回答生成列為 Backend 的 **Excluded**。端點形狀（`POST /api/v1/assistant/chat` 或獨立服務）由 AI 模組負責人另行定義。

前端現況：固定回覆「我只是個語言模型，這件事我幫不上忙。」，延遲 700ms。

---

## 9. 資料現況 Checklist

### ✅ 真值已在 published snapshot，可立即串接（10 項）

- [x] 主頁 KPI — 新北青年人口、佔比、YoY
- [x] 主頁 29 區機會指數地圖（⚠️ 需重訂著色門檻）
- [x] 主頁重點行政區排名
- [x] 就業 機會分布地圖
- [x] 就業 雷達圖五維度 `yoiComponents`
- [x] 參政 熱點地圖＋區域排名（⚠️ 需重訂門檻、需正名單位）
- [x] 生育 分佈地圖（⚠️ 需重訂門檻）
- [x] 生育 核心指標三項（總生育數、生育率、青年人口占比）＋ 對全市平均比
- [x] 主頁 青年總預算＋YoY＋近五年趨勢（⚠️ 單位千元、110/111 為 null）
- [x] 施政 人口走勢圖（資料在 `annual.population`，只差組陣列）

### ⚠️ analytics 已算出，但未發布進 snapshot（1 項）

- [ ] **參政 青年關注議題文字雲** — `youth_topic_weight/all.json` 已有資料；UI 年份選擇器已移除（2026-09-12），只需固定發布 114 年那筆 `topics[]` 進 `manifest.artifacts.analyses`

### ⚠️ 部分可用，資料覆蓋不足（2 項）

- [ ] **服務涵蓋率** — `status: "partial"`，只有 9 個據點，29 區中位數為 0。需補 `youth_service_points` 清單與 geocoding
- [ ] **主頁青年參選熱度** — 只有 111 年 `observed`，103/107 缺人口分母，無法算趨勢

### ⚠️ 分子分母都有，只差 analytics 補一個欄位（3 項）

- [ ] **青年里長占比** — `borough_chief_v1[].youth_elected_count / elected_count`，87 筆三屆 29 區齊全
- [ ] **生育 疊圖迴歸線** — x/y 兩軸都已在 `districts[]`，只缺 OLS `slope`/`intercept`/`r_squared`
- [ ] **施政 人口成長率大字** — `annual.population` 相鄰年相減即得

### ❌ 算法已定義，但欄位未產出（5 項）

- [ ] **就業 散佈圖 1** — 缺 `knowledge_job_ratio`（需確認 `EDGRDESC` 是否穩定輸出）+ OLS
- [ ] **就業 散佈圖 2** — 缺住宅用篩選的 `house_price_median_wan` + `estimated_monthly_wage` + OLS
- [ ] **生育 托育資源覆蓋率** — `babysitting_places` 391 筆無經緯度，須先 geocoding 才能做 1km buffer
- [ ] **生育 FaFI 友善度** — 三項輸入只有 `housing` 齊備
- [ ] **施政 薪資成長率＋走勢** — `wages` 110–113 已有，只差 analytics

### ❌ 無資料源，需新建 collector（3 項）

- [ ] **參政 青年局各科別預算比例**（2026-09-12 取代原「補助地區分布」）— `youth_budgets` 的 `business_plan` 只有 3 類，對不上前端 4 個新科別名稱，需向青年局確認是否有更細的科別／計畫別決算拆分
- [ ] **參政 預算執行率** — 111/112 決算 PDF 為影像型待 OCR，113 欄位已解析但未算執行率
- [ ] **參政 YRR** — 中選會選舉人年齡結構無資料源

### ❌ 前端硬編、pipeline 無對應概念（4 項）

- [ ] 主頁 全台青年人口 `4,820,000`（`quality: "proxy"`，無全國人口 collector）
- [ ] 主頁 全台佔比 `20.6%`
- [ ] 主頁 生育卡「對全市平均比 92%」（全市層級無比較對象，應改顯示 YoY）
- [ ] `policySupportScore` 欄位（只存在於 `districts.csv` fixture）

---

## 10. 已知不一致與待辦

| # | 問題 | 位置 | 建議處理 |
|---|---|---|---|
| 1 | spec 檔含未解 merge conflict（4 處）| `docs/superpowers/specs/2026-09-10-backend-read-api-design.md` | 解衝突，兩處都採 `ours` |
| 2 | 三張 choropleth 門檻全部與真實值域不符（2026-09-12 改為主色調可調的 3 階漸層 `tieredFillColor`，門檻改為 opportunity `[60,75]`、participation `[52,62]`、fertility `[41,46]`，但問題本質未變）| `frontend/src/lib/mapColors.ts` | 改分位數動態分級，或 API 於 `meta` 附門檻 |
| 3 | `youthParticipationIndex` 名實不符（實為里長參選率 per 100k，非 0–100 指數）| 前端型別、fixture、mapColors | 改名 `youthCandidacyRatePer100k`，UI 標籤與單位一併更新 |
| 4 | 預算有兩套形狀（`policy.*` vs `annual.budget_trend`）| `dashboard_overview.json` | API 只暴露 `policy.*` |
| 5 | 子分數三套命名（`yoiComponents.job` / `score_job` / 無）| pipeline、分析文件、前端 | 統一用 `yoiComponents.*` |
| 6 | `district_id` vs `id` 命名分歧 | pipeline vs 前端型別 | 統一 `district_id`，見 §2 |
| 7 | `manifest.artifacts.analyses` 為空 `{}` | `published_snapshot.py` | 擴充以發布 analyses artifacts |
| 8 | `policySupportScore` 無資料源卻被生育頁使用 | `FamilyFriendlinessPanel.tsx` | 改接 `fafi_score`，在那之前顯示「資料待補」 |
| 9 | 前端自行做 OLS 迴歸（違反邊界）| `OverlayComparisonPanel.tsx` | 改由 analytics 提供係數 |
| 10 | `house_price_median` 未篩住宅用，含土地/車位 | `transform` | 加 `transaction_type` 篩選，平溪區例外 fallback |
| 11 | `EDGRDESC`（職缺學歷）未在 curated keys | `job_vacancies` transform | 確認是否穩定輸出 |
| 12 | 年齡口徑文案殘留 20–39 / 20–35 | 生育頁、施政頁 | 全部改 18–35 |
| 13 | `yoiComponents.talent` 29 區只有 35/65 兩值 | `college_majors` 為學校所在地 | 已將權重降至 0.05，UI 可加註 |
| 14 | `youth_keyword_frequency` top terms 為未濾除常見詞 | `youth_keyword_config.json` | 文字雲改用 `youth_topic_weight` |
| 15 | 就業散佈圖 Plot 2 的 `yLabel` 仍是「房價所得比（倍）」，未跟上文件決議的「每坪平均房價」 | `CrossAnalysisScatter.tsx` | 已於 2026-09-12 決議採文件版並改字串，已完成 |
| 16 | 文字雲年份選擇器已移除，UI 改為單一固定畫面 | `YouthTopicWordCloud.tsx` | 已於 2026-09-12 決議固定回傳 114 年，見 §6.4；`year` query 參數不再需要 |
| 17 | 「資源投入與產出」第一張圖從地區別補助換成部門別預算比例，且新科別名稱對不上 `youth_budgets.business_plan` 既有 3 類 | `ResourceIoCharts.tsx` | 見 §6.3；需與青年局確認決算科別拆分口徑 |
| 18 | `PolicyOutcomeTracker` 的 up/down 顏色寫死且方向對調，兩張卡好壞方向相反卻共用同一規則，薪資成長 +2.8% 現顯示為警示色 | `PolicyOutcomeTracker.tsx` | 契約新增 `desiredDirection` 欄位，見 §8.1；前端改依此欄位決定顏色，不要寫死 |

---

## 附錄 A：29 區 `district_id` 對照

以 `data-pipeline/config/districts.json` 為準，格式為 8 碼數字，新北市前綴 `65000`：

| district_id | district_name |
|---|---|
| 65000010 | 板橋區 |
| 65000020 | 三重區 |
| 65000030 | 中和區 |
| 65000040 | 永和區 |
| 65000050 | 新莊區 |
| 65000060 | 新店區 |
| 65000070 | 樹林區 |
| 65000080 | 鶯歌區 |
| 65000090 | 三峽區 |
| 65000100 | 淡水區 |
| 65000110 | 汐止區 |
| 65000120 | 瑞芳區 |
| 65000130 | 土城區 |
| 65000140 | 蘆洲區 |
| 65000150 | 五股區 |
| 65000160 | 泰山區 |
| 65000170 | 林口區 |
| 65000180 | 深坑區 |
| 65000190 | 石碇區 |
| 65000200 | 坪林區 |
| 65000210 | 三芝區 |
| 65000220 | 石門區 |
| 65000230 | 八里區 |
| 65000240 | 平溪區 |
| 65000250 | 雙溪區 |
| 65000260 | 貢寮區 |
| 65000270 | 金山區 |
| 65000280 | 萬里區 |
| 65000290 | 烏來區 |

以 `config/districts.json` 為單一真實來源；Backend 應於啟動時載入並驗證 29 筆齊全且 id 唯一。

✅ **已驗證**：`frontend/public/Map_NewTaipei.json` TopoJSON 的 29 個 `properties.id` 與本表**完全吻合，零筆落差**。地圖填色可直接用 `district_id` 對接，不需任何轉換表。

## 附錄 B：可用 curated datasets 與青年適用性

`youth_eligibility` 三態決定該資料能否用於 18–35 歲核心指標：

| 等級 | 意義 | 可用資料集 |
|---|---|---|
| `eligible` | 可直接作核心青年指標 | `population`（`youth_18_35_total`）、`births`（`births_mother_age_18_35`）|
| `proxy_only` | 僅近似參考，須標 `is_proxy` | `wages`（官方年齡組，新北市整體）|
| `context_only` | 只作青年生活環境背景 | `house_prices`、`rentals`、`job_vacancies`、`bus_stops`、`railway_stops`、`bike_stops`、`babysitting_places`、`youth_budgets`、`movement`、`marriages` 等 |

規則：

1. 區級比較只能用 `geo_level=district` 且 `district_id` 非 `null` 的資料。
2. `county` / `national` 資料與區級並用時，必須標示為 proxy。
3. 來源沒有的期間**不以 0 補值**，一律 `null`。
