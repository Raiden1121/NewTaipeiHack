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

### 1.5 時間粒度（重要——2026-09-12 補寫）

**這是本文件先前最大的缺口**：很多資料底層跨好幾個年度／屆別，但前端 KPI 卡通常只想要「現在」的一個數字。契約之前只寫了資料存不存在，沒寫「這個欄位到底是陣列還是純量，如果是陣列該怎麼收斂成一個數字」——導致同一份底層資料在不同元件被用對、用錯、或乾脆沒用。

三種形狀，任何欄位只能是其中一種，寫欄位時務必標明是哪一種：

| 形狀 | 意思 | 範例 |
|---|---|---|
| **純量（Scalar）** | 就是現在這一刻的一個數字／字串，前端直接顯示，不需要自己挑 | `districts[].opportunityIndex`、`districts[].youthBoroughChiefRatioPercent` |
| **時間序列（Series）** | 一個陣列，每個元素是一年／一屆，**前端要嘛整包拿去畫趨勢圖，要嘛不應該只挑一個元素當「現在」的值**——如果需要「現在」的純量，那應該是 Backend 另外送一個 Scalar 欄位，不是叫前端自己篩 | `annual.population.years[]`（5 個元素，110–114，畫趨勢折線圖用）、`annual.fertility.years[]`（同上）、`policy.budgetTrend[]`（5 個元素，折線圖用） |
| **選擇性 Series（Historical detail）** | 陣列保留給「以後可能要做歷年比較」的功能，**目前沒有任何 UI 直接消費整包**，KPI 卡都是吃另外提供的 Scalar | `elections.borough_chief_v1[]`（3 屆 × 29 區＝87 筆，目前無元件直接用整包；KPI 卡吃 `districts[].youthBoroughChiefRatioPercent` 或 `elections.borough_chief_v1_citywide`）|

**本次修正的具體案例**（都是「Series 有了，但沒人告訴前端該怎麼收斂成 Scalar」造成的）：

1. **`youth-topic-weight`**：底層 pipeline 產出是 5 年 Series（110–114），但 UI 拿掉年份選擇器後只要 1 年。契約已決議：**API 對外固定收斂成 Scalar 輸出**（`{ analysis_id, year_roc: 114, topics: [] }`，不帶 `years` 包裝），底層 Series 留在 pipeline 內部，不對外暴露。見 §6.4。
2. **青年里長占比**：`elections.borough_chief_v1[]` 是 3 屆 Series，但契約從沒說過 KPI 卡該挑哪一屆——這正是導致它從沒被前端消費、永遠顯示「資料待補」的原因（並非缺資料，是缺「怎麼收斂」的規格）。已補上 `districts[].youthBoroughChiefRatioPercent`（純量，固定 111 年屆）與 `elections.borough_chief_v1_citywide`（純量，全市加總），見 §6.2。
3. **`policy-outcomes.desiredDirection`**：不是時間維度問題，但同一類錯誤——欄位語意（方向）沒寫清楚，前端只好自己寫死猜測，猜錯一次就對調成 bug。見 §8.1。

**規則**：新增任何「底層有多年資料」的欄位時，契約必須同時回答：(a) 這個欄位是 Scalar 還是 Series；(b) 如果是 Scalar，取的是哪一年／哪一屆、為什麼；(c) 如果是 Series，前端該把它整包畫成圖，還是只是保留供未來使用（不該有任何元件從 Series 裡「挑一個」當作現在的值——這個收斂邏輯永遠該在 Backend 做，不在前端）。

---

## 2. 命名映射（重要）

`shared.md` 明文警告過這個問題，而它**已經發生了**：同一個概念目前有三套名字。

| 概念 | pipeline 實際輸出 | frontend 現有型別 | 分析文件寫的 |
|---|---|---|---|
| 行政區代碼 | `district_id` | `id` | `id` |
| 行政區名稱 | `district_name` | `name` | `name` |
| 工作機會子分數 | `yoiComponents.job` | （無） | `score_job` |
| 薪資子分數 | `yoiComponents.salary` | （無） | `score_salary` |
| 青年活力與發展子分數 | `yoiComponents.talent` | （無） | `score_talent` |
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

每筆包含原始指標、五個子分數、公開 YOI 與品質欄位；核心 YOI 欄位如下。

**原始指標（單位為實際量綱）**

