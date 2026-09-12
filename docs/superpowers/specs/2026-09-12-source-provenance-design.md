# Source Provenance and DynamoDB Display Design

**Date:** 2026-09-12  
**Status:** Implemented locally on the `datapipeline` branch; AWS/Backend handoff pending

## Goal

讓既有與未來的資料都能在 published snapshot 與 DynamoDB 顯示可追溯來源，同時保留目前已上傳的 S3 Raw 不變，不要求重新下載或重新上傳歷史 Raw。

## Current Evidence

- `data-pipeline/src/orchestration/contracts.py` 的 `CollectorSpec` 目前只有 dataset、collector 與 period strategy，沒有統一的 source contract。
- `CollectedPayload.metadata` 可以保存來源資訊，但回傳普通 list 的 collector 目前只會寫入 `dataset`、`period`、`fetched_at`、`records`。
- `build_common_metadata()` 已有 `source`，但 curated common contract 尚未有統一的 `source_url`。
- 部分 collector 已保留 `source_url` 或 `source_document_url`；部分既有 Raw 沒有來源欄位。
- Backend 目前仍是 mock API；預定由 published snapshot／DynamoDB adapter 讀取 pipeline 的發布結果，不在 request 時重新執行 ETL。

## Decisions

### 1. Source registry 是來源定義的唯一設定入口

新增 `data-pipeline/config/sources.json`，使用 pipeline 內部的 snake_case 欄位：

```json
{
  "schema_version": 1,
  "sources": {
    "moi_household_registration": {
      "name_zh": "內政部戶政司",
      "source_url": "https://example.gov.tw/dataset",
      "url_type": "dataset"
    }
  },
  "dataset_defaults": {
    "population": "moi_household_registration"
  }
}
```

`source_url` 是使用者可以查證的官方 landing page、dataset page 或 API page；不是 S3 內部路徑。對於動態 resource，registry 保存穩定的資料集頁面，Raw 仍可保留實際下載 URL。

第一版 registry 必須涵蓋目前 transform 產生的 source IDs：

`moi_household_registration`、`ntpc_youth_bureau_budget`、`ntpc_social_affairs_babysitting`、`moe_9620`、`moe_9621_9622`、`cec_election_candidate_roster`、`new_taipei_real_estate_open_data`、`join_gov_public_policy_platform`、`dgbas_table_6`、`taiwanjobs`、`ntpc_youth_bureau_startup_base`、`mol_talent_demand`、`mol_training_numbers`、`mol_vocational_courses`、`tdx`、`nlsc_village_boundaries`、`ntpc_youth_bureau_meeting_minutes`、`ntpc_youth_bureau_grant_detail`。

### 2. Raw 採向後相容，不回寫歷史檔案

新執行產生的 Raw envelope 統一包含：

```json
{
  "dataset": "population",
  "period": "11507",
  "fetched_at": "2026-09-12T02:00:00Z",
  "source": "moi_household_registration",
  "source_url": "https://example.gov.tw/dataset",
  "source_url_type": "dataset",
  "records": []
}
```

既有 Raw 只讀不改。轉換時以 registry 與 Raw envelope 補 provenance；若需要在 S3 重新發布，寫入新的 curated／published 版本，不覆蓋原始 Raw。

來源解析優先順序：

1. curated record 已有的 `source`；若與 Raw／collector source 不同，保留 record source 並寫入 `source_conflict`。
2. 既有 Raw 或 collector metadata 的 `source`。
3. `sources.json.dataset_defaults`。
4. 無法確認時保留 `null`，並寫入 quality warning，不猜測來源。

URL 解析優先使用 Raw／collector 的明確 `source_url`，其次使用 curated record 的 `source_url`，最後使用 registry 的 canonical `source_url`。

### 3. Internal、published、DynamoDB 使用不同命名但同一語意

- Raw／Curated：`source`、`source_url`、`source_url_type`。
- Published／API／DynamoDB：`source`、`sourceName`、`sourceUrl`、`sourceRefs`。
- `source` 是穩定分組 ID；`sourceName` 與 `sourceUrl` 由 registry 解析，不由 Frontend 硬編碼。

單一來源的 metric 可以填 `source`、`sourceName`、`sourceUrl`。多來源衍生指標不冒充單一官方來源，使用 `source: null`、`sourceUrl: null` 與 `sourceRefs: [...]`。

### 4. DynamoDB key 不因來源欄位改變

沿用現有 snapshot key：

```text
PK=SNAPSHOT#{snapshot_id}#RESOURCE#district_details
SK=DISTRICT#{district_id}
```

來源欄位是 item 內的非 key attributes；Backend 仍以 snapshot、resource 與 district key 查詢，不掃描整張表。

## Data Flow

```text
sources.json
       ↓
collector / legacy Raw resolver
       ↓
S3 Raw（新資料保存 source；舊資料不修改）
       ↓
Curated（補 source_url）
       ↓
Analytics published snapshot
  ├─ manifest.sources
  └─ public metric sourceName/sourceUrl/sourceRefs
       ↓
DynamoDB serving projection
       ↓
Backend API → Frontend
```

## Error Handling

- `sources.json` JSON 格式錯誤、缺少必填欄位或 URL 不是 `http://`／`https://`：在 pipeline 開始前失敗，不產生新的 published pointer。
- record 使用未知 source ID：保留原 ID，`sourceName`／`sourceUrl` 為 `null`，quality report 加入 `unknown_source_id`。
- legacy Raw 沒有來源且 registry 沒有 dataset mapping：不阻擋其他資料集，但該資料的 source 欄位為 `null` 並記錄 `source_unresolved`。

## Scope

本次包含 source registry、legacy Raw 相容解析、curated／published contract、DynamoDB projection contract 與測試。EventBridge Scheduler、Step Functions 的完整 Terraform 資源與全套 pipeline Lambda 部署不在本 feature 的程式修改範圍；它們只需要把同一份 `sources.json` 隨 pipeline artifact 部署，並啟動既有流程。

## Acceptance Criteria

1. 不修改既有 S3 Raw，即可從 legacy `population` Raw 產生含 `source`／`source_url` 的 curated 與 published output。
2. 新 collector 產生的 Raw envelope 一律有 nullable 的 source fields。
3. `sourceName` 與 `sourceUrl` 只由 registry／pipeline output 提供，Frontend 不維護來源對照表。
4. 單一來源 metric 在 DynamoDB projection 有 `source`、`sourceName`、`sourceUrl`。
5. 多來源衍生 metric 使用 `sourceRefs`，不產生誤導性的單一 `sourceUrl`。
6. 既有 DynamoDB partition/sort key 不變，Backend adapter 可用同一組 key 讀取。
7. 測試驗證 legacy Raw 的內容 hash 前後一致、未知 source 有 quality warning、published snapshot 不含 `raw_records`。
