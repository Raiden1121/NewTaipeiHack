# 新北市青年局預算 PDF 資料源 Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 將青年局官方年度預算 PDF 的「計畫及預算統計表」接入既有 data pipeline，保留原始 PDF 與版本資訊，並產生可供後續 analytics 使用的 curated JSON。

**Architecture:** 新增 youth_budget collector，從官方列表頁發現所有年度文件，下載並以 pypdf 抽取目標表格；collector 以 typed payload 回傳 JSON records 與 PDF artifacts，pipeline 統一寫入 raw。新增 budget transform 將機關層級資料轉成 common metadata，使用 ALL_AVAILABLE 讓同年度預算案與法定預算共存。

**Tech Stack:** Python standard library urllib、html.parser、hashlib、unittest、pypdf、既有 local JSON pipeline。

**Spec:** docs/superpowers/specs/2026-09-09-youth-budget-source-design.md

## Global Constraints

- 只解析 計畫及預算統計表，不擴大到 PDF 其他表格。
- youth_budgets 使用 PeriodStrategy.ALL_AVAILABLE，輸出 key 為 all。
- proposed_budget 與 legal_budget 必須以 document_id、年度與版本欄位共存，不得互相覆蓋。
- 預算資料使用 geo_level=organization，district_id 與 district_name 必須是 JSON null。
- 預算資料使用 age_scope=not_age_specific 與 youth_eligibility=context_only。
- Collector 與 transform 不計算年度增減、跨資料集指標或重新計算來源比率。
- 原始 PDF 以 SHA-256 命名保存，raw JSON 保存來源與 artifact metadata。
- 測試使用 fake HTTP/PDF seams，不呼叫 live source；live 驗證只作為最後的手動 smoke check。
- 既有資料、curated、quality、quarantine 檔案不自動刪除。

## File Structure

### New files

- data-pipeline/src/collectors/contracts.py: SourceArtifact 與 CollectedPayload typed contracts。
- data-pipeline/src/collectors/youth_budget.py: 官方列表/詳情/PDF discovery、下載、hash、表格定位與 raw row extraction。
- data-pipeline/src/transform/budget.py: raw budget rows 到 curated organization-level records 的轉換與 quarantine。
- data-pipeline/tests/test_youth_budget.py: listing/detail/PDF parsing、版本辨識、artifact metadata、錯誤分支測試。
- data-pipeline/tests/test_transform_budget.py: budget transform、organization grain、數值型別與 quarantine 測試。

### Modified files

- data-pipeline/requirements.txt: 加入 pypdf。
- data-pipeline/src/transform/common.py: 將 organization 加入合法 GEO_LEVELS。
- data-pipeline/src/transform/pipeline.py: 註冊 youth_budgets canonical dataset 與 transform dispatch。
- data-pipeline/src/transform/io.py: 新增安全、原子性的 binary source-artifact writer。
- data-pipeline/src/run_pipeline.py: 支援 CollectedPayload、寫入 artifact metadata、註冊 ALL_AVAILABLE collector。
- data-pipeline/tests/test_transform_pipeline.py: raw replay、artifact payload 與 pipeline output integration tests。
- data-pipeline/tests/test_orchestration_schedule.py: 驗證 default registry 的 youth_budgets strategy。
- data-pipeline/src/collectors/data.md: collector interface、來源欄位、測試樣本與執行方式。
- data-pipeline/src/transform/transform.md: youth_budgets raw/curated contract、organization grain 與 null rules。
- data-pipeline/data-pipeline.md: 新資料集的 pipeline output、replay、resume 與 artifact 說明。
- data-pipeline/data/data_description.md: 以實際產出的 curated sample 補上 dataset keys、年度/版本、單位與限制。

## Task 1: 建立 source artifact contract 與保存層

**Files:**

