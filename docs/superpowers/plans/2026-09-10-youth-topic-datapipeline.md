# Youth Topic Data Pipeline Implementation Plan

> **For agentic workers:** Read `docs/superpowers/specs/2026-09-10-youth-topic-datapipeline-design.md` first. This plan is intentionally scoped to `data-pipeline`; do not modify Backend or Frontend. Steps use checkbox syntax for tracking. This plan does not include Git add/commit operations.

**Goal:** 新增 join 提案與青年局會議紀錄資料流，產生可重播的 curated records 與年度青年議題權重 JSON。

**Architecture:** 兩個 `ALL_AVAILABLE` collectors 各自保存來源 raw；source-specific transforms 將資料標準化但不計算跨來源分數；新增 analytics package 讀取 authoritative curated index，計算議題計數、訊號與 1–5 權重。文字雲圖片與字型大小仍由後續 Frontend 負責。

**Tech Stack:** Python standard library、`urllib`、`pypdf`、`jieba`、既有 `CollectedPayload`/`SourceArtifact`、local JSON outputs、`unittest`。

**Spec:** `docs/superpowers/specs/2026-09-10-youth-topic-datapipeline-design.md`

## Global Constraints

- `join_proposals` 與 `youth_council_minutes` 都使用 `PeriodStrategy.ALL_AVAILABLE`。
- collector 只保存來源資料與 artifact；transform 不呼叫 live API；跨來源分數只在 analytics 計算。
- 無年齡欄位的來源使用 `age_scope=not_age_specific` 與 `youth_eligibility=context_only`；青年議題判定另用 `youth_topic_proxy`。
- join 維持 national grain；青年局會議維持 organization grain；兩者的 district fields 都是 JSON `null`。
- raw、curated、analytics 都保留可追溯來源欄位；缺失值使用 `null`，不補 0。
- 同義詞只對同一 canonical topic 計算一次；每個輸出年度固定包含設定檔中的 22 個 topic。
- 不新增 PNG/SVG rendering；不修改 Backend、Frontend 或 AWS infrastructure。
- 單元測試使用 fake source responses；live source 只作獨立 smoke check。
- 既有 working-tree 修改不覆寫；本計畫不執行 `git add`、`git commit`、merge 或 push。

## File map

### New files

- `data-pipeline/config/youth_topic_rules.json`: 22 topics、aliases、proxy rules、PDF section/escalated rules。
- `data-pipeline/config/youth_topic_weights.json`: analytics coefficients and normalization version。
- `data-pipeline/config/youth_topic_userdict.txt`: jieba 青年議題詞典，固定詞組切分。
- `data-pipeline/config/youth_topic_stopwords.txt`: analytics 前處理使用的停用詞清單。
- `data-pipeline/src/collectors/join_proposals.py`: data.gov/join source discovery and raw rows。
- `data-pipeline/src/collectors/youth_council_minutes.py`: meeting document discovery, PDF download, text extraction and artifacts。
- `data-pipeline/src/transform/join_proposals.py`: join raw-to-curated transform。
- `data-pipeline/src/transform/youth_council_minutes.py`: page text to meeting-item transform。
- `data-pipeline/src/analytics/__init__.py`: analytics package marker。
- `data-pipeline/src/analytics/config.py`: typed topic-rule/weight config loaders and validation。
- `data-pipeline/src/analytics/io.py`: authoritative dataset index and curated JSON loading。
- `data-pipeline/src/analytics/youth_topic_weight.py`: topic matching, counts, scoring and output construction。
- `data-pipeline/src/run_analytics.py`: local analytics CLI。
- `data-pipeline/tests/test_join_proposals.py`: join collector tests。
- `data-pipeline/tests/test_youth_council_minutes.py`: PDF/listing collector tests。
- `data-pipeline/tests/test_transform_join_proposals.py`: join transform tests。
- `data-pipeline/tests/test_transform_youth_council_minutes.py`: minutes transform tests。
- `data-pipeline/tests/test_youth_topic_weight.py`: analytics formula tests。

### Modified files

