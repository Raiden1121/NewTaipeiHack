import { readFile } from 'node:fs/promises';
import path from 'node:path';
import type { AiEvidence } from '../types/aiEvidence.js';
import { parseCuratedFile, recordToEvidence } from './curatedRecord.js';
import {
  DEFAULT_LIMIT_PER_DATASET,
  TRANSACTION_LEVEL_DATASETS,
  TRANSACTION_LEVEL_NOTE,
  applyEvidenceFilters,
  isAnalyticsDatasetName,
  summarizeQualityFlags,
  type EvidenceBundle,
  type EvidenceQuery,
  type EvidenceRepository,
} from './evidenceRepository.js';

/**
 * dataset_index.json 的單一條目。
 *
 * 形狀來自 `data-pipeline/src/transform/io.py` 的 `write_dataset_index()` ＋
 * `src/run_pipeline.py` 的 `_write_authoritative_index()`，已用真實輸出核對過：
 *
 * ```json
 * {
 *   "schema_version": 2,
 *   "datasets": {
 *     "population": [
 *       { "output_key": "11507", "path": "curated/population.json",
 *         "period_strategy": "monthly", "source_period": "11507",
 *         "transform_version": "2026-09-02.1" }
 *     ]
 *   }
 * }
 * ```
 *
 * 三個容易踩錯的地方（全部實測過）：
 * 1. `datasets` 是**物件**（key = canonical dataset 名），不是陣列。
 * 2. 路徑欄位叫 `path`，不是 `curated_path`。
 * 3. **沒有 `status` 欄位** — index 本身就只收錄這次 `status == "ok"` 且檔案存在的
 *    unit，所以「過濾 status === 'ok'」在真實資料下永遠回空陣列。
 */
export interface DatasetIndexEntry {
  /** map 的 key，讀取時補進來（entry 本身沒有這個欄位） */
  dataset: string;
  output_key: string;
  path: string;
  period_strategy: string;
  source_period: string;
  transform_version: string;
}

export interface DatasetIndex {
  schemaVersion: number | null;
  entries: DatasetIndexEntry[];
}

/**
 * 讀 data-pipeline 產出的 `data/quality/dataset_index.json`。
 *
 * 依 `data-pipeline/data-pipeline.md` 的規則：只能讀這份 index 指到的 authoritative
 * curated 檔案，不可自己 glob curated 目錄 —— 所以這個模組刻意不提供掃描目錄的 API。
 */
export async function readDatasetIndex(dataDir: string): Promise<DatasetIndex> {
  const indexPath = path.join(dataDir, 'quality', 'dataset_index.json');
  let raw: string;
  try {
    raw = await readFile(indexPath, 'utf-8');
  } catch (error) {
    throw new Error(
      `讀不到 dataset_index.json：${indexPath}。` +
        '請先在 data-pipeline 產生本機資料：' +
        'cd data-pipeline && python src/run_pipeline.py --period 11507 --output-dir data' +
        `（原始錯誤：${error instanceof Error ? error.message : String(error)}）`,
    );
  }

  const parsed: unknown = JSON.parse(raw);
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`dataset_index.json 外層必須是物件：${indexPath}`);
  }
  const envelope = parsed as Record<string, unknown>;
  const datasets = envelope.datasets;
  if (datasets === null || typeof datasets !== 'object' || Array.isArray(datasets)) {
    throw new Error(
      `dataset_index.json 的 datasets 必須是「dataset 名稱 → 條目陣列」的物件（schema_version 2）：${indexPath}`,
    );
  }

  const entries: DatasetIndexEntry[] = [];
  for (const [dataset, value] of Object.entries(datasets as Record<string, unknown>)) {
    if (!Array.isArray(value)) {
      continue;
    }
    for (const item of value) {
      if (item === null || typeof item !== 'object' || Array.isArray(item)) {
        continue;
      }
      const entry = item as Record<string, unknown>;
      const entryPath = entry.path;
      if (typeof entryPath !== 'string' || entryPath.length === 0) {
        continue;
      }
      entries.push({
        dataset,
        output_key: typeof entry.output_key === 'string' ? entry.output_key : '',
        path: entryPath,
        period_strategy: typeof entry.period_strategy === 'string' ? entry.period_strategy : '',
        source_period: typeof entry.source_period === 'string' ? entry.source_period : '',
        transform_version: typeof entry.transform_version === 'string' ? entry.transform_version : '',
      });
    }
  }

  return {
    schemaVersion: typeof envelope.schema_version === 'number' ? envelope.schema_version : null,
    entries,
  };
}

/**
 * 選出某個 dataset 要用的 index 條目。
 *
 * 指定 period 時取完全相符的 output_key；沒指定時取 output_key 字典序最大的那筆
 * （ROC 期間字串等寬，字典序等於時間序，所以就是最新一筆）。
 */
export function selectIndexEntry(
  index: DatasetIndex,
  dataset: string,
  period?: string,
): DatasetIndexEntry | null {
  const candidates = index.entries.filter((entry) => entry.dataset === dataset);
  if (candidates.length === 0) {
    return null;
  }
  if (period !== undefined) {
    return candidates.find((entry) => entry.output_key === period) ?? null;
  }
  return candidates.reduce((latest, entry) => (entry.output_key > latest.output_key ? entry : latest));
}