- Create: data-pipeline/src/collectors/contracts.py
- Modify: data-pipeline/src/transform/io.py
- Modify: data-pipeline/src/run_pipeline.py
- Test: data-pipeline/tests/test_transform_pipeline.py

**Interfaces:**

- SourceArtifact(filename: str, content: bytes, media_type: str, sha256: str)
- CollectedPayload(records: list[dict[str, Any]], metadata: dict[str, Any], artifacts: tuple[SourceArtifact, ...])
- write_source_artifacts(artifacts: Sequence[SourceArtifact], *, dataset: str, output_dir: str | Path) -> list[dict[str, Any]]
- _raw_and_transform_payload(dataset: str, collected: Any, *, period: str, fetched_at: str) -> tuple[dict[str, Any], Any, tuple[SourceArtifact, ...]]

- [ ] Step 1: Write failing contract and writer tests.

  建立一個 SourceArtifact，寫入暫存 output directory，驗證 binary 內容、相對路徑、media type、SHA-256 與 byte size。再加入 pipeline test，確認 CollectedPayload 的 records/metadata 可寫入 JSON，bytes 會被分離保存。

  測試資料使用 b"%PDF-test"，預期路徑為 raw/youth_budgets/artifacts/115_legal_budget_abc.pdf。

- [ ] Step 2: Run focused tests and verify RED.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_transform_pipeline -v

  Expected: new contract 或 writer 尚不存在，測試失敗。

- [ ] Step 3: Implement the typed payload and safe artifact writer.

  SourceArtifact 與 CollectedPayload 使用 immutable dataclass。write_source_artifacts 必須：

  1. 拒絕空檔名、包含 /、反斜線、.. 的 path traversal。
  2. 寫入 raw/{dataset}/artifacts/{filename}。
  3. 使用與既有 JSON writer 相同的同目錄 temporary-file replacement。
  4. 寫入前驗證 content 計算出的 SHA-256 等於傳入值。
  5. 回傳 path、media_type、sha256、size_bytes。

  更新 _raw_and_transform_payload：保留現有 list/envelope 行為；遇到 CollectedPayload 時回傳 records、metadata 與 artifacts。更新 _run_execution_unit：先保存 artifacts，再將 artifact metadata 放入 raw JSON 的 source_artifacts 欄位，最後寫 raw JSON。

- [ ] Step 4: Run focused tests and verify GREEN.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_transform_pipeline -v

  Expected: 既有 pipeline tests 與新的 artifact tests 全部通過。

- [ ] Step 5: Commit.

    git add data-pipeline/src/collectors/contracts.py data-pipeline/src/transform/io.py data-pipeline/src/run_pipeline.py data-pipeline/tests/test_transform_pipeline.py
    git commit -m "feat(pipeline): persist source binary artifacts"

## Task 2: 建立青年局列表與 PDF collector

**Files:**

- Modify: data-pipeline/requirements.txt
- Create: data-pipeline/src/collectors/youth_budget.py
- Test: data-pipeline/tests/test_youth_budget.py

**Interfaces:**

- fetch_youth_budgets(*, list_url: str = BUDGET_LIST_URL, open_url: OpenURL = _open_url, years: Sequence[str] | None = None) -> CollectedPayload
- BudgetDocument(budget_year_roc: str, document_status: str, document_status_label: str, title: str, detail_url: str, pdf_url: str | None, published_date: str | None, updated_date: str | None)
- _parse_listing_page(html: str, *, page_url: str) -> list[BudgetDocument]
- _parse_document_status(label: str) -> tuple[str, str]
- _extract_budget_table(page_text: str, *, document: BudgetDocument, page_number: int) -> list[dict[str, Any]]
- BudgetCollectorError(RuntimeError)
- OpenURL is the existing Callable[..., Any] injectable urllib opener pattern used by the other collectors.

