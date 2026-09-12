# Source Provenance and DynamoDB Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不重新上傳既有 Raw 的前提下，建立 source registry、legacy provenance enrichment、published source contract，以及可供 DynamoDB／Backend／Frontend 顯示的 `sourceName` 與 `sourceUrl`。

**Architecture:** `data-pipeline/config/sources.json` 是穩定來源定義；新 Raw 保存當次 source metadata，舊 Raw 只讀並在 transform/replay 時由 registry 補值。Pipeline 將來源資訊帶入 curated 與 versioned published snapshot；DynamoDB 只保存同一 snapshot 的 serving projection，Backend 不重新計算或掃描 Raw。

**Tech Stack:** Python 3、既有 `CollectedPayload`／local JSON pipeline、JSON schema-like validation、pytest/unittest、TypeScript shared API contract、既有 DynamoDB snapshot key contract。

**Spec:** `docs/superpowers/specs/2026-09-12-source-provenance-design.md`

**Execution status (2026-09-12):** Tasks 1–5 and the local end-to-end handoff
are implemented on the current `datapipeline` branch. Backend adapter tests and
the actual AWS/DynamoDB deployment remain a handoff because `backend/` is still
a placeholder package without test/build scripts; no AWS resource or Raw object
was changed.

## Global Constraints

- 既有 `data-pipeline/data/raw/` 與已上傳 S3 Raw 視為 immutable；本計畫不得覆蓋或要求重新下載歷史 Raw。
- 來源 ID 使用既有 snake_case，例如 `moi_household_registration`；不得由 Frontend 建立 source-to-name mapping。
- `sourceUrl` 必須是可查證的官方 HTTP(S) URL；無法確認時使用 `null`，不得猜測。
- Published snapshot 不得包含 `raw_record` 或 `raw_records`。
- DynamoDB key 維持 `SNAPSHOT#{snapshot_id}#RESOURCE#...`／resource-specific `SK`；來源欄位不是 key。
- 只修改 working tree；除非使用者另外要求，不執行 `git add`、`git commit`、push 或 AWS apply。

---

### Task 1: 建立來源 registry 與驗證介面

**Files:**
- Create: `data-pipeline/config/sources.json`
- Create: `data-pipeline/src/source_registry.py`
- Create: `data-pipeline/tests/test_source_registry.py`
- Modify: `data-pipeline/data-pipeline.md`

**Interfaces:**
- Produces `SourceDefinition(source: str, name_zh: str, source_url: str | None, url_type: str)`。
- Produces `SourceContext(source: str | None, source_name: str | None, source_url: str | None, url_type: str | None, warnings: tuple[str, ...])`。
- Produces `SourceRegistry.from_json(path) -> SourceRegistry`。
- Produces `SourceRegistry.dataset_source(dataset: str) -> str | None`。
- Produces `SourceRegistry.resolve(dataset: str, source: str | None = None, source_url: str | None = None) -> SourceContext`。
- Produces `SourceRegistry.public_catalog() -> list[dict[str, Any]]`，欄位為 `source`、`sourceName`、`sourceUrl`、`urlType`。

- [x] **Step 1: Write registry contract tests first**

```python
def test_registry_resolves_id_to_public_source_fields(tmp_path):
    path = tmp_path / "sources.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "sources": {
            "moi_household_registration": {
                "name_zh": "內政部戶政司",
                "source_url": "https://example.gov.tw/population",
                "url_type": "dataset"
            }
        },
        "dataset_defaults": {"population": "moi_household_registration"}
    }), encoding="utf-8")

    registry = SourceRegistry.from_json(path)
    context = registry.resolve(dataset="population")

    assert context.source == "moi_household_registration"
    assert context.source_name == "內政部戶政司"
    assert context.source_url == "https://example.gov.tw/population"
```