/**
 * 讀出單一 index 條目對應的 curated 檔案，轉成 AiEvidence[]。
 *
 * 路徑一律用 index 的 `path` **原值**去組，不自己拼 `dataset/period`。
 * 這點很重要：pipeline 有兩種輸出模式 —— 單月 full mode（`--period`）寫成平面
 * `curated/{dataset}.json`，range mode（`--start-period`/`--end-period`）寫成
 * `curated/{dataset}/{period}.json`。用 `path` 原值兩種都吃得到。
 */
export async function loadEvidenceFromCuratedFile(
  dataDir: string,
  entry: DatasetIndexEntry,
): Promise<AiEvidence[]> {
  const curatedPath = path.join(dataDir, entry.path);
  const raw = await readFile(curatedPath, 'utf-8');
  const payload = parseCuratedFile(JSON.parse(raw) as unknown, entry.path);

  const evidence: AiEvidence[] = [];
  payload.records.forEach((record, recordIndex) => {
    evidence.push(
      ...recordToEvidence(record, {
        sourcePath: entry.path,
        period: entry.output_key || entry.source_period,
        dataset: entry.dataset,
        recordIndex,
      }),
    );
  });
  return evidence;
}

/**
 * 便利函式：給 dataset 名稱，回傳該 dataset 的 evidence。
 *
 * 找不到條目時回傳空陣列，不丟錯 —— 呼叫端應該把這視為「資料不足」寫進 limitations，
 * 而不是當成系統錯誤中斷（見 `src/handlers/insufficientData.ts`）。
 */
export async function buildEvidenceForDataset(
  dataDir: string,
  dataset: string,
  period?: string,
): Promise<AiEvidence[]> {
  const index = await readDatasetIndex(dataDir);
  const entry = selectIndexEntry(index, dataset, period);
  if (entry === null) {
    return [];
  }
  return loadEvidenceFromCuratedFile(dataDir, entry);
}

/**
 * 本機開發用的 EvidenceRepository：直接讀 data-pipeline 的輸出目錄。
 *
 * 正式路徑是 DynamoDB（見 `DynamoEvidenceRepository`），但這個實作有一個
 * DynamoDB 給不了的價值：它讀的是 data-pipeline **真的產生出來的檔案**，
 * 所以能擋掉「格式對不上」這種只有接真實資料才會發現的問題。
 */
export class CuratedFileEvidenceRepository implements EvidenceRepository {
  readonly description: string;

  constructor(private readonly dataDir: string) {
    this.description = `curated-files(${dataDir})`;
  }

  async query(query: EvidenceQuery): Promise<EvidenceBundle> {
    const index = await readDatasetIndex(this.dataDir);
    const limit = query.limitPerDataset ?? DEFAULT_LIMIT_PER_DATASET;
    // `analytics_*` 是另一個 repository 的 dataset 名稱，不是 curated 缺漏。
    // 不濾掉的話會產生「dataset_index 沒有 analytics_employment 的條目」這種
    // 誤導的 limitation。
    const requested = (query.datasets ?? [...new Set(index.entries.map((entry) => entry.dataset))]).filter(
      (dataset) => !isAnalyticsDatasetName(dataset),
    );

    const evidence: AiEvidence[] = [];
    const notes: string[] = [];
    let totalMatched = 0;
    let truncated = false;

    const excluded = requested.filter((dataset) => TRANSACTION_LEVEL_DATASETS.includes(dataset));
    if (excluded.length > 0) {
      notes.push(TRANSACTION_LEVEL_NOTE);
    }
    const usable = requested.filter((dataset) => !TRANSACTION_LEVEL_DATASETS.includes(dataset));

    for (const dataset of usable) {
      const entry = selectIndexEntry(index, dataset, query.period);
      if (entry === null) {
        notes.push(
          query.period === undefined
            ? `dataset_index 沒有 ${dataset} 的條目，本次回應沒有這個資料集可引用。`
            : `dataset_index 沒有 ${dataset} 在期間 ${query.period} 的條目，本次回應沒有這個資料集可引用。`,
        );
        continue;
      }

      const all = await loadEvidenceFromCuratedFile(this.dataDir, entry);
      const matched = applyEvidenceFilters(all, query);
      totalMatched += matched.length;

      if (matched.length === 0) {
        notes.push(`${dataset}（${entry.path}）在本次篩選條件下沒有符合的資料點。`);
        continue;
      }
      if (matched.length > limit) {
        truncated = true;
        notes.push(
          `${dataset} 僅取樣 ${limit} 筆，實際符合條件共 ${matched.length} 筆；` +
            '這是為了控制 prompt 長度而截斷，不代表資料只有這麼多，也不可據此推論全體分布。',
        );
      }
      evidence.push(...matched.slice(0, limit));
    }

    notes.push(...summarizeQualityFlags(evidence));

    return { evidence, totalMatched, truncated, notes };
  }
}