- [ ] Step 1: Add parser fixtures and failing tests.

  使用 inline fake HTML 與 extracted page-text fixture，覆蓋：

  1. 列表 parser 辨識 115/116 ROC 年度。
  2. 預算案、法定版、法定預算正確映射到 proposed_budget 或 legal_budget。
  3. 相對 detail URL 能以列表頁 URL 解析。
  4. detail parser 只選 PDF 連結。
  5. 目前表格文字能產生一個 total row 與三個 detail rows。
  6. 非 PDF bytes、缺少表格標題、缺少 header、重複 total、數值格式錯誤會拋出 BudgetCollectorError。
  7. 相同 PDF bytes 的 SHA-256 與 artifact filename 穩定。

  115 fixture 至少包含：

      業務計畫 工作計畫 本年度預算數 比率
      新北市政府青年局合計 213,022 100.00
      一般行政 一般行政 56,819 26.67
      青年發展業務 青年發展業務 155,903 73.19
      第一預備金 第一預備金 300 0.14

- [ ] Step 2: Run collector tests and verify RED.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_youth_budget -v

  Expected: module/import 或未實作 parser 的失敗。

- [ ] Step 3: Add PDF dependency and source constants.

  在 requirements.txt 加入 pypdf。collector 定義：

      BUDGET_LIST_URL = "https://www.youth.ntpc.gov.tw/youth/ch/app/data/list?module=youth0008&id=108"
      REQUEST_TIMEOUT_SECONDS = 120
      MAX_PDF_BYTES = 50 * 1024 * 1024

  使用既有 urllib.request pattern、injectable open_url 與 verified SSL context。下載內容只讀取一次，拒絕空檔案、超過大小限制或前四個 bytes 不是 %PDF- 的內容，並產生 sha256:<hex>。

- [ ] Step 4: Implement listing and detail discovery.

  以 Unicode normalization 後的 anchor text 匹配：

      r"新北市政府青年局主管(?P<year>\d{3})年度單位預算[（(](?P<status>[^）)]+)[）)]"

  實作 status mapping：

      預算案 -> proposed_budget
      法定版 -> legal_budget
      法定預算 -> legal_budget

  未知版本直接拋錯。跟進 detail URL，找出 PDF URL，並保存 listing URL、detail URL、文件標題、發布日期、更新日期。

- [ ] Step 5: Implement target-table extraction.

  使用 pypdf.PdfReader(io.BytesIO(pdf_bytes)) 逐頁搜尋 計畫及預算統計表 與 單位：新臺幣千元、%。不可把第 28 頁寫死；找到後記錄 one-based page number。

  解析 header 之後、頁尾之前的 rows。最後兩個 numeric cells 分別是 budget amount 與 ratio。三欄 row 解析為 total row 並令 work_plan=null；四欄 row 解析為 business/work plan detail row。保留原始 row text 與來源字串，不在 collector 計算數值或比率。

  每份 PDF 建立一個 SourceArtifact，filename 例如 115_legal_budget_0123456789ab.pdf；每筆 row 都帶 document_id、source_pdf_sha256、source_page_number 與 source_document_url。

- [ ] Step 6: Implement filtering and duplicate handling.

  years 未指定時處理列表頁所有符合規則的文件；指定時只保留指定 ROC 年。以 year、normalized status、sha256 去重同一文件，但不能去重掉同年度的 proposal/legal 版本。回傳包含 rows、documents metadata 與 PDF artifacts 的 CollectedPayload。

- [ ] Step 7: Run collector tests and verify GREEN.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_youth_budget -v

  Expected: listing、status、PDF validation、table parsing、hash 與 artifact tests 全部通過，且不呼叫網路。

- [ ] Step 8: Commit.

    git add data-pipeline/requirements.txt data-pipeline/src/collectors/youth_budget.py data-pipeline/tests/test_youth_budget.py
    git commit -m "feat(collector): parse youth bureau budget PDFs"

## Task 3: 新增 organization-level budget transform

**Files:**