- `data-pipeline/requirements.txt`: add the pinned-compatible `jieba` dependency。
- `data-pipeline/src/transform/pipeline.py`: register both transforms and canonical dataset names。
- `data-pipeline/src/run_pipeline.py`: import collectors, register all-available specs, forward `config_dir` to source-specific transforms, and support typed payloads already used by youth budgets。
- `data-pipeline/src/orchestration/refresh.py`: add both dataset names to supported refresh datasets。
- `data-pipeline/config/refresh_profiles.json`: add both sources to monthly refresh。
- `data-pipeline/src/orchestration/retention.py`: recognize `year_roc` in all-available record filtering。
- `data-pipeline/tests/test_orchestration_schedule.py`: verify all-available execution units。
- `data-pipeline/tests/test_orchestration_refresh.py`: verify refresh profile membership。
- `data-pipeline/tests/test_orchestration_retention.py`: verify old/new ROC year retention。
- `data-pipeline/tests/test_transform_pipeline.py`: verify typed payload, artifacts and raw replay for both sources。
- `data-pipeline/src/collectors/data.md`: document source interfaces and raw records。
- `data-pipeline/src/transform/transform.md`: document curated contracts and proxy rules。
- `data-pipeline/data-pipeline.md`: document output paths, analytics command and replay。
- `data-pipeline/data/data_description.md`: document actual curated keys and source limitations after a live smoke run。

---

### Task 1: Freeze topic/config and source contracts

**Files:**

- Create: `data-pipeline/config/youth_topic_rules.json`
- Create: `data-pipeline/config/youth_topic_weights.json`
- Create: `data-pipeline/config/youth_topic_userdict.txt`
- Create: `data-pipeline/config/youth_topic_stopwords.txt`
- Modify: `data-pipeline/requirements.txt`
- Create: `data-pipeline/src/analytics/config.py`
- Test: `data-pipeline/tests/test_youth_topic_weight.py`

**Interfaces:**

- `load_topic_rules(path: str | Path) -> YouthTopicRules`
- `load_topic_weights(path: str | Path) -> TopicWeights`
- `TopicDefinition.label: str`, `.aliases: tuple[str, ...]`, `.exclude_terms: tuple[str, ...]`
- `YouthTopicRules.topics: tuple[TopicDefinition, ...]`
- `YouthTopicRules.by_label: Mapping[str, TopicDefinition]`
- `TopicWeights.w_join`, `.w_minutes`, `.w_resolved`, `.w_escalated`

- [ ] **Step 1: Write the failing configuration tests.**

  Assert that the configuration loads exactly 22 labels, contains `社宅` under `社會住宅`, contains the proxy agencies/keywords, and contains all four coefficients:

  ```python
  rules = load_topic_rules(CONFIG_DIR / "youth_topic_rules.json")
  assert len(rules.topics) == 22
  assert "社宅" in rules.by_label["社會住宅"].aliases
  weights = load_topic_weights(CONFIG_DIR / "youth_topic_weights.json")
  assert (weights.w_join, weights.w_minutes) == (1.0, 1.8)
  assert (weights.w_resolved, weights.w_escalated) == (1.2, 2.5)
  ```

- [ ] **Step 2: Run the focused test and verify it fails.**

  Run from `data-pipeline`:

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_youth_topic_weight -v
  ```

  Expected: FAIL because the configuration loaders and files do not exist.

- [ ] **Step 3: Add the JSON configuration and minimal loaders.**

  Add all 22 existing frontend labels, aliases, proxy rules, section regexes, escalated phrases, and the four weight coefficients. The loader must reject duplicate labels, empty aliases, missing required coefficient keys, and unknown normalization names.

- [ ] **Step 4: Add `jieba` without coupling rendering to the pipeline.**

  Add `jieba>=0.42,<1` to `requirements.txt`, and add the configured user dictionary/stop-word files. The analytics matcher uses the configured user dictionary for token boundaries; it does not import the Python `word_cloud` renderer.

- [ ] **Step 5: Re-run the focused test.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_youth_topic_weight -v
  ```

  Expected: PASS for configuration loading and validation.

---

### Task 2: Implement the `join_proposals` collector