- [x] **Step 2: Run the focused test and verify it fails**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_source_registry.py`

Expected: FAIL because `source_registry.py` and `sources.json` do not exist.

- [x] **Step 3: Add the registry file and strict loader**

`sources.json` must contain every source ID currently emitted by transforms: `moi_household_registration`, `ntpc_youth_bureau_budget`, `ntpc_social_affairs_babysitting`, `moe_9620`, `moe_9621_9622`, `cec_election_candidate_roster`, `new_taipei_real_estate_open_data`, `join_gov_public_policy_platform`, `dgbas_table_6`, `taiwanjobs`, `ntpc_youth_bureau_startup_base`, `mol_talent_demand`, `mol_training_numbers`, `mol_vocational_courses`, `tdx`, `nlsc_village_boundaries`, `ntpc_youth_bureau_meeting_minutes`、`ntpc_youth_bureau_grant_detail`。URL 應沿用各 collector 已存在的官方 landing/resource 常數；動態 resource 使用穩定資料集頁面。

Loader must reject non-object JSON, unsupported `schema_version`, duplicate source IDs, missing `name_zh`, and non-HTTP(S) `source_url`. Unknown source IDs are allowed during resolution so legacy records can remain readable, but return a context with nullable name/URL and a warning.

- [x] **Step 4: Run the focused tests**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_source_registry.py`

Expected: PASS, including dataset default lookup, explicit source override, URL validation, unknown source handling, and deterministic catalog ordering.

- [x] **Step 5: Document registry ownership**

Document that the registry is packaged with the pipeline Lambda artifact, Raw stores runtime provenance, and DynamoDB is only the read projection. State that changing a canonical URL creates a new pipeline/published version; it does not mutate historical Raw.

### Task 2: Make new Raw envelopes source-aware without rewriting legacy Raw

**Files:**
- Modify: `data-pipeline/src/run_pipeline.py:1293-1346` (`_raw_and_transform_payload`) and execution-unit/replay call sites
- Modify: `data-pipeline/src/transform/common.py:143-205` (`build_common_metadata`)
- Create: `data-pipeline/src/transform/provenance.py`
- Create: `data-pipeline/tests/test_source_provenance.py`
- Modify: `data-pipeline/tests/test_transform_common.py`
- Modify: `data-pipeline/tests/test_transform_pipeline.py`

**Interfaces:**
- `build_common_metadata(..., source_url: str | None = None) -> dict[str, Any]` adds nullable curated `source_url`.
- `enrich_curated_records(records, *, dataset, raw_payload, registry) -> tuple[list[dict[str, Any]], dict[str, Any]]` copies records, fills `source_url`, and returns a resolution report.
- `_raw_and_transform_payload(..., source_registry: SourceRegistry | None = None)` always adds nullable `source`, `source_url`, and `source_url_type` for newly collected envelopes.

- [x] **Step 1: Add failing tests for all three input shapes**

Cover:

1. Generic list collector receives `source` from `dataset_defaults`.
2. `CollectedPayload.metadata.source_url` overrides the registry URL.
3. Existing envelope with no source fields remains untouched when it is reused, while the resulting curated record receives registry provenance.
4. A record that already has a source ID keeps that ID instead of being overwritten by the dataset default.
5. Unknown source produces `source_unresolved` or `unknown_source_id` in the resolution report and leaves URL as `None`.