- Modify: data-pipeline/src/transform/common.py
- Create: data-pipeline/src/transform/budget.py
- Modify: data-pipeline/src/transform/pipeline.py
- Test: data-pipeline/tests/test_transform_budget.py
- Test: data-pipeline/tests/test_transform_common.py
- Test: data-pipeline/tests/test_transform_pipeline.py

**Interfaces:**

- transform_youth_budgets(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None) -> TransformResult
- GEO_LEVELS includes organization and preserves district/county/national behavior.
- dataset_requires_resolver("youth_budgets") returns False.

- [ ] Step 1: Write failing transform tests.

  使用 115 與 116 raw fixtures，驗證：

      result.records[0]["dataset"] == "youth_budgets"
      result.records[0]["geo_level"] == "organization"
      result.records[0]["district_id"] is None
      result.records[0]["value"] == 213022
      result.records[0]["unit"] == "TWD_thousand"
      result.records[0]["period_start"] == "2026-01-01"
      result.records[0]["youth_eligibility"] == "context_only"

  另外測試 malformed amount/ratio、缺少 business plan、未知 document_status 會進 quarantine 並保留 raw_record。

- [ ] Step 2: Run transform tests and verify RED.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_transform_budget -v

  Expected: transform 不存在或 organization 尚未被 common metadata 接受。

- [ ] Step 3: Add organization geo level.

  將 organization 加入 transform/common.py 的 GEO_LEVELS。增加 focused common-metadata test，確認 organization 可以配合 district_id=null 與 district_name=null 建立 record。

- [ ] Step 4: Implement transform_youth_budgets.

  每筆 raw row：

  1. 用 parse_roc_year 轉換 ROC 年；用 parse_int 解析 budget_amount；用 parse_decimal 解析 ratio_percent。
  2. 驗證 document_status、row_type、business_plan 與 unit_label。
  3. 建立 common metadata：geo_level=organization、period_type=year、metric_id=budget_amount、unit=TWD_thousand、age_scope=not_age_specific、youth_eligibility=context_only。
  4. 加入 organization_name、新北市青年局、budget_year_roc、document_status、row_type、business_plan、work_plan、budget_ratio_percent、source_pdf_sha256 與 raw_record。
  5. 合法 row 呼叫 quality.accept()；不合法 row 以明確 reason quarantine。

  不加總 detail rows、不重新計算 source ratio、不把千元轉成元。

- [ ] Step 5: Register transform dispatch.

  在 transform/pipeline.py import transform_youth_budgets，將 youth_budgets 加入 _PLAIN_TRANSFORMS；不可加入 _GEOGRAPHIC_TRANSFORMS。

- [ ] Step 6: Run focused tests and verify GREEN.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_transform_budget tests.test_transform_common tests.test_transform_pipeline -v

  Expected: budget transform、common metadata 與 dispatch tests 全部通過。

- [ ] Step 7: Commit.

    git add data-pipeline/src/transform/common.py data-pipeline/src/transform/budget.py data-pipeline/src/transform/pipeline.py data-pipeline/tests/test_transform_budget.py data-pipeline/tests/test_transform_common.py data-pipeline/tests/test_transform_pipeline.py
    git commit -m "feat(transform): add organization-level youth budgets"

## Task 4: 註冊 source-aware pipeline、replay 與 resume

**Files:**

- Modify: data-pipeline/src/run_pipeline.py
- Modify: data-pipeline/tests/test_transform_pipeline.py
- Modify: data-pipeline/tests/test_orchestration_schedule.py

**Interfaces:**

- DEFAULT_COLLECTOR_SPECS contains CollectorSpec("youth_budgets", _collect_youth_budgets, PeriodStrategy.ALL_AVAILABLE)。
- _collect_youth_budgets(period: str) -> CollectedPayload；period 只作 execution provenance。