**Files:**

- Create: `data-pipeline/src/collectors/join_proposals.py`
- Create: `data-pipeline/tests/test_join_proposals.py`

**Interfaces:**

- `fetch_join_proposals(*, resource_urls: Sequence[str] | None = None, listing_url: str = JOIN_LIST_URL, open_url: OpenURL = _open_url) -> CollectedPayload`
- `_parse_resource_payload(payload: Any, *, source_url: str) -> list[dict[str, Any]]`
- `_parse_listing_page(html: str, *, page_url: str) -> list[ProposalDocument]`
- `JoinProposalCollectorError(RuntimeError)`

- [ ] **Step 1: Write fake JSON resource tests.**

  Use a payload with Chinese source keys and one payload with canonical keys. Assert that title, content, endorsement count, dates, URL, optional fields, `source_payload`, and `year_roc` are preserved. Missing category/agency/status must become `None`.

- [ ] **Step 2: Write fallback listing/detail tests.**

  Provide fake paginated listing HTML and detail HTML. Assert that the collector discovers each proposal URL, fetches detail text, deduplicates the same proposal ID, and records a per-document failure without discarding successful records.

- [ ] **Step 3: Run focused tests and verify RED.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_join_proposals -v
  ```

  Expected: FAIL because the collector module and parser functions do not exist.

- [ ] **Step 4: Implement source adapters.**

  Try configured data.gov resources first. Decode JSON by content rather than assuming a file extension. Keep the fallback listing adapter injectable so tests do not require live HTTP. Use request timeout, generic `Accept`, a project User-Agent, and explicit response-size limits.

- [ ] **Step 5: Implement raw field normalization without analytics.**

  Normalize key names and whitespace only. Preserve every unknown source field under `source_payload`. Parse `endorsement_count` only as a raw-safe string/int field; do not calculate scores or filter youth topics in the collector. Add `year_roc` from the source submission date for retention and preserve the original date string.

- [ ] **Step 6: Return `CollectedPayload`.**

  Metadata must contain source URLs, discovered count, successful count, skipped count, failures, and source retrieval time. Records remain JSON serializable and artifacts remain empty for this source.

- [ ] **Step 7: Run the collector tests and verify GREEN.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_join_proposals -v
  ```

  Expected: all fake-source parsing, deduplication, optional-field, and failure tests pass.

---

### Task 3: Implement the `youth_council_minutes` collector

**Files:**

- Create: `data-pipeline/src/collectors/youth_council_minutes.py`
- Create: `data-pipeline/tests/test_youth_council_minutes.py`

**Interfaces:**

- `fetch_youth_council_minutes(*, listing_url: str = MINUTES_LIST_URL, open_url: OpenURL = _open_url) -> CollectedPayload`
- `_parse_listing_page(html: str, *, page_url: str) -> list[MeetingDocument]`
- `_extract_pdf_pages(pdf_bytes: bytes) -> list[str]`
- `_build_source_artifact(document: MeetingDocument, pdf_bytes: bytes) -> SourceArtifact`
- `YouthCouncilMinutesCollectorError(RuntimeError)`

- [ ] **Step 1: Write listing and PDF detection tests.**

  Fake the official index page with first-to-sixth-term links. Cover a detail URL that returns PDF bytes without a `.pdf` suffix and a detail URL that returns HTML containing a PDF link. Assert that both produce one document.

- [ ] **Step 2: Write artifact and text extraction tests.**

  Patch `_extract_pdf_pages` with deterministic page text. Assert that the payload contains `meeting_id`, `meeting_date`, `term`, `year_roc`, `page_texts`, `source_pdf_sha256`, and a stable `SourceArtifact.filename`.

- [ ] **Step 3: Write failure tests.**

  Assert that empty bytes, non-PDF bytes, oversized PDF bytes, missing meeting date, and PDF extraction errors are recorded as document failures. A failure in one document must not erase other successful documents.

