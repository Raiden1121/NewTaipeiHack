# 青年就業（EmploymentPage）參數分析與資料源對應 

> 本文件依據最新的前端 React 元件架構（`features/employment`），嚴格對齊 Notion MD 公式定義，並完整對應 `data_description.md` 中實際可用的 18 個資料集。
> 所有計算皆由 Backend 完成後才拋給 Frontend 顯示。
> YOI 核心公式與五面向子指數**直接沿用 `homepage_analysis.md` v9** 的定義，本文件僅列重點摘要與前端呈現差異。

目前 data pipeline 已依本文件產出 `data/analytics/employment/all.json` 與
`data/quality/analytics_employment.json`；Backend／Frontend 只需讀取產物，
不在 request time 重新計算。

---

## 一、前端元件與參數對應表

青年就業頁分為 **2 大 Section**，對應 3 個主要 Component。

> **資料源編號說明**：A = 全站底層、C = 青年就業五面向、對應 Notion 編號

### Section 1：新北市機會分布地圖 + 右側區域詳細分析
(`DistributionMap.tsx` + `DistrictDetailPanel.tsx`)

#### 1-1 分布地圖（左側）

| UI 顯示項目 | 對應欄位 | 資料源 | 計算邏輯 |
|------------|---------|-------|---------|
| 地圖顏色（低機會→高機會） | `opportunityIndex` | **A1, C1.1–C2.3, C4.1, C4.2, C5.1–C5.3** | YOI 公式（詳見第二節），輸出 0–100 |

> 地圖顏色分級與 Homepage 完全相同。

#### 1-2 區域詳細分析 — 雷達圖（右側）

> ⚠️ **前端改動備註**：右側面板新增**雷達圖**，顯示選中行政區的五面向子指數評分。
> - 雷達圖共 4 圈，每圈代表 25 分，滿分 100（最外圈）
> - 前端目前尚未配置五個頂點對應到哪五個面向，**待前端修改後對接**
> - 建議頂點順序（順時針）：工作機會 → 薪資水準 → 青年活力與發展 → 居住友善度 → 交通可及

| UI 顯示項目 | 對應欄位 | 資料源 | 計算邏輯 |
|------------|---------|-------|---------|
| 綜合分數 | `opportunityIndex` | 衍生（同地圖） | YOI 加權合成分數，範圍 0–100 |
| 工作機會 | `score_job` | **C1.1** `job_vacancies` | S_job 子指數，0–100（詳見第二節） |
| 薪資水準 | `score_salary` | **C2.2** `job_vacancy_salaries` + **C1.1** `job_vacancies` | S_salary 子指數，0–100 |
| 青年活力與發展 | `score_talent` | **A1** `population` + **C3.1** `college_majors` | S_talent 子指數，0–100 |
| 居住友善度 | `score_housing` | **C4.1** `rentals` + **C4.2** `house_prices` | S_housing 子指數，0–100 |
| 交通可及 | `score_transport` | **C5.1** `bus_stops` + **C5.2** `railway_stops` + **C5.3** `bike_stops` | S_transport 子指數，0–100 |

> ⚠️ **「居住友善度」命名備注**：
> 原 Homepage 定義中此面向稱為「居住負擔」，為了讓雷達圖分數與直覺一致（分數高 = 好），**本頁統一改名為「居住友善度」(`score_housing`)**。
> 計算公式**不變**，仍使用 `norm_inv`（反向標準化）——居住成本越低的區，`score_housing` 越高，代表居住環境越「友善」。
> Backend 傳給 Frontend 的欄位語意已是「越高越好」，**前端無需再次反轉**。

---

### Section 2：跨主題比對分析 (`ScatterAnalysisPanel.tsx`)

> ⚠️ **前端改動備註**：
> - 原設計有「都會區」/「非都會區」顏色區分，**已移除**，改為所有 29 個行政區以統一色系呈現
> - 每張散點圖加入一條 **OLS 回歸直線（虛線）**
> - 回歸直線的截距與斜率由 Backend 計算後傳給 Frontend（`regression_slope`、`regression_intercept`），Frontend 根據公式 `y = intercept + slope × x` 繪製

