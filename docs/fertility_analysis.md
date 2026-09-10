# 青年生育（FertilityPage）參數分析與資料源對應 

> 本文件依據最新的前端 React 元件架構（`features/fertility`），對齊現有資料庫（`births`, `population`, 托育中心清單）並定義各項指標。
> ⚠️ **統一收斂年齡口徑**：前端 UI 圖示上的「20-39 歲」將**全面改為「18-35 歲」**，以與全站「青年」定義一致。這不但不會增加資料工程師的困難，反而能直接複用已建好的 D1/E1 資料管道，解決資料錯位問題。

---

## 一、前端元件與參數對應表

青年生育頁分為 **2 大 Section**。

### Section 1：新北市青年生育分佈總覽 + 核心生育指標
(`DistributionMap.tsx` + `CoreMetricsPanel.tsx`)

#### 1-1 分佈總覽地圖（左側）

| UI 顯示項目 | 對應欄位 | 資料源 | 計算邏輯 |
|------------|---------|-------|---------|
| 地圖顏色（生育率低→高） | `fertilityRate` | **E1** `births` + **A2** `18_35_female` | 計算該區育齡青年生育率。依 29 區分數的百分位數（Q1, Q3）區分深淺色，與機會地圖邏輯相同。 |

#### 1-2 核心指標 (Core Metrics)（右側）

> **狀態顯示邏輯**：未點選地圖時，顯示「新北市全市」加總平均值；點選特定行政區後，顯示該區的獨立數值。

| UI 顯示項目 | 對應欄位 | 資料源 | 計算邏輯 |
|------------|---------|-------|---------|
| 青年總生育數 | `total_births` | **E1** `births` | 該區（或全市）當年「生母年齡 18-35 歲」的嬰兒出生數加總。 |
| 平均生育率 | `fertilityRate` | **E1** + **A2** | 該區（或全市）`total_births` ÷ `youth_18_35_female` × 1000‰ |
| 青年人口占比 | `youth_ratio` | **A1** `population` | 該區（或全市） 18-35 歲總人口 ÷ 該區（或全市）總人口 × 100% |
| 托育資源覆蓋率 | `daycare_coverage` | 托育點位 + **A2** + 里界 | **以 1km 步行半徑與面積分攤法**計算覆蓋的青年女性比例（詳見第二節） |

> 📝 **關於「平均生育率」的中文解釋與數值**：
> 前端圖上的 `0.92` 類似於「總和生育率(TFR)」，但受限於我們沒有各單齡的生育率細項，我們採用的公式是 **「育齡青年生育率 (‰)」**。
> - **中文涵義**：「**每千名 18-35 歲青年女性中，當年度生下幾名嬰兒**」。
> - **呈現方式**：數值約落在 15‰ - 40‰ 之間，建議前端將單位明確標示為 ‰（千分比）。

---

### Section 2：機會疊圖與資源量化評估 (`OverlayInvestmentPanel.tsx`)

#### 2-1 疊圖比較分析 (Scatter Analysis)

> 探索「青年機會指數(YOI)」與「青年生育率」的關聯。由 Backend 計算 OLS 迴歸線。

| 軸 | 顯示說明 | 對應欄位 | 資料源 | 計算邏輯 |
|----|---------|---------|-------|---------|
| **X 軸** | 青年就業機會指數 | `opportunityIndex` | 衍生 | Homepage 算出的 YOI（1-100分） |
| **Y 軸** | 青年生育率 (‰) | `fertilityRate` | 衍生 | 上述算出的育齡青年生育率 (‰) |
| **每個點** | 行政區 | `district_name` | — | 29 個行政區，各一點 |
| **回歸線** | OLS 趨勢線 | `slope`, `intercept` | 衍生 | `y = intercept + slope × x` |

#### 2-2 青年成家環境友善指數 (Family-Friendly Index, FaFI)

> 原前端名稱待定，現正名為「青年成家環境友善指數」。
> 將三項關鍵指標（托育、居住、薪資）進行**等權重 (1/3)** 合成，輸出 1-100 的綜合評分。