- [ ] **Step 4: Run focused tests and verify RED.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_youth_council_minutes -v
  ```

  Expected: FAIL because the collector module and artifact parser do not exist.

- [ ] **Step 5: Implement dynamic discovery and PDF extraction.**

  Follow the official meeting-record links, detect PDF by magic bytes/content type, download with the existing verified SSL pattern, enforce a maximum size, hash the exact bytes, and extract every page with `pypdf.PdfReader`.

- [ ] **Step 6: Return metadata and artifacts.**

  The raw payload must contain `documents`, `records`, and artifact references after the pipeline writer persists the binary files. Store each page text in the record so `--input` replay does not use the artifact or network.

- [ ] **Step 7: Run the collector tests and verify GREEN.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_youth_council_minutes -v
  ```

  Expected: all fake listing, PDF, hash, extraction, and partial-failure tests pass.

---

### Task 4: Add source-specific transforms

**Files:**

- Create: `data-pipeline/src/transform/join_proposals.py`
- Create: `data-pipeline/src/transform/youth_council_minutes.py`
- Modify: `data-pipeline/src/transform/pipeline.py`
- Test: `data-pipeline/tests/test_transform_join_proposals.py`
- Test: `data-pipeline/tests/test_transform_youth_council_minutes.py`

**Interfaces:**

- `transform_join_proposals(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None, rules: YouthTopicRules) -> TransformResult`
- `transform_youth_council_minutes(records: Iterable[Mapping[str, Any]], *, fetched_at: str | None = None, rules: YouthTopicRules) -> TransformResult`
- `run_transform("join_proposals", records, fetched_at=..., config_dir=...)`
- `run_transform("youth_council_minutes", records, fetched_at=..., config_dir=...)`

- [ ] **Step 1: Write join transform tests.**

  Assert common metadata, `geo_level=national`, null district fields, Gregorian year boundaries, `context_only`, `youth_topic_proxy`, `proxy_reasons`, numeric endorsement parsing, and `raw_record` preservation. Include a non-matching proposal and assert it remains in curated output with `youth_topic_proxy=false`.

- [ ] **Step 2: Write meeting transform tests.**

  Use page text containing `討論事項`, `提案事項`, `決議`, and an escalated phrase. Assert one item record per proposal, correct page provenance, discussed/resolved/escalated flags, and precedence. Add a missing-resolution fixture and assert `parse_status=partial` plus `manual_review_required=true`.

- [ ] **Step 3: Run focused tests and verify RED.**

  ```bash
  PYTHONPATH=src python3 -m unittest \
    tests.test_transform_join_proposals \
    tests.test_transform_youth_council_minutes -v
  ```

  Expected: FAIL because the transform modules and registry entries do not exist.

- [ ] **Step 4: Implement join transform.**

  Use existing `clean_text`, `parse_int`, `parse_roc_date`, `build_common_metadata`, and `QualityCollector`. Do not discard non-proxy rows. Apply agency/keyword proxy rules only to add flags and reasons.

- [ ] **Step 5: Implement meeting section parser and transform.**

  Normalize NFKC whitespace, split pages into section blocks using configured regexes, extract item boundaries and item text, detect escalated phrases only within the applicable resolution text, and quarantine records missing required meeting identity. Preserve source text and page numbers.

- [ ] **Step 6: Register both canonical datasets.**

  Add imports and entries to `_PLAIN_TRANSFORMS` in `transform/pipeline.py`. Add an optional `config_dir` argument to `run_transform`; only these two transforms load `YouthTopicRules` from that directory. Neither dataset belongs in `_GEOGRAPHIC_TRANSFORMS`; `dataset_requires_resolver()` must remain false for both.

- [ ] **Step 7: Run focused tests and verify GREEN.**

  ```bash
  PYTHONPATH=src python3 -m unittest \
    tests.test_transform_join_proposals \
    tests.test_transform_youth_council_minutes \
    tests.test_transform_pipeline -v
  ```

  Expected: all transform, registry, metadata, section, and quarantine tests pass.

---

### Task 5: Register collection, replay, refresh, and retention

**Files:**