| 欄位 | 單位 | 板橋區實值 |
|---|---|---|
| `youth_18_35_total` | 人 | 107970 |
| `youth_ratio` | % | 19.6394 |
| `youth_yoy` | % | -2.6043 |
| `vacancies_per_km2` | 職缺/km² | 50.4217 |
| `vacancies_per_10k_youth` | 職缺/萬青年 | 99.38 |
| `occupation_shannon_index` | — | 3.59 |
| `talent_demand_yoy` | % | -6.00 |
| `salary_median` | TWD/月 | 35000 |
| `high_salary_ratio` | 比例 0–1 | 0.0378 |
| `adjusted_youth_wage` | 萬元/年（相容性／散點圖 proxy，不進 S_salary） | 77.61 |
| `college_student_density` | 人/km² | 967.55 |
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
| `opportunityIndex` | number | 公開 YOI，先算 `YOI_raw` 再做 P5/P95 norm | **0 – 100**（中位 47.6722）|
| `yoiRaw` | number \| null | `0.25·job + 0.25·salary + 0.15·talent + 0.20·housing + 0.15·transport`，未做最終 norm | **17.6149 – 52.4448**（中位 37.2857）|
| `yoiComponents` | object | 五個 0–100 子分數 | 見下 |
| `normalizedInputs` | object | 18 個原始指標標準化後的 0–100 值，除錯用；包含相容性欄位 |
| `retentionRiskLevel` | `"low"\|"medium"\|"high"` | 低 8 / 中 13 / 高 8 區 |
| `fertilityRate` | number | 育齡青年生育率 ‰ | **12.67 – 74.92**（中位 26.70）|
| `fertilityVsCityAvg` | number | 對全市平均比 % | 49.63 – 293.51 |
| `serviceCoverageRate` | number | 服務涵蓋率 % | **0 – 90.80（中位 0）** |
| `serviceCoverageStatus` | string | 目前 29 區全為 `"partial"` |
| `youthCandidacyRatePer100k` | number | 青年**里長候選人**數/十萬青年（參選密度，分母是人口）| **0 – 64.68**（中位 6.27）|
| `youthParticipationIndex` | number | 同上，deprecated alias |
| `youthBoroughChiefRatioPercent` | number \| null | 青年**里長當選**占比 %（席次占比，分母是總當選席次）；固定 111 年屆，見 §6.2 | 依 mock 值域約 2–10% |
| `qualityStatus` | string | 目前 29 區全為 `"observed"` |
| `sourcePeriods` | object | 19 個資料集各自的來源期間 |

`yoiComponents` 各子分數實際範圍：

| 子分數 | min | median | max | 備註 |
|---|---|---|---|---|
| `job` | 10.00 | 44.16 | 86.29 | |
| `salary` | 0.22 | 39.49 | 91.61 | |
| `talent` | 3.02 | 53.15 | 85.96 | 青年人口佔比、青年人口 YoY、大專學生密度 |
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

> `opportunityIndex` 現在先由 `YOI_raw` 做 P5/P95 norm，公開值域為 **0–100**；目前 29 區中位數為 47.6722。若前端仍採固定門檻，應依這個公開值域重新檢查分桶；更穩健的作法仍是由 API 提供分位數門檻。

### 4.3 重點行政區分析（`DistrictHighlightsTable`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 排名（依機會指數降冪） | `data.districts[]` 依 `opportunityIndex` 排序 | ✅ |
| 區名 / 分數 | `district_name` / `opportunityIndex` | ✅ |

### 4.4 青年參政概況（`ParticipationOverviewCard`）

| UI 顯示 | 欄位 | 現況 |
|---|---|---|
| 青年參選熱度 `12.8%` | `data.elections.city_councilor_t1_citywide[]`，取 `quality_status === "observed"` 的最新一筆（111 年 `youth_candidacy_rate: 1.674`）| ✅ 已接上（`ParticipationOverviewCard.tsx`），且正確標成「每十萬青年」而非 `%`——原本擔心的單位誤用已避開，元件是靠篩 `quality_status` 挑年份，不是直接拿陣列最後一筆，示範了 §1.5 說的「Series 該怎麼在前端安全收斂」 |
| 趨勢（原設計 `+1.5%`）| 需 103/107 的 rate 才能比較 | ❌ 103/107 缺人口分母，103/107 兩年 `quality_status` 皆為 `unavailable`；目前 UI 已移除趨勢箭頭，只顯示單一數值＋屆別註記，不再嘗試比較 |
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
| 青年活力與發展 | `data.metrics.yoiComponents.talent` | ✅ 29 區皆有區級變異（3.02–85.96） |
| 居住友善度 | `data.metrics.yoiComponents.housing` | ✅ |
| 交通可及 | `data.metrics.yoiComponents.transport` | ✅ |