- [x] **Step 2: Run the focused tests to verify they fail**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_source_provenance.py tests/test_transform_common.py tests/test_transform_pipeline.py -k source`

Expected: FAIL because no registry-aware envelope builder or curated provenance enrichment exists.

- [x] **Step 3: Implement the source resolution boundary**

Use this precedence in `enrich_curated_records`:

```python
record_source = record.get("source") or raw_payload.get("source")
context = registry.resolve(
    dataset=dataset,
    source=record_source,
    source_url=raw_payload.get("source_url") or record.get("source_url"),
)
record["source"] = context.source
record["source_url"] = context.source_url
```

Do not mutate the input record or Raw payload. Preserve dataset-specific fields such as `source_document_url`, `proposal_url`, and `geocode_source_url`; `source_url` is the canonical dataset/source verification URL.

- [x] **Step 4: Load the registry once per pipeline run and enrich before `write_curated`**

`run_full_pipeline`, `run_period_range`, `run_refresh`, and replay mode must load `config/sources.json`. New collections pass the registry to `_raw_and_transform_payload`; legacy reuse passes the loaded Raw payload to `enrich_curated_records` without writing the Raw file again. Add a per-dataset `source_resolution` object to the existing collection status with resolved IDs, unresolved count, and warning codes.

- [x] **Step 5: Update the common curated contract**

Add `source_url` after `source` in `build_common_metadata`, with a default of `None`, and update the existing test from the old field count to the new explicit contract. The central enrichment step must fill this field for both newly collected and legacy-replayed records.

- [x] **Step 6: Run the focused and regression tests**

Run:

```bash
cd data-pipeline
.venv/bin/python -m pytest -q tests/test_source_provenance.py tests/test_transform_common.py tests/test_transform_pipeline.py
```

Expected: PASS; existing transform behavior and record fields remain unchanged except for the new nullable `source_url`.

### Task 3: Backfill curated output from existing Raw through replay/resume

**Files:**
- Modify: `data-pipeline/src/run_pipeline.py:1035-1058` (`_run_replay`)
- Create: `data-pipeline/tests/test_legacy_raw_replay.py`
- Modify: `data-pipeline/src/transform/transform.md`
- Modify: `data-pipeline/data/data_description.md`

**Interfaces:**
- Replay consumes an old Raw envelope or raw record list and produces curated/quality/quarantine output with the same `SourceRegistry` interface as normal runs.
- Replay returns exit code `0` for a resolvable legacy source and records unresolved provenance in quality output instead of silently inventing a URL.

- [x] **Step 1: Write the immutability test**

Create a temporary legacy Raw file with only `dataset`, `period`, `fetched_at`, and `records`; compute its SHA-256 before replay. Run the replay path with a registry mapping. Assert that the Raw bytes and hash are unchanged, curated records contain `source == "moi_household_registration"` and the canonical `source_url`, and no new Raw file is written.

- [x] **Step 2: Run the test to verify it fails**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_legacy_raw_replay.py`

Expected: FAIL because replay currently passes only records to the transform and drops the Raw envelope provenance context.

- [x] **Step 3: Preserve the full legacy envelope during replay**

Change `_run_replay` to retain the decoded payload, derive `fetched_at` as it does today, call `enrich_curated_records` after `run_transform`, and pass the enriched `TransformResult` to `write_curated`. Do not call `write_raw` in replay mode.

- [x] **Step 4: Verify the real checked-in legacy sample**

Run the replay test against `data-pipeline/data/raw/population/11202_20260901T155328601881Z.json` using a temporary output directory. Assert the source is resolved from `dataset_defaults`, the input file is byte-identical, and generated curated JSON contains no `raw_records` requirement beyond the existing internal curated contract.

- [x] **Step 5: Document the migration command**

Document the safe historical reprocessing path:

```bash
cd data-pipeline
PYTHONPATH=src .venv/bin/python src/run_pipeline.py \
  --input data/raw/population/11202_20260901T155328601881Z.json \
  --dataset population \
  --output-dir data \
  --config-dir config
```

Explain that this regenerates curated/quality/quarantine only; it does not re-download or overwrite Raw.

- [x] **Step 6: Run replay and full pipeline tests**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_legacy_raw_replay.py tests/test_run_pipeline_refresh.py tests/test_orchestration_retention.py`

Expected: PASS and existing retention/index behavior remains unchanged.

### Task 4: Publish a versioned source catalog and multi-source provenance

**Files:**
- Create: `data-pipeline/src/analytics/provenance.py`
- Modify: `data-pipeline/src/analytics/published_snapshot.py`
- Modify: `data-pipeline/src/run_analytics.py`
- Create: `data-pipeline/tests/test_published_source_catalog.py`
- Modify: `data-pipeline/tests/test_published_snapshot.py`
- Modify: `docs/superpowers/plans/2026-09-12-unified-published-release.md` only to link this source contract

**Interfaces:**
- `build_public_source_catalog(registry) -> list[dict[str, Any]]` returns deterministic camelCase source entries.
- `source_refs_for_datasets(dataset_names, registry) -> list[str]` returns sorted unique source IDs.
- `publish_homepage_snapshot(..., source_catalog: Sequence[Mapping[str, Any]] = ())` writes `manifest.sources` without changing the atomic `current.json` behavior.

- [x] **Step 1: Write the manifest and derived-source tests**

Assert that a published manifest contains:

```json
{
  "sources": [
    {
      "source": "moi_household_registration",
      "sourceName": "內政部戶政司",
      "sourceUrl": "https://example.gov.tw/population",
      "urlType": "dataset"
    }
  ]
}
```

Also assert that a synthetic analysis using multiple datasets exposes `sourceRefs` and does not choose one arbitrary `sourceUrl`.

- [x] **Step 2: Run the tests to verify they fail**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_published_source_catalog.py`

