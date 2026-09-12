# 青年關注議題文字雲 Data Pipeline 設計

## Goal

在既有 `data-pipeline` 中新增 join.gov.tw 提案與新北市青年局會議紀錄兩個來源，保存可重播的 raw/curated 資料，並在 analytics 計算每個 ROC 年度與議題的出現次數、訊號與 `weight: 1..5`。本設計不修改 Backend、Frontend，也不產生文字雲圖片。

## Scope

- 新增 `join_proposals` all-available collector。
- 新增 `youth_council_minutes` all-available collector，保存 PDF artifact、SHA-256 與逐頁文字。
- 新增兩個 source-specific transform，保留來源欄位與 `raw_record`。
- 新增固定的 22 個青年議題、同義詞、青年 proxy 關鍵字、會議段落 regex 與 escalated 關鍵字設定。
- 新增 `youth_topic_weight` analytics，計算 `join_mentions`、`minutes_mentions`、`resolved`、`escalated`、`raw_score` 與 `weight`。
- 接入現有 `run_pipeline.py`、`dataset_index.json`、refresh、replay、retention、quality/quarantine 流程。
- 提供 local analytics runner 與可驗證的 JSON 輸出。

## Non-goals

- 不修改 `frontend/src/features/politics/components/YouthTopicWordCloud.tsx`。
- 不修改 Backend API。
- 不在 Data Pipeline 或 Backend 產生 PNG/SVG 文字雲。
- 不將沒有年齡欄位的 join 或會議資料宣稱為真實 18–35 歲民意。
- 不將全國 join 資料拆分到新北市 29 區。
- 不把缺少來源資料的年度補成 0。
- 不加入 `word_cloud` 圖片產生套件；目前 Python repo 僅作中文處理與演算法參考。

## Existing boundaries

- `collectors/` 負責來源請求、來源格式驗證、逐筆 raw record 與 binary artifact。
- `transform/` 只讀已保存 raw，不呼叫 live API；負責型別、日期、期間、品質與 curated contract。
- `analytics/` 負責跨來源議題匹配、計數、正規化與權重。
- `run_pipeline.py` 負責 execution unit、raw/curated/quality/quarantine 與 authoritative dataset index。
- Backend 未來只讀 analytics output；Frontend 未來把 `weight` 映射到字型大小與排版。

## Source strategy

### `join_proposals`

優先使用 data.gov.tw「公共政策網路參與平臺－提點子」年度資料資源；collector 不假設資源必定是 CSV，應依實際 Content-Type/內容支援 JSON，並保留可替換的 fallback adapter。若官方開放資料缺少歷史年度或欄位不足，再使用 join 提案列表頁的動態發現與逐案 detail 抓取。

Collector 需保存完整來源 payload。`agency`、`category`、`status` 等欄位若來源沒有，保留 JSON `null`，不得猜測。

Raw row 最低欄位：

```json
{
  "proposal_id": null,
  "proposal_url": null,
  "title": "",
  "content": "",
  "interest_impact": null,
  "endorsement_count": null,
  "endorsement_threshold": null,
  "submitted_at": null,
  "published_at": null,
  "status": null,
  "agency": null,
  "category": null,
  "year_roc": "114",
  "source_payload": {}
}
```

### `youth_council_minutes`

從青年局青委會與會議紀錄入口頁動態發現文件。detail URL 不一定以 `.pdf` 結尾，collector 必須依 `%PDF-` magic bytes 或 Content-Type 判斷 PDF；若 detail page 是 HTML，才繼續尋找 PDF link。

Collector 使用既有 `CollectedPayload`/`SourceArtifact`，每份成功 PDF 保存：

- `meeting_id`
- `meeting_name`
- `meeting_date`
- `term`
- `year_roc`
- `detail_url`
- `pdf_url`
- `source_pdf_sha256`
- `page_texts`

`page_texts` 寫入 raw JSON，確保 raw replay 不需重新下載或重新讀取 PDF。

## Curated contracts

### `join_proposals`

- `geo_level`: `national`
- `district_id`, `district_name`: `null`
- `period_type`: `year`
- `period_start`, `period_end`: ROC 年轉 Gregorian 年度邊界
- `metric_id`, `value`, `unit`: `null`
- `age_scope`: `not_age_specific`
- `youth_eligibility`: `context_only`
- `youth_topic_proxy`: `true`/`false`
- `proxy_reasons`: 命中的機關或關鍵字
- `raw_record`: 完整來源 row

`youth_topic_proxy` 不是年齡證明。因目前 common contract 將 `not_age_specific` 對應到 `context_only`，不可將這類資料錯標為 `proxy_only`。

### `youth_council_minutes`

一份 PDF 可產生多筆「會議提案項目」curated records：