| UI 顯示項目 | 對應欄位 | 說明 | 顏色邏輯（依分位數） |
|------------|---------|------|----------------|
| 綜合評分 | `fafi_score` | `(托育覆蓋得分 + 居住友善得分 + 薪資得分) / 3` | 綠色（> Q3），黃色（Q1 - Q3），紅色（< Q1） |

---

## 二、核心指標詳細計算邏輯

### 2.1 托育資源覆蓋率 (`daycare_coverage`)

採用與 Homepage「服務涵蓋率」相同的 **圓形 buffer ＋ 面積比例分攤法**。
- **半徑設定 (r)**：改為 **1.0 km**。原因：考量托育接送通常伴隨嬰幼兒，屬「步行生活圈」，2.5km 太遠。此數值在 Backend 可配置為變數以便未來微調。
- **目標人口分母**：採用 **18-35 歲女性人口 (`youth_18_35_female`)**（選項 B）。原因：最貼近生育與主要照顧者的潛在族群，且資料庫（A2）已有現成欄位，對資料源最友善，無須重新抓取 0-6 歲幼童資料。

**計算步驟**：
1. 以各公私立托育中心座標為圓心，畫半徑 1km 的聯集圓 `B`。
2. 計算各里 `v` 與 `B` 的面積交集比例：`f_v = area(polygon_v ∩ B) / area(polygon_v)`。
3. 該區覆蓋人口 = `Σ_v [ f_v × youth_18_35_female(v) ]`
4. 該區托育覆蓋率 = `該區覆蓋人口 ÷ 該區青年女性總人口`

### 2.2 青年成家環境友善指數 (FaFI)

```text
FaFI_score = ( norm(托育資源覆蓋率) + score_housing(即居住友善度) + norm(各地區平均薪資) ) / 3
```
* `norm()` 函式與 Homepage 相同，為 Min-Max 標準化並截斷 P5/P95，將數值投射到 0-100。
* `score_housing` 已經是 0-100 且方向為正向（越高越友善），故直接放入。
* 「各地區平均薪資」採用與 Employment 頁面相同的 `estimated_wage`（房價代理推算值）。

> 💡 **為何這三項算出來保證介於 0-100 之間？**
> 因為上述三個輸入變數各自的範圍都被嚴格限制在 `[0, 100]`，我們將這三者相加後「除以 3」求算術平均。根據數學原理，即使出現極端值（三個都拿 0 分，或三個都拿 100 分），平均的結果仍會完美鎖定在 `0-100` 的區間內，完全不會溢出。

---

## 三、Backend API 資料計算 Pseudocode