Expected: FAIL because the publisher does not yet accept a source catalog.

- [x] **Step 3: Add source catalog to the published snapshot**

Load the registry once in the `all` analytics path, pass its public catalog to `publish_homepage_snapshot`, and add source IDs to each manifest dataset entry. Keep existing analytics payload shapes stable; only add source metadata fields where the public metric contract already has a metric object. For derived homepage rows, add `sourceRefs` at the resource/metric metadata level rather than pretending the YOI has one source.

- [x] **Step 4: Preserve atomic publication semantics**

Write all snapshot artifacts, including `manifest.sources`, before updating `current.json`. A source registry validation or source catalog failure must leave the previous current pointer unchanged.

- [x] **Step 5: Run analytics/publisher regression tests**

Run:

```bash
cd data-pipeline
.venv/bin/python -m pytest -q tests/test_published_source_catalog.py tests/test_analytics_input_resolver.py
```

Expected: PASS; published output still excludes `raw_record`/`raw_records`, and the existing snapshot id/current pointer behavior is unchanged.

### Task 5: Define the DynamoDB projection fields and pure item builder

**Files:**
- Create: `data-pipeline/src/publish/__init__.py`
- Create: `data-pipeline/src/publish/dynamo_projection.py`
- Create: `data-pipeline/tests/test_dynamo_projection.py`
- Create: `shared/src/metrics.ts`
- Create: `shared/src/index.ts`
- Modify: `shared/shared.md`

**Interfaces:**
- `project_metric_source(metric, source_catalog) -> dict[str, Any]` returns `source`, `sourceName`, `sourceUrl`, and `sourceRefs` without changing the metric value.
- `project_snapshot_items(snapshot_dir, manifest) -> list[dict[str, Any]]` emits the existing PK/SK plus source attributes; it performs no AWS network call.
- Shared `MetricValue` adds:

```ts
source: string | null;
sourceName: string | null;
sourceUrl: string | null;
sourceRefs: string[];
```

- [x] **Step 1: Write pure projection tests**

Use a fake published snapshot and assert:

```python
assert item["PK"] == "SNAPSHOT#fixture#RESOURCE#district_details"
assert item["SK"] == "DISTRICT#65000010"
assert item["metrics"]["population"]["source"] == "moi_household_registration"
assert item["metrics"]["population"]["sourceName"] == "內政部戶政司"
assert item["metrics"]["population"]["sourceUrl"].startswith("https://")
```

Add a multi-source case that returns `source is None`, `sourceUrl is None`, and a sorted non-empty `sourceRefs` list.

- [x] **Step 2: Run the focused test to verify it fails**

Run: `cd data-pipeline && .venv/bin/python -m pytest -q tests/test_dynamo_projection.py`

Expected: FAIL because the pure projection module does not exist.

- [x] **Step 3: Implement the projection without changing table keys**

Use the published manifest source catalog to resolve names and URLs. Do not make the projection builder read Raw, Curated, or call a government API. A missing source definition preserves the source ID and emits nullable display fields plus a projection warning.

- [x] **Step 4: Add shared TypeScript contract tests**

Add fixture assertions that direct metrics accept `sourceName`/`sourceUrl`, derived metrics use `sourceRefs`, and `null` remains a valid value. Do not put source lookup logic in the shared types or Frontend.

- [x] **Step 5: Run Python and TypeScript checks**

Run:

```bash
cd data-pipeline && .venv/bin/python -m pytest -q tests/test_dynamo_projection.py
cd .. && npm --workspace @newtaipei-youth/shared run build
```

Expected: PASS with no AWS credentials and no network calls.

### Task 6: Connect the projection to the existing Backend/DynamoDB contract

**Files:**
- Modify: `docs/superpowers/plans/2026-09-10-backend-read-api.md` metric contract and loader handoff sections
- Modify: `backend/backend.md`
- Modify: `infrastructure/infrastructure.md`