- `geo_level`: `organization`
- `district_id`, `district_name`: `null`
- `period_type`: `year`
- `period_start`, `period_end`: 會議日期所在 Gregorian 年度邊界
- `metric_id`, `value`, `unit`: `null`
- `age_scope`: `not_age_specific`
- `youth_eligibility`: `context_only`
- `meeting_id`, `meeting_name`, `meeting_date`, `term`
- `item_no`, `section_type`, `source_page_start`, `source_page_end`
- `source_text`
- `discussed`, `resolved`, `escalated`
- `parse_status`, `manual_review_required`
- `source_pdf_sha256`, `raw_record`

處理層級的優先順序為 `escalated > resolved > discussed`；但 curated 同時保存三個 boolean，避免遺失來源狀態。

若找不到決議段落，不能直接推論 `escalated=false`；需標記 `parse_status=partial` 與 `manual_review_required=true`。

## Configuration

### `config/youth_topic_rules.json`

包含：

- 目前前端的 22 個 canonical labels。
- 每個 label 的 aliases、排除詞與匹配欄位。
- 青年 proxy 機關清單與關鍵字。
- 會議 section header regex。
- escalated phrase 清單。
- jieba user dictionary 與 stop-word 檔案路徑。

同義詞在匹配前先做 NFKC、空白與標點正規化，並以長詞優先；同一筆 record 對同一 canonical topic 只計一次。

### `config/youth_topic_weights.json`

```json
{
  "version": "1",
  "w_join": 1.0,
  "w_minutes": 1.8,
  "w_resolved": 1.2,
  "w_escalated": 2.5,
  "normalization": "yearly_max"
}
```

## Analytics contract

對每個 `(topic_label, year_roc)` 計算：

```text
join_support_score = Σ (1 + log(1 + endorsement_count))
join_mentions = 命中該 topic 的不同提案數
minutes_mentions = 命中該 topic 的不同會議提案項目數
resolved = 該年度該 topic 是否出現在決議段落
escalated = 該年度該 topic 是否命中 escalated phrase
```

每個年度的 numeric signal 各自除以該年度最大值，最大值為 0 時 normalized value 為 0：

```text
raw_score =
    1.0 × normalized_join
  + 1.8 × normalized_minutes
  + 1.2 × resolved
  + 2.5 × escalated
```

量化規則：

```text
weight = clamp(round_half_up(1 + 4 × raw_score / max_raw_score), 1, 5)
```

若該年度所有 topic 的 `max_raw_score` 為 0，全部 `weight=1`。若 `minutes_mentions > 0`，`weight` 至少為 3；若 `escalated=true`，`weight=5`。

輸出的 `signal` 使用 `escalated > minutes > join > null` 優先順序。即使沒有訊號，也輸出設定檔中的 22 個 topic，避免 Frontend 每年收到不同欄位集合。

Output：

```text
data/analytics/youth_topic_weight/all.json
data/quality/analytics_youth_topic_weight.json
```

`all.json` 頂層包含 `metric_id`、`calculation_version`、`source_datasets`、`config_version` 與年度結果。

## Orchestration and retention

兩個來源都使用 `PeriodStrategy.ALL_AVAILABLE`，分別輸出：

```text
curated/join_proposals/all.json
curated/youth_council_minutes/all.json
```

raw/curated records 使用 `year_roc`，retention 必須能辨識該欄位，保留前五個完整年度與當年度。初期加入 monthly refresh；來源更新頻率與 pipeline 執行頻率分開記錄。

## Failure behavior

- data.gov resource unavailable：記錄來源錯誤，不以空資料覆蓋舊 curated。
- 單一 join detail 失敗：保留 failure metadata，其他 records 繼續處理。
- 單一 PDF 下載或抽文字失敗：保留 document failure；其他 PDF 繼續處理。
- PDF 無法辨識 section：curated 可保留 partial item，但需 `manual_review_required=true`。
- analytics 找不到必要 dataset：回傳明確錯誤，不產生不完整權重檔。
- 缺失數值使用 `null`；來源沒有的年度不補 0。

## Acceptance criteria

1. Fake join resource 可產生完整 raw 與 curated records，缺失欄位保留 `null`。
2. Fake meeting listing/detail/PDF 可產生 PDF artifact、SHA-256、逐頁文字與 item records。
3. 同義詞能合併為單一 canonical topic，單一來源 row 不重複計數。
4. join 與 minutes 都能以 `year_roc` 正確分年度。
5. minutes 能區分 discussed、resolved、escalated，版面異常會產生 manual review flag。
6. 兩個資料集只產生 `all.json`，並可透過 raw replay 重跑 transform。
7. analytics 對每個可用年度輸出 22 個 topic，`weight` 永遠在 1–5。
8. 有 minutes 訊號的 topic 至少為 3，escalated topic 強制為 5。
9. focused tests、完整 unittest、compileall 與 `git diff --check` 通過。