#### 2-1 Scatter Plot 1：起薪與知識型職缺密度相關性（各行政區）

> 原前端標題「起薪與教育水準相關性」X 軸改為「知識型職缺比例」取代「高等教育普及率」。
> 原因：區級教育普及率無可靠資料（`college_majors` 為學校所在地，非居住地，29 區高度失衡）。
> 詳細決策記錄見第三節。

| 軸 | 顯示說明 | 對應欄位 | 資料源 | 計算邏輯 |
|----|---------|---------|-------|---------|
| **X 軸** | 知識型職缺比例（%） | `knowledge_job_ratio` | **C1.1** `job_vacancies` | 各區「要求大專以上學歷的職缺數」÷ 各區總職缺數 × 100%（詳見第三節） |
| **Y 軸** | 估算起薪（萬元／年） | `estimated_wage` | **C2.1** `wages` + **C4.2** `house_prices` | 仍為散點圖的輔助房價代理欄位，不再參與 YOI 的 S_salary |
| **每個點** | 行政區名稱 | `district_name` | — | 共 29 個點 |
| **回歸線** | OLS 直線 | `regression_slope`, `regression_intercept` | 衍生 | `y = regression_intercept + regression_slope × x` |

#### 2-2 Scatter Plot 2：房價與平均薪資關聯（各行政區）

| 軸 | 顯示說明 | 對應欄位 | 資料源 | 計算邏輯 |
|----|---------|---------|-------|---------|
| **X 軸** | 青年平均月薪（萬元） | `estimated_monthly_wage` | **C2.1** `wages` + **C4.2** `house_prices` | `estimated_wage(d) ÷ 12`（年薪換算月薪） |
| **Y 軸** | 每坪平均房價（萬元／坪） | `house_price_median_wan` | **C4.2** `house_prices` | 各區「住宅用」`price_per_ping` 中位數 ÷ 10,000（元換算萬元）。平溪例外：使用所有類型。 |
| **每個點** | 行政區名稱 | `district_name` | — | 共 29 個點（平溪因缺住宅用資料，以特例方式處理，前端建議加 `*` 標記） |
| **回歸線** | OLS 直線 | `regression_slope`, `regression_intercept` | 衍生 | `y = regression_intercept + regression_slope × x` |

---

## 二、核心指數公式（引用 homepage_analysis.md v9）

> 下列公式與 `homepage_analysis.md` 第二節完全相同。**後端實作以 homepage_analysis.md 為準文件**，本節僅供對照摘要。

### YOI 加權合成

```text
YOI_raw = 0.25·S_job + 0.25·S_salary + 0.15·S_talent + 0.20·S_housing + 0.15·S_transport
YOI     = norm(YOI_raw)
```

### 各面向對應前端欄位

| homepage_analysis.md 代號 | 本頁前端欄位名稱 | 前端標籤 | 說明 |
|---------------------------|----------------|---------|------|
| S_job | `score_job` | 工作機會 | 職缺密度（每平方公里）、Shannon 多樣性 |
| S_salary | `score_salary` | 薪資水準 | 職缺刊登薪資中位數、高薪職缺比；不含房價代理薪資 |
| S_talent | `score_talent` | 青年活力與發展 | 青年人口佔比、青年人口 YoY、大專學生密度（ROC 114） |
| S_housing | `score_housing` | **居住友善度** | norm_inv（租金、房價、租金薪資比）；分數越高代表居住越友善 |
| S_transport | `score_transport` | 交通可及 | 公車/軌道/自行車密度 |

### 標準化函數（純 Min-Max，不截斷 P5/P95）

```text
norm(x)     = (x - min) / (max - min) × 100
norm_inv(x) = 100 - norm(x)    ← 居住友善度（S_housing）使用此公式
```

---

## 三、散點圖詳細計算邏輯

### 3.1 知識型職缺比例（Scatter 1 X 軸）

```text
knowledge_job_ratio(d) =
  Σ position_count [ v ∈ job_vacancies, v.district_id == d, 學歷要求 ∈ 大專以上 ]
  ÷
  Σ position_count [ v ∈ job_vacancies, v.district_id == d ]
  × 100%
```