**Interfaces:**
- Backend reads source display fields from the DynamoDB item; it does not call `sources.json`, S3 Raw, or an external government URL at request time.
- The existing `PublishedDataStore` and snapshot key contract remain unchanged.

- [x] **Step 1: Document the contract handoff before adapter changes**

Record the exact shared contract change in the Backend read API plan: a direct metric fixture has `source`, `sourceName`, and `sourceUrl`; a derived metric fixture has `sourceRefs`. The API must serialize both without dropping the URL or converting `null` to an empty string.

- [x] **Step 2: Update the DynamoDB adapter mapping in the Backend plan**

When executing the existing Backend read API plan, map the new attributes through the same response schema used by Local JSON. Keep the query keys exactly:

```text
dashboard overview: PK=SNAPSHOT#{snapshot_id}#RESOURCE#dashboard_overview
district detail:   PK=SNAPSHOT#{snapshot_id}#RESOURCE#district_details
analysis rows:     PK=SNAPSHOT#{snapshot_id}#ANALYSIS#{analysis_id}
```

- [ ] **Step 3: Verify no request-time enrichment was added in Backend tests**

The adapter tests must use a fake DocumentClient and verify one keyed `GetItem`/`Query`; they must not read `sources.json`, scan DynamoDB, or call a URL.

- [x] **Step 4: Document deployment boundary**

Backend adapter verification is pending: the current `backend/package.json` has
no `test` or `build` script, so this feature does not add a second mock adapter
or claim that the API layer is implemented.

Document that `sources.json` is packaged with the pipeline artifact, the published snapshot contains its immutable source catalog, and the future pipeline/DynamoDB loader writes the projection before exposing the new snapshot id to Backend. Do not apply Terraform in this feature plan.

### Task 7: End-to-end verification and handoff

**Files:**
- Modify: `data-pipeline/src/transform/transform.md`
- Modify: `data-pipeline/data/data_description.md`
- Modify: `backend/backend.md`
- Modify: `infrastructure/infrastructure.md`
- Create: `data-pipeline/tests/test_source_provenance_e2e.py`

- [x] **Step 1: Build a deterministic end-to-end fixture**

Use one legacy population Raw without source fields, one new `CollectedPayload` with explicit `source_url`, and one multi-source analytics fixture. Run pipeline transform, published snapshot, and pure DynamoDB projection in a temporary directory.

- [x] **Step 2: Assert the acceptance contract**

Verify:

```text
legacy Raw bytes unchanged
new Raw has source/source_url/source_url_type
curated records have source/source_url
manifest.sources is present
direct metric has sourceName/sourceUrl
derived metric has sourceRefs and null sourceUrl
DynamoDB PK/SK are unchanged
published snapshot has no raw_records
```

- [x] **Step 3: Run the complete local verification**

Run:

```bash
cd data-pipeline
.venv/bin/python -m pytest -q
cd ..
npm --workspace @newtaipei-youth/shared run build
npm --workspace @newtaipei-youth/backend run test
npm --workspace @newtaipei-youth/backend run build
```

If Backend has not yet been implemented, report that the last two commands are a handoff gate and keep the Python/published/projection checks as the completed evidence; do not replace them with mock success claims.

Observed handoff result: `npm --workspace @newtaipei-youth/backend run test`
and `run build` both report `Missing script`; Python and shared TypeScript
verification pass.

- [x] **Step 4: Record the migration decision**

Report that existing Raw does not need to be re-uploaded. Historical records become source-aware when replayed/reprocessed; only new Raw writes the normalized envelope fields. Any source that cannot be proven remains `null` and is surfaced in quality output.

## Review Checklist

- [x] No task overwrites historical Raw or changes S3 object metadata in place.
- [x] All source IDs emitted by current transforms have registry entries or an explicit unresolved quality result.
- [x] Source URL is never invented from an unverified path.
- [x] Derived metrics do not claim a single official source when they combine multiple datasets.
- [x] Local JSON and DynamoDB use the same published snapshot ID and response fields.
- [x] No AWS deployment, Scheduler change, or commit is performed in this execution.