- [ ] Step 1: Write failing registry and pipeline tests.

  驗證 default registry 將 youth_budgets 設為 ALL_AVAILABLE；range run 只產生 curated/youth_budgets/all.json，不產生 monthly/annual partition。使用 injected CollectedPayload 加入一個 fake artifact，驗證 raw JSON、artifact、curated JSON、quality JSON、quarantine JSON 都建立。

  加入 replay test：以 --dataset youth_budgets --input 讀取產生的 raw JSON，確認不呼叫 collector、不下載 PDF。

- [ ] Step 2: Run orchestration/pipeline tests and verify RED.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_orchestration_schedule tests.test_transform_pipeline -v

  Expected: registry、output key 或 typed payload 支援尚未完成而失敗。

- [ ] Step 3: Register collector and preserve all-available semantics.

  Import youth_budget collector 與 CollectedPayload，新增 _collect_youth_budgets，並將 source 加入 DEFAULT_COLLECTOR_SPECS 的 ALL_AVAILABLE。不可加入 TDX specs。range execution 使用 source_period=end_period 作為 provenance，output_key 固定為 all。

- [ ] Step 4: Complete raw envelope and resume behavior.

  raw payload 必須包含 documents、source_artifacts 與 records。--resume 在 schema/transform version 相同且 curated/youth_budgets/all.json 存在時直接 reused_output；只有 transform version 變更時讀取既有 raw，不重新下載 PDF。--force 重新下載並建立新的 raw snapshot；內容相同的 PDF 可以依 hash 重用相同 artifact filename。

- [ ] Step 5: Run focused tests and verify GREEN.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_orchestration_schedule tests.test_transform_pipeline -v

  Expected: registry、ALL_AVAILABLE scheduling、artifact output、replay、resume 與 force tests 全部通過。

- [ ] Step 6: Commit.

    git add data-pipeline/src/run_pipeline.py data-pipeline/tests/test_transform_pipeline.py data-pipeline/tests/test_orchestration_schedule.py
    git commit -m "feat(pipeline): schedule youth budget source"

## Task 5: 更新 data contract 與文件

**Files:**

- Modify: data-pipeline/src/collectors/data.md
- Modify: data-pipeline/src/transform/transform.md
- Modify: data-pipeline/data-pipeline.md
- Modify: data-pipeline/data/data_description.md

- [ ] Step 1: Document collector behavior.

  在 collectors/data.md 補上官方列表來源、標題/status mapping、fetch_youth_budgets interface、ALL_AVAILABLE semantics、PDF artifact path 與 fake-test/live-source boundary。

- [ ] Step 2: Document raw and curated schemas.

  在 transform/transform.md 補上 raw envelope、curated common metadata、organization grain、TWD_thousand、proposal/legal coexistence、null rules，以及 ratio 是 source-provided 而非 pipeline 重算。

- [ ] Step 3: Document commands and output paths.

  在 data-pipeline.md 補上：

    cd data-pipeline
    PYTHONPATH=src python3 src/run_pipeline.py --start-period 11501 --end-period 11601 --output-dir data
    PYTHONPATH=src python3 src/run_pipeline.py --dataset youth_budgets --input data/raw/youth_budgets/11501_20260909T120000Z.json --output-dir data

  說明 dataset_index.json 指向 curated/youth_budgets/all.json，analytics 不可直接 glob curated directory。

- [ ] Step 4: Update data_description from actual output.

  Task 6 live run 後，依實際 JSON 補上 keys、rows、年度、document statuses、source unit、artifact metadata 與限制。不能宣稱列表頁以外的歷史完整性，也不能自行編造 sample。

- [ ] Step 5: Run documentation consistency checks.

    rg -n "youth_budgets|organization|proposed_budget|legal_budget|TWD_thousand" data-pipeline/src/collectors/data.md data-pipeline/src/transform/transform.md data-pipeline/data-pipeline.md data-pipeline/data/data_description.md

  Expected: changed sections 的 dataset name、output path、status、unit 全部一致，且沒有未完成標記。