> 前端 `DistrictDetailCard.tsx` 已改為讀取選取行政區的 `yoiComponents`。五個頂點順序固定為：工作機會 → 薪資水準 → 青年活力與發展 → 居住友善度 → 交通可及（順時針）。
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

`GET /api/v1/districts/{districtId}`（選取行政區時）／`GET /api/v1/dashboard/overview`（全市，未選取時）

| UI 顯示 | 選取行政區時 | 未選取（全市）時 | 現況 |
|---|---|---|---|
| 服務涵蓋率 | `data.metrics.serviceCoverageRate` | `data.service_coverage.value` | ⚠️ **`partial`**。29 區中位數為 **0**，只有少數區有值（板橋 90.79、三重 86.08、中和 90.80、永和 55.13、新莊 41.55）。原因：`youth_service_points` 只有 **9 個據點**（`verified_point_count: 9`），半徑 2500m。全市值 49.23。 |
| 青年里長占比 | `districts[].youthBoroughChiefRatioPercent`（純量，%）| `elections.borough_chief_v1_citywide.ratio_percent`（純量，%）| ✅ **已修好並接上**。兩者都固定取**民國 111 年屆**——見下方時間粒度說明。 |
| YRR | ❌ | ❌ | 分子（青年當選席次占比）可算；分母「青年選舉人數/總選舉人數」**無資料源**，中選會選舉人年齡結構未接。若以戶政青年/成年人口比代替，須標 `is_proxy: true`。 |

> 📌 **青年里長占比的時間粒度（見 §1.5）**：`elections.borough_chief_v1[]` 底層是 **3 屆 Series**（103／107／111 年，共 87 筆，每區各一筆），但這只是保留給未來歷年比較用的明細，**KPI 卡不該從這個陣列裡自己挑一筆**。契約新增兩個 Scalar 欄位讓前端直接用：
> - `districts[].youthBoroughChiefRatioPercent: number | null` — 該區純量，選取行政區時用。
> - `elections.borough_chief_v1_citywide: { year_roc, elected_count, youth_elected_count, ratio_percent }` — 全市加總純量，未選取時用。
>
> 兩者都固定取 **111 年**（`youth_elected_count / elected_count × 100`）：103／107 年雖然有 `elected_count`/`youth_elected_count`，但沒有可靠的候選人年齡分母核對來源，只有 111 年可信賴，跟 `districts[].youthCandidacyRatePer100k`（同樣是里長 V1 資料，只是分母換成青年人口而非總當選席次）用同一屆是一致的——注意這兩個欄位語意不同，`youthCandidacyRatePer100k` 是「青年里長參選密度」（分母是人口），`youthBoroughChiefRatioPercent` 是「青年里長席次占比」（分母是總席次），不要混用。103／107 兩屆的明細留在 `borough_chief_v1[]` 裡不丟棄，之後若要做「近三屆青年里長占比趨勢」可以直接用，不用重算。
>
> `ParticipationKpiGrid.tsx` 已改為讀這兩個 Scalar 欄位（2026-09-12）。

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

### ✅ 真值已在 published snapshot，可立即串接（13 項）

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
- [x] 施政 人口成長率大字 `currentPopGrowth`（2026-09-12 已在 API 產出，與 `kpis.cityYouthPopulationYoY` 一致）
- [x] 參政 青年里長占比（2026-09-12 修好：新增 `districts[].youthBoroughChiefRatioPercent` 與 `elections.borough_chief_v1_citywide`，`ParticipationKpiGrid.tsx` 已接上，見 §6.2）
- [x] 施政 `desiredDirection`（2026-09-12 API 已產出並接上 `PolicyOutcomeTracker.tsx`，見 §8.1）

### ⚠️ analytics 已算出，但未發布進 snapshot（1 項）

- [ ] **參政 青年關注議題文字雲** — `youth_topic_weight/all.json` 已有資料；UI 年份選擇器已移除（2026-09-12），只需固定發布 114 年那筆 `topics[]` 進 `manifest.artifacts.analyses`