| 元素 | 資料源 | 說明 |
|------|-------|------|
| 學歷要求欄位 | **C1.1** `job_vacancies` raw 的 `EDGRDESC` 欄位 | 包含「大學」「專科」「碩士」「博士」「學士」等關鍵字視為大專以上 |
| 分子 | `position_count` 加總（篩選大專以上） | 只用 `geo_level=district` 的筆數 |
| 分母 | `position_count` 加總（全部） | 與 S_job 中計算總職缺數相同 |

> ⚠️ **決策備注（X 軸選項評估）**：
> 原設計希望使用「高等教育普及率」，評估三個備選後採用選項 B：
> - **A. E1 生母教育程度**：區級但僅限有生育的女性，樣本偏差。保留給生育頁使用。
> - **B. 職缺學歷要求比例（✅ 已採用）**：29 區皆有資料；反映「各區工作的知識密度」，與起薪邏輯正相關。
> - **C. college_majors**：學校所在地非居住地，29 區嚴重失衡，不建議。

### 3.2 OLS 回歸直線計算

兩張散點圖均在 Backend 計算 **OLS（普通最小平方法）回歸係數**：

pipeline 使用 `analytics.homepage_math.calculate_ols_regression` 的純 Python
實作，不新增 NumPy 依賴。它會先排除 `null`、NaN、Infinity；0 是有效值。
輸出 `method=ols`、`sample_size`、`slope`、`intercept`、`r_squared`。有效點
不足兩筆或 X 沒有變異時，對應統計欄位保留 `null`，不把退化資料硬補成 0。

Frontend 收到後根據 `y = intercept + slope × x` 繪製虛線回歸線。

---

## 四、Backend API 資料計算 Pseudocode