- Modify: `data-pipeline/src/run_pipeline.py`
- Modify: `data-pipeline/src/orchestration/refresh.py`
- Modify: `data-pipeline/config/refresh_profiles.json`
- Modify: `data-pipeline/src/orchestration/retention.py`
- Test: `data-pipeline/tests/test_transform_pipeline.py`
- Test: `data-pipeline/tests/test_orchestration_schedule.py`
- Test: `data-pipeline/tests/test_orchestration_refresh.py`
- Test: `data-pipeline/tests/test_orchestration_retention.py`

**Interfaces:**

- `_collect_join_proposals(_period: str) -> CollectedPayload`
- `_collect_youth_council_minutes(_period: str) -> CollectedPayload`
- `CollectorSpec("join_proposals", ..., PeriodStrategy.ALL_AVAILABLE)`
- `CollectorSpec("youth_council_minutes", ..., PeriodStrategy.ALL_AVAILABLE)`

- [ ] **Step 1: Write registry and schedule tests.**

  Assert both datasets are in `DEFAULT_COLLECTOR_SPECS`, both use `ALL_AVAILABLE`, the output key is `all`, and a range from `11001` to `11509` invokes each all-available collector once.

- [ ] **Step 2: Write typed-payload and artifact integration tests.**

  Inject fake `CollectedPayload` values and assert the runner writes raw JSON, PDF artifact metadata, `curated/{dataset}/all.json`, quality, quarantine, and dataset-index entries.

- [ ] **Step 3: Write replay tests.**

  Run `--dataset <dataset> --input <raw>` with the collector patched to raise if called. Assert curated output is rebuilt without network or PDF download.

- [ ] **Step 4: Write refresh and retention tests.**

  Assert the monthly profile contains both datasets. Use `year_roc` values `109`, `110`, `114`, and `115` to verify retention keeps the configured window and removes only stale records. Keep unknown-period records rather than deleting them.

- [ ] **Step 5: Register the collectors and refresh names.**

  Import both collectors, add all-available specs, add both names to `SUPPORTED_DATASETS`, and add both to the monthly refresh profile. Forward `config_dir` from normal pipeline and `--input` replay calls into `run_transform`, so source-specific transforms use the selected topic rules. Use the existing artifact persistence path for meeting PDFs.

- [ ] **Step 6: Extend retention for `year_roc`.**

  Add `year_roc` to `_record_period()` as an annual key. Do not change snapshot freshness rules or delete unknown-period records.

- [ ] **Step 7: Run orchestration tests and verify GREEN.**

  ```bash
  PYTHONPATH=src python3 -m unittest \
    tests.test_transform_pipeline \
    tests.test_orchestration_schedule \
    tests.test_orchestration_refresh \
    tests.test_orchestration_retention -v
  ```

  Expected: all registry, all-available, artifact, replay, refresh, and retention tests pass.

---

### Task 6: Implement youth topic analytics

**Files:**

- Create: `data-pipeline/src/analytics/__init__.py`
- Create: `data-pipeline/src/analytics/io.py`
- Create: `data-pipeline/src/analytics/youth_topic_weight.py`
- Create: `data-pipeline/src/run_analytics.py`
- Test: `data-pipeline/tests/test_youth_topic_weight.py`

**Interfaces:**

- `load_curated_dataset(dataset: str, *, output_dir: str | Path) -> list[dict[str, Any]]`
- `calculate_youth_topic_weights(join_records: Iterable[Mapping[str, Any]], minute_records: Iterable[Mapping[str, Any]], *, rules: YouthTopicRules, weights: TopicWeights) -> dict[str, Any]`
- `write_youth_topic_weights(result: Mapping[str, Any], *, output_dir: str | Path) -> tuple[Path, Path]`
- CLI: `python src/run_analytics.py --metric youth_topic_weight --output-dir data --config-dir config`

- [ ] **Step 1: Write deterministic formula tests.**

  Use two years and three topics. Assert:

  ```python
  result = calculate_youth_topic_weights(join_rows, minute_rows, rules=rules, weights=weights)
  topic = result["years"][0]["topics"][0]
  assert topic["join_mentions"] == 2
  assert topic["minutes_mentions"] == 1
  assert 1 <= topic["weight"] <= 5
  ```

  Also test alias merging, one-count-per-record behavior, `log1p` support score, yearly normalization, all-zero scores, minutes floor 3, escalated force 5, and `signal` precedence.

