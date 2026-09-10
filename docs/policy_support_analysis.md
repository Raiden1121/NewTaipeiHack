# 施政協助（PolicySupportPage）參數分析與資料源對應

> 本文件依據最新的前端 React 元件架構（`features/policy`），定義「政策成效追蹤」區塊的核心指標計算邏輯，並對齊現有資料庫（`wages`, `population`）。
> ⚠️ 下半部的「AI 政策決策輔助 (Decision Support)」為獨立服務模組，本文件不作資料流定義。

---

## 一、前端元件與參數對應表

### Section 1：政策成效追蹤 (Policy Outcomes)

#### 1-1 薪資成長率

| UI 顯示項目 | 對應欄位 | 資料源 | 計算邏輯 |
|------------|---------|-------|---------|
| 薪資成長率 (大字 YoY) | `wage_growth_rate` | **D2** `wages` | `(最新年份薪資 - 前一年份薪資) / 前一年份薪資` |
| 薪資歷年趨勢圖 | `wage_trend` | **D2** `wages` | 取得 2019~2024 歷年「25-29歲」薪資數據組成 Array |

> ⚠️ **開發與資料注意事項**：
> 1. 依據 `data_description.md` 盤點，我們的 `wages` 資料集提供 **2019～2024 年** 的歷史資料。
> 2. 計算歷年成長率時，**第一年（基期 2019）的成長率必為 Null 或 0**。Backend 傳送資料時應將第一年的 YoY 設為 Null，請提醒前端具備防呆機制，避免畫線條或顯示綠色箭頭時報錯。
> 3. 薪資採用全「新北市整體」的資料，不細分至 29 區。年齡段建議採用 25-29 歲區間作為主要指標（或 25-34 歲區間加權）。

#### 1-2 青年人口世代變化率

| UI 顯示項目 | 對應欄位 | 資料源 | 計算邏輯 |
|------------|---------|-------|---------|
| 人口變化率 (大字 YoY) | `pop_growth_rate` | **A1** `population` | `(最新年份 18-35 歲總人口 - 前一年份 18-35 歲總人口) / 前一年份總人口` |
| 人口歷年趨勢圖 | `pop_trend` | **A1** `population` | 取得近五年（如 2022~2026）的 18-35 歲總人口數組成 Array |

> ⚠️ **開發與資料注意事項**：
> 1. **年齡口徑修正**：前端截圖顯示「20-35 歲」為設計錯誤，已正名並統一為 **18-35 歲**。
> 2. 依據 `data_description.md` 盤點，`population` 提供 **2018-01～2026-07** 的按月資料，且直接包含 `youth_18_35_total` 欄位（`youth_eligibility=eligible`）。Backend 可直接取每年同月份（例如每年 7 月）或年度平均，來構成近 5 年的年度趨勢折線圖資料。

---

## 二、Backend API 資料計算 Pseudocode

```python
def generate_policy_support_data():
    # ── 1. 取得歷史資料 ────────────────────────────────
    # 從資料庫取得新北市整體薪資 (D2) 與人口 (A1) 歷史紀錄
    # 根據 data_description.md，wages 有 2019~2024，直接可用
    wages_history = db.get_history("wages")  
    
    # population 有 2018~2026，我們取近 5 年 (2022~2026) 每年 7 月做代表
    pop_history = db.get_history("population", years=[2022, 2023, 2024, 2025, 2026], month=7)

    # ── 2. 計算薪資趨勢與 YoY ──────────────────────────
    wage_trend = []
    for i, w in enumerate(wages_history): # 假設 wages_history 依年份遞增排序
        year = w.year
        # 取 25-29 歲組的薪資作為代表
        salary = w.salary_25_29  
        
        yoy = None
        if i > 0:
            prev_salary = wages_history[i-1].salary_25_29
            yoy = ((salary - prev_salary) / prev_salary) * 100
            
        wage_trend.append({
            "year": year,
            "wage": salary,
            "yoy": round(yoy, 2) if yoy is not None else None
        })

    # ── 3. 計算人口趨勢與 YoY ──────────────────────────
    pop_trend = []
    for i, p in enumerate(pop_history): # 假設依年份遞增排序
        year = p.year
        youth_total = p.youth_18_35_total # 直接取用 derived_18_35
        
        yoy = None
        if i > 0:
            prev_total = pop_history[i-1].youth_18_35_total
            yoy = ((youth_total - prev_total) / prev_total) * 100
            
        pop_trend.append({
            "year": year,
            "population": youth_total,
            "yoy": round(yoy, 2) if yoy is not None else None
        })

    # ── 4. 組合回傳結果 ─────────────────────────────────
    return {
        "policyOutcomes": {
            "wageTrend": wage_trend,
            "populationTrend": pop_trend,
            # 前端大字直接取陣列最後一筆資料即可
            "currentWageGrowth": wage_trend[-1]["yoy"], 
            "currentPopGrowth": pop_trend[-1]["yoy"]
        }
    }
```

---

## 三、AI 政策決策輔助 (Decision Support)

> ⚠️ **分工說明**：本區塊（包含對話介面、RAG 檢索、政策建議生成）由 **陳紀睿負責**。
> 本文件僅定義上半部的「政策成效追蹤」資料流，AI 助手的 Prompt Engineering 與資料串接邏輯另見專屬文件。