```python
def generate_employment_data(snapshot_date, year):
    """
    產生青年就業頁所需的全部資料。
    大部分 YOI 計算與 generate_homepage_data() 共用，此函數直接引用結果後再擴充。
    snapshot_date : 職缺/交通快照日期（目前只有 2026-09-03）
    year          : 主要統計年份
    """

    # ── 沿用 Homepage 已計算的 YOI 五面向分數 ────────────────
    # homepage_data = generate_homepage_data(snapshot_date, year)
    # 每個 district 已含：
    #   opportunityIndex, retentionRiskLevel,
    #   score_job, score_salary, score_talent, score_housing, score_transport
    #   estimated_wages (dict: district_id → 年薪 元)

    # ── 拉取職缺資料（散點圖用） ─────────────────────────────
    vacancies = db.get("job_vacancies")   # C1.1

    # ── 計算各區 knowledge_job_ratio ─────────────────────────
    COLLEGE_KEYWORDS = ["大學", "專科", "碩士", "博士", "學士"]

    def is_college_required(vacancy):
        edgr = vacancy.raw_record.get(
            "EDGRDESC（最低學歷要求）", vacancy.raw_record.get("EDGRDESC", "")
        )
        return any(kw in edgr for kw in COLLEGE_KEYWORDS)

    knowledge_ratio = {}
    for d in ALL_29_DISTRICTS:
        d_vac      = [v for v in vacancies if v.district_id == d]
        total      = sum(v.position_count for v in d_vac)
        college    = sum(v.position_count for v in d_vac if is_college_required(v))
        knowledge_ratio[d] = (college / total * 100) if total > 0 else None

    # ── 計算各區住宅用房價中位數（Scatter 2 Y 軸）────────────
    houses = db.get("house_prices")   # C4.2
    house_median_wan = {}
    for d in ALL_29_DISTRICTS:
        if d == "平溪區":
            prices = [h.price_per_ping for h in houses
                      if h.district_id == d and h.price_per_ping]
        else:
            prices = [h.price_per_ping for h in houses
                      if h.district_id == d and h.price_per_ping
                      and h.transaction_type == "住宅用"]
        house_median_wan[d] = median(prices) / 10000 if prices else None

    # ── Scatter 1 ─────────────────────────────────────────────
    s1_points = [
        {
            "district_name": district_names[d],
            "x": round(knowledge_ratio[d], 2),           # 知識型職缺比例 (%)
            "y": round(estimated_wages[d], 2),            # 估算年薪 (萬元)
        }
        for d in ALL_29_DISTRICTS
    ]
    valid_s1  = [p for p in s1_points if p["x"] is not None and p["y"] is not None]
    regression1 = calculate_ols_regression([(p["x"], p["y"]) for p in valid_s1])

    # ── Scatter 2 ─────────────────────────────────────────────
    s2_points = [
        {
            "district_name": district_names[d],
            "x": round(estimated_wages[d] / 12, 2),           # 月薪 (萬元)
            "y": house_median_wan[d],                          # 房價 (萬元/坪)
        }
        for d in ALL_29_DISTRICTS
    ]
    valid_s2  = [p for p in s2_points if p["x"] is not None and p["y"] is not None]
    regression2 = calculate_ols_regression([(p["x"], p["y"]) for p in valid_s2])

    # ── 組合各區輸出 ──────────────────────────────────────────
    districts_result = []
    for d in ALL_29_DISTRICTS:
        districts_result.append({
            "id":                     d,
            "name":                   district_names[d],
            "opportunityIndex":       round(yoi_by_district[d], 1),
            "retentionRiskLevel":     risk_level[d],
            "score_job":              round(s_job[d], 1),
            "score_salary":           round(s_salary[d], 1),
            "score_talent":           round(s_talent[d], 1),
            "score_housing":          round(s_housing[d], 1),  # 居住友善度，越高越好
            "score_transport":        round(s_transport[d], 1),
            "knowledge_job_ratio":    round(knowledge_ratio[d], 2),
            "estimated_wage":         round(estimated_wages[d], 2),                # 年薪 萬元
            "estimated_monthly_wage": round(estimated_wages[d] / 12, 2),           # 月薪 萬元
            "house_price_median_wan": house_median_wan[d],
        })

    return {
        "districts": districts_result,
        "scatter": {
            "plot1": {
                "title":       "起薪與知識型職缺密度相關性（各行政區）",
                "x_label":     "知識型職缺比例（%）",
                "y_label":     "估算起薪（萬元／年）",
                "points":      s1_points,
                "regression":  regression1,  # {slope, intercept, r_squared}
                "note":        "X 軸為職缺要求大專以上學歷的比例（非居住人口教育程度）"
            },
            "plot2": {
                "title":       "房價與平均薪資關聯（各行政區）",
                "x_label":     "青年平均月薪（萬元）",
                "y_label":     "每坪平均房價（萬元）",
                "points":      s2_points,
                "regression":  regression2,
                "note":        "薪資為以房價代理估算之值；房價僅含住宅用（平溪例外使用全類型）"
            }
        }
    }
```

---

## 五、資料缺口與注意事項

| 項目 | 說明 | 影響欄位 |
|------|------|---------|
| ⚠️ 職缺快照唯一性 | `job_vacancies` 目前使用最新 `11509` 快照，`knowledge_job_ratio` 及 `score_job` 均為單點估計 | Scatter 1、S_job |
| ✅ 職缺學歷欄位 | transform 保留 raw `EDGRDESC（最低學歷要求）`；analytics 以大學／專科／學士／碩士／博士關鍵字計算比例 | `knowledge_job_ratio` |
| ⚠️ 平溪房價缺住宅用資料 | 平溪無住宅用記，使用所有類型 fallback；前端建議加 `*` 標記 | Scatter 2 Y 軸 |
| ⚠️ 薪資快照與覆蓋率 | 薪資採完整上下界的職缺區間中點；小樣本區與單邊薪資會使中位數及高薪比例不穩定，詳細排除數寫入 quality artifact | `score_salary` |
| ⚠️ 大專學生密度 proxy | `college_majors` 依學校所在地映射行政區，淡水／新莊等學區可能偏高；青年人口欄位補足區級變異，但不代表學生戶籍或人才品質 | `score_talent` 雷達圖 |