- [ ] **Step 2: Write dataset-index loading tests.**

  Create a temporary `quality/dataset_index.json` pointing to two curated files. Assert analytics reads only indexed files, rejects a missing required dataset, and does not glob unrelated curated files.

- [ ] **Step 3: Run analytics tests and verify RED.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_youth_topic_weight -v
  ```

  Expected: FAIL because the analytics package, loaders, and calculator do not exist.

- [ ] **Step 4: Implement topic matching.**

  Normalize text, apply aliases longest-first, tokenize with configured jieba dictionary when needed, and return a set of canonical labels per record. Never count multiple aliases from the same record as multiple mentions.

- [ ] **Step 5: Implement per-year aggregation.**

  Filter join rows to `youth_topic_proxy=true`; match title/content. Match minutes item `source_text`; count distinct `source_record_id` per topic/year. Aggregate resolved/escalated booleans and keep source counts.

- [ ] **Step 6: Implement score, quantization, and provenance.**

  Apply the spec formula, add `calculation_version`, source dataset names, config version, normalization name, generated timestamp, and one fixed 22-topic list per available year. Use `None` for signal when no signal exists.

- [ ] **Step 7: Implement the CLI writer.**

  Read `dataset_index.json`, load both curated files, calculate the result, atomically write `data/analytics/youth_topic_weight/all.json`, and write a quality report containing input counts, matched counts, year coverage, and config version.

- [ ] **Step 8: Run analytics tests and verify GREEN.**

  ```bash
  PYTHONPATH=src python3 -m unittest tests.test_youth_topic_weight -v
  ```

  Expected: all formula, alias, normalization, output-shape, and index-loading tests pass.

---

### Task 7: Document the contract and perform end-to-end verification

**Files:**

- Modify: `data-pipeline/src/collectors/data.md`
- Modify: `data-pipeline/src/transform/transform.md`
- Modify: `data-pipeline/data-pipeline.md`
- Modify: `data-pipeline/data/data_description.md`

- [ ] **Step 1: Document collector and raw contracts.**

  Add source URLs, fallback behavior, raw fields, PDF artifact paths, `page_texts`, failure behavior, and fake-source test boundary.

- [ ] **Step 2: Document curated contracts.**

  Add both dataset schemas, grain, null rules, `year_roc`, proxy semantics, section flags, manual-review flags, and `raw_record` preservation.

- [ ] **Step 3: Document analytics output and command.**

  Add the exact output path, JSON shape, formula, coefficients, normalization rule, and command:

  ```bash
  cd data-pipeline
  PYTHONPATH=src python3 src/run_analytics.py \
    --metric youth_topic_weight \
    --output-dir data \
    --config-dir config
  ```

- [ ] **Step 4: Run the full data-pipeline test suite.**

  ```bash
  cd data-pipeline
  PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_*.py'
  ```

  Expected: existing tests and new tests all pass.

- [ ] **Step 5: Run compilation and diff checks.**

  ```bash
  PYTHONPATH=src python3 -m compileall -q src tests
  git diff --check
  ```

- [ ] **Step 6: Run isolated live smoke checks.**

  Execute only the two new collectors against official sources, save outputs under a temporary directory, and inspect:

  - discovered source/document count;
  - year coverage;
  - raw-to-curated row count;
  - failed/partial document count;
  - PDF artifact hash and replay result;
  - analytics 22-topic output for each available year.

  Do not copy mutable live counts into documentation until they are generated from the resulting curated JSON and quality reports.

## Completion checklist

- [ ] Spec requirements are represented by Tasks 1–7.
- [ ] No collector performs cross-source analytics.
- [ ] No analytics reads unindexed curated files.
- [ ] No data is silently converted to zero or nearest district.
- [ ] Raw replay works for both sources.
- [ ] `weight` is calculated only in analytics.
- [ ] Frontend/Backend files remain untouched in this phase.
- [ ] Full test, compile, and diff checks have verified the implementation before claiming completion.