- [ ] Step 6: Commit.

    git add data-pipeline/src/collectors/data.md data-pipeline/src/transform/transform.md data-pipeline/data-pipeline.md data-pipeline/data/data_description.md
    git commit -m "docs(pipeline): document youth budget dataset"

## Task 6: Live smoke validation 與完整驗證

**Files:**

- No source changes unless a verified failure requires a scoped fix.
- Read: generated raw/youth_budgets、curated/youth_budgets/all.json、quality、quarantine、dataset_index outputs。

- [ ] Step 1: Install declared PDF dependency in the project environment.

    data-pipeline/.venv/bin/python -m pip install -r data-pipeline/requirements.txt

  若 project environment 不存在，使用 repository 既有 documented Python environment；不可以移除 PDF parser 依賴取代安裝。

- [ ] Step 2: Run focused suite.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest tests.test_youth_budget tests.test_transform_budget tests.test_transform_pipeline tests.test_orchestration_schedule -v

  Expected: zero failures，且 focused tests 不呼叫 live network。

- [ ] Step 3: Run live source smoke check.

  執行以下 read-only smoke command，第一輪限制 ROC years=115、116。確認文件版本、target page、artifact hashes、row counts、amount 與 ratio，並與提供的兩份 PDF 比對。此命令只作驗證，不把 live output 當成測試 fixture。

    cd data-pipeline
    PYTHONPATH=src python3 -c 'from collectors.youth_budget import fetch_youth_budgets; import json; payload=fetch_youth_budgets(years=("115", "116")); print(json.dumps({"documents": payload.metadata.get("documents", []), "rows": payload.records}, ensure_ascii=False, indent=2))'

- [ ] Step 4: Run pipeline in a temporary output directory.

    cd data-pipeline
    PYTHONPATH=src python3 src/run_pipeline.py --start-period 11501 --end-period 11601 --output-dir /private/tmp/newtaipeihack-budget-data --strict

  檢查 collection_range.json、dataset_index.json、raw JSON、curated JSON、quality JSON、quarantine JSON 與 PDF artifacts。確認 unit=TWD_thousand、district fields=null、proposal/legal records coexist。

- [ ] Step 5: Run replay validation.

  使用以下命令選取第一個 raw JSON 並 replay 到第二個 temporary output directory，確認不需要網路且 curated records 與原始 transform output 一致。

    cd data-pipeline
    raw_path=$(find /private/tmp/newtaipeihack-budget-data/raw/youth_budgets -maxdepth 1 -name '*.json' -print -quit)
    PYTHONPATH=src python3 src/run_pipeline.py --dataset youth_budgets --input "$raw_path" --output-dir /private/tmp/newtaipeihack-budget-replay

- [ ] Step 6: Run full suite and static checks.

    cd data-pipeline
    PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
    python3 -m compileall -q src tests
    cd ..
    git diff --check

  Expected: unittest、compileall 與 git diff --check 都以 exit code 0 結束。

- [ ] Step 7: Commit only evidence-based documentation updates.

  若 data_description.md 是依 Task 6 實際 output 更新，僅提交該文件；不可把 ignored generated data-pipeline/data/raw、curated、quality、quarantine 加入 commit。

    git add data-pipeline/data/data_description.md
    git commit -m "docs(data): record youth budget output evidence"

## Completion Checklist

- [ ] Official listing discovery works with injected responses and live smoke validation.
- [ ] Current 115/116 tables parse into one total plus three detail rows each.
- [ ] PDF artifacts and JSON raw metadata are hash-addressed and replayable.
- [ ] youth_budgets is registered as ALL_AVAILABLE and indexed at curated/youth_budgets/all.json.
- [ ] Curated records use organization grain and preserve null district fields.
- [ ] Proposal/legal versions coexist without overwrite.
- [ ] Quality and quarantine output make parser failures visible.
- [ ] Documentation reflects actual output and focused/full verification commands pass.