### ⚠️ 部分可用，資料覆蓋不足（2 項）

- [ ] **服務涵蓋率** — `status: "partial"`，只有 9 個據點，29 區中位數為 0。需補 `youth_service_points` 清單與 geocoding
- [ ] **主頁青年參選熱度** — 只有 111 年 `observed`，103/107 缺人口分母，無法算趨勢

### ⚠️ 分子分母都有，只差 analytics 補一個欄位（1 項）

- [ ] **生育 疊圖迴歸線** — x/y 兩軸都已在 `districts[]`，`regression` 欄位已存在但目前是 `{slope:0, intercept:0, r_squared:0}` 假值，尚未算真實 OLS

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
| 13 | `yoiComponents.talent` 仍含學校所在地 proxy | `college_majors` 為學校所在地；人口欄位為結構與變動訊號，不等同人才品質 | 已改為青年人口佔比 0.4、青年人口 YoY 0.4、大專學生密度 0.2；總權重 0.15，UI 可加註 |
| 14 | `youth_keyword_frequency` top terms 為未濾除常見詞 | `youth_keyword_config.json` | 文字雲改用 `youth_topic_weight` |
| 15 | 就業散佈圖 Plot 2 的 `yLabel` 仍是「房價所得比（倍）」，未跟上文件決議的「每坪平均房價」 | `CrossAnalysisScatter.tsx` | 已於 2026-09-12 決議採文件版並改字串，已完成 |
| 16 | 文字雲年份選擇器已移除，UI 改為單一固定畫面 | `YouthTopicWordCloud.tsx` | 已於 2026-09-12 決議固定回傳 114 年，見 §6.4；`year` query 參數不再需要 |
| 17 | 「資源投入與產出」第一張圖從地區別補助換成部門別預算比例，且新科別名稱對不上 `youth_budgets.business_plan` 既有 3 類 | `ResourceIoCharts.tsx` | 見 §6.3；需與青年局確認決算科別拆分口徑 |
| 18 | `PolicyOutcomeTracker` 的 up/down 顏色寫死且方向對調，兩張卡好壞方向相反卻共用同一規則，薪資成長 +2.8% 現顯示為警示色 | `PolicyOutcomeTracker.tsx` | ✅ 2026-09-12 已修：API 加 `desiredDirection`，前端改讀它，拿掉本地寫死常數 |
| 19 | **Repo 與正式部署脫鉤**：`infrastructure/modules/api/lambda/handler.py` 唯一一次 commit（`fee5418`）的內容，與 `frontend/.env` 指向的正式 API Gateway 實際回傳的內容不一致——正式環境已經是對的（`youth-topic-weight` 攤平格式、`budget_by_department`、`desiredDirection` 都在），但 repo 裡的原始碼還是舊的錯誤版本。代表有人手動改過部署但沒 commit，下次 `terraform apply` 會把正式環境打回錯誤格式 | `handler.py` | ✅ 2026-09-12 已修：重寫 `handler.py` 對齊正式環境的回應，另外補上 `youthBoroughChiefRatioPercent`／`borough_chief_v1_citywide`（正式環境目前還沒有，需要重新部署）；**部署本身需要另外執行 `terraform apply`，本次只改了原始碼，沒有觸發部署** |
| 20 | 青年里長占比從未被前端消費：`elections.borough_chief_v1[]` 資料齊全，但契約沒寫「KPI 卡該收斂成哪一年」，導致沒人接，永遠顯示「資料待補」——這是 §1.5 新增時間粒度規則要解決的典型案例 | `ParticipationKpiGrid.tsx` | ✅ 2026-09-12 已修：新增 `districts[].youthBoroughChiefRatioPercent` 與 `elections.borough_chief_v1_citywide` 兩個 Scalar 欄位（固定 111 年屆），前端改讀這兩個欄位，見 §6.2 |
| 21 | `PoliticsResourceIoAnalysis` 型別的 `geo_level` 寫 `"district"`、`grants_by_district: unknown[]` 是從未用過的死欄位，跟正式環境實際回傳的 `geo_level: "county"`（且無此欄位）不符 | `frontend/src/lib/api/types.ts` | ✅ 2026-09-12 已修：`geo_level` 改 `"county"`，`grants_by_district` 刪除，`budget_by_department` 改為必要欄位（不再是 optional）|

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