```python
import numpy as np

def generate_fertility_data(snapshot_date, year):
    # ── 1. 取得前置計算資料 ────────────────────────────────
    # 從 Homepage / Employment 取得 YOI 與代理薪資
    # yoi_data = generate_homepage_data(year)
    # yoi_by_district = yoi_data["yoi_dict"]
    # score_housing   = yoi_data["score_housing"]
    # estimated_wage  = yoi_data["estimated_wage"]

    # 取得生育與人口資料
    births = db.get("births", year)       # E1
    pop = db.get("population", year)      # A1, A2
    daycare_centers = db.get("daycares")  # 托育中心點位

    # ── 2. 托育資源覆蓋率 (Daycare Coverage) ───────────────
    # r = 1.0 km
    daycare_coverage_by_district = calculate_areal_coverage(
        points=daycare_centers, 
        radius_km=1.0, 
        target_pop_field="youth_18_35_female"
    )

    # ── 3. 計算 29 區各項基礎指標 ──────────────────────────
    fertility_rates = {}
    total_births = {}
    youth_ratios = {}
    
    city_births_total = 0
    city_female_total = 0
    city_youth_total = 0
    city_pop_total = 0

    for d in ALL_29_DISTRICTS:
        # 人口
        d_female = pop[d].youth_18_35_female
        d_youth  = pop[d].youth_18_35_total
        d_pop    = pop[d].people_total
        
        # 生育數
        d_births = sum(b.value for b in births if b.district_id == d)
        
        total_births[d] = d_births
        fertility_rates[d] = (d_births / d_female * 1000) if d_female else 0
        youth_ratios[d] = (d_youth / d_pop * 100) if d_pop else 0
        
        # 累加至全市
        city_births_total += d_births
        city_female_total += d_female
        city_youth_total += d_youth
        city_pop_total += d_pop

    city_fertility_rate = (city_births_total / city_female_total * 1000)
    city_youth_ratio = (city_youth_total / city_pop_total * 100)
    city_daycare_coverage = calculate_citywide_coverage(daycare_centers, 1.0, "youth_18_35_female")

    # ── 4. 計算青年成家環境友善指數 (FaFI) ───────────────────
    norm_daycare = minmax_clip_to_100(list(daycare_coverage_by_district.values()))
    norm_wage = minmax_clip_to_100(list(estimated_wage.values()))

    fafi_scores = {}
    for i, d in enumerate(ALL_29_DISTRICTS):
        fafi = (norm_daycare[i] + score_housing[d] + norm_wage[i]) / 3.0
        fafi_scores[d] = fafi

    # 計算 Q1, Q3 用於 FaFI 分級
    fafi_list = list(fafi_scores.values())
    q1_fafi = np.percentile(fafi_list, 25)
    q3_fafi = np.percentile(fafi_list, 75)
    
    # 計算生育率的 Q1, Q3 用於地圖深淺 (前端依此 mapping 顏色)
    fertility_list = list(fertility_rates.values())
    q1_fert = np.percentile(fertility_list, 25)
    q3_fert = np.percentile(fertility_list, 75)

    # ── 5. 計算 Scatter OLS 迴歸 ────────────────────────────
    # X: YOI, Y: 生育率
    scatter_points = []
    for d in ALL_29_DISTRICTS:
        scatter_points.append({
            "district_name": district_names[d],
            "x": round(yoi_by_district[d], 1),
            "y": round(fertility_rates[d], 2)
        })
    
    regression = calc_ols_regression(
        [p["x"] for p in scatter_points], 
        [p["y"] for p in scatter_points]
    )

    # ── 6. 組合回傳資料 ──────────────────────────────────────
    districts_result = []
    for d in ALL_29_DISTRICTS:
        districts_result.append({
            "id": d,
            "name": district_names[d],
            "fertilityRate": round(fertility_rates[d], 2),
            "fertilityLevel": "high" if fertility_rates[d] >= q3_fert else ("low" if fertility_rates[d] <= q1_fert else "medium"),
            "totalBirths": total_births[d],
            "youthRatio": round(youth_ratios[d], 2),
            "daycareCoverage": round(daycare_coverage_by_district[d] * 100, 1),
            "fafiScore": round(fafi_scores[d], 1),
            "fafiLevel": "high" if fafi_scores[d] >= q3_fafi else ("low" if fafi_scores[d] <= q1_fafi else "medium")
        })

    return {
        "citySummary": {
            "totalBirths": city_births_total,
            "fertilityRate": round(city_fertility_rate, 2),
            "youthRatio": round(city_youth_ratio, 2),
            "daycareCoverage": round(city_daycare_coverage * 100, 1)
        },
        "districts": districts_result,
        "scatter": {
            "title": "生育率 vs. 青年就業機會指數",
            "x_label": "青年就業機會指數",
            "y_label": "青年生育率 (‰)",
            "points": scatter_points,
            "regression": regression
        }
    }
```

---

## 五、資料缺口與注意事項

| 項目 | 說明 | 影響 |
|------|------|------|
| 🟢 資料定義對齊 | 前端顯示的 20-39 歲已改為 18-35 歲，完美貼合現有 `births_mother_age_18_35` 欄位。 | 系統一致性提升 |
| 🔴 托育據點資料 | 須確保資料工程師爬取的公私托清單附有「經緯度」或「完整地址」（供 geocoding），方可執行 1.0 km 緩衝區計算。 | 托育覆蓋率、FaFI |
| ⚠️ 前端圖例修改 | 請提醒前端將雷達圖/長條圖旁的綠色/橘色/紅色判定邏輯，從固定的(>70, 50-70, <50)改為動態吃 Backend 傳送的 `fafiLevel`（基於分位數計算）。 | 前端顯示準確度 |
| ⚠️ OLS 關係解讀 | 如果 Scatter 算出 YOI 和 生育率呈現「負相關」（機會越多生育率越低，這在都會區很常見），請確保介面呈現中立，交由使用者與 AI 判讀。 | 業務洞察 |
