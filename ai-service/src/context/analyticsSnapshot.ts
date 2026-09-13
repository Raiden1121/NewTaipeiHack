import { readFile } from 'node:fs/promises';
import path from 'node:path';

/**
 * 讀取 data-pipeline 的 **Deterministic Analytics published snapshot**。
 *
 * 這是架構圖上 `Deterministic Analytics → DynamoDB / AI Context → AI Service` 這條線
 * 目前真正存在的形式：analytics 算完之後不是寫進 `dataset_index.json`（那份只收 11 個
 * curated dataset），而是發布成一個帶版本的快照目錄。
 *
 * ```text
 * data-pipeline/data/analytics/
 * ├── published/
 * │   ├── current.json                    ← {"snapshot_id": "dev-full-20260912"}
 * │   └── dev-full-20260912/
 * │       ├── manifest.json               ← artifacts 清單、上游期間、warnings
 * │       ├── dashboard_overview.json     ← 29 區指標 + 全市 KPI + 年度趨勢
 * │       ├── district_details.json       ← 與 dashboard_overview 的 districts 重複
 * │       └── analyses/
 * │           ├── employment.json
 * │           ├── fertility.json
 * │           ├── participation.json
 * │           ├── policy_support.json
 * │           ├── topic_weight.json
 * │           └── keyword_frequency.json
 * ```
 *
 * **一律透過 `current.json` 決定要讀哪個快照，不自己 glob `published/` 目錄。**
 * 理由跟 curated 那邊只讀 `dataset_index.json` 一樣：目錄裡同時存在
 * `dev-employment-20260911`、`dev-fertility-20260912`、`dev-full-20260912` 等多個
 * 部分快照（只跑單一分析時產生的）。用「檔名排序取最後」會抽到
 * `dev-youth-participation-20260911` 這種只有一個分析的快照，於是 AI 會拿到
 * 殘缺的資料卻毫不知情。`current.json` 是 pipeline 明確宣告的 authoritative 指標。
 */

/** `published/current.json` 的形狀。 */
interface CurrentSnapshotPointer {
  snapshot_id?: unknown;
}

/** manifest 裡一個 artifact 的參照。 */
export interface AnalyticsArtifactRef {
  /**
   * artifact 的識別名稱。`dashboard_overview` 或 `analyses` 底下的分析名稱
   * （employment / fertility / participation / policy_support / …）。
   * 這個值會成為 evidence 的 dataset 名稱（加上 `analytics_` 前綴）。
   */
  key: string;
  /** 相對於 dataDir 的路徑，會成為 evidence 的 sourcePath，可直接回頭開檔查證。 */
  sourcePath: string;
  /** 絕對路徑，實際讀檔用。 */
  absolutePath: string;
}

export interface AnalyticsSnapshot {
  snapshotId: string;
  /** manifest 的 `generated_at`，ISO 8601。會成為 evidence 的 fetchedAt。 */
  generatedAt: string | null;
  /** manifest 的 `as_of`；真實資料裡目前是 null。 */
  asOf: string | null;
  schemaVersion: number | null;
  artifacts: AnalyticsArtifactRef[];
  /**
   * manifest 頂層的 `warnings`，例如 `incomplete_village_population_coverage`。
   *
   * 這些必須一路帶到輸出的 limitations —— 它們是 pipeline 自己宣告「這份快照有已知
   * 缺陷」，如果 AI 拿著資料卻不知道有缺陷，就會把 partial 的數字當成完整的講。
   */
  warnings: string[];
  /** manifest `datasets[]` 收錄的上游 curated dataset 名稱，用在 computation 說明裡。 */
  upstreamDatasets: string[];
}

/**
 * `district_details.json` 刻意不讀。
 *
 * 實測確認它的 `districts[].metrics{}` 與 `dashboard_overview.json` 的 `districts[]`
 * 是同一組欄位、同一批數值。兩份都讀的後果不只是浪費 token：模型會看到同一個數字
 * 出現在兩個不同的 evidenceId 上，於是可以「用兩筆 evidence 互相佐證」一個其實只有
 * 單一來源的結論。那是製造出來的可信度。
 */
export const SKIPPED_ARTIFACT_KEYS: readonly string[] = ['district_details'];

/** analytics 目錄相對於 data-pipeline 輸出根目錄的位置。 */
const ANALYTICS_DIR = 'analytics';
const PUBLISHED_DIR = 'published';

/**
 * 讀 `published/current.json` 取得目前 authoritative 的 snapshot id。
 *
 * 找不到檔案時丟錯並附上產生資料的指令 —— 這跟 `readDatasetIndex()` 的處理一致：
 * 「還沒跑過 pipeline」是本機開發最常見的失敗，錯誤訊息要能直接告訴人怎麼修。
 */
export async function readCurrentSnapshotId(dataDir: string): Promise<string> {
  const pointerPath = path.join(dataDir, ANALYTICS_DIR, PUBLISHED_DIR, 'current.json');
  let raw: string;
  try {
    raw = await readFile(pointerPath, 'utf-8');
  } catch (error) {
    throw new Error(
      `讀不到 analytics published/current.json：${pointerPath}。` +
        '請先在 data-pipeline 產生並發布 analytics 快照' +
        `（原始錯誤：${error instanceof Error ? error.message : String(error)}）`,
    );
  }

  const parsed = JSON.parse(raw) as CurrentSnapshotPointer;
  const snapshotId = typeof parsed?.snapshot_id === 'string' ? parsed.snapshot_id.trim() : '';
  if (snapshotId.length === 0) {
    throw new Error(`published/current.json 缺少 snapshot_id 字串：${pointerPath}`);
  }
  return snapshotId;
}

/**
 * 讀出一個 snapshot 的 manifest 與 artifact 清單。
 *
 * `snapshotId` 省略時用 `current.json` 指定的。明確指定的用途是回溯比較
 * （例如想確認某個結論是在哪個快照下產生的）。
 */
export async function readAnalyticsSnapshot(
  dataDir: string,
  snapshotId?: string,
): Promise<AnalyticsSnapshot> {
  const resolvedId = snapshotId ?? (await readCurrentSnapshotId(dataDir));
  const manifestPath = path.join(dataDir, ANALYTICS_DIR, PUBLISHED_DIR, resolvedId, 'manifest.json');

  let raw: string;
  try {
    raw = await readFile(manifestPath, 'utf-8');
  } catch (error) {
    throw new Error(
      `讀不到 analytics snapshot manifest：${manifestPath}。` +
        `current.json 指向 snapshot_id="${resolvedId}"，但該目錄下沒有 manifest.json` +
        `（原始錯誤：${error instanceof Error ? error.message : String(error)}）`,
    );
  }

  const parsed: unknown = JSON.parse(raw);
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`manifest.json 外層必須是物件：${manifestPath}`);
  }
  return parseAnalyticsManifest(parsed as Record<string, unknown>, dataDir, resolvedId);
}

/**
 * 把 manifest 物件轉成 `AnalyticsSnapshot`。
 *
 * 從 `readAnalyticsSnapshot` 拆出來，讓 `DynamoEvidenceRepository` 用同一份規則解析
 * 表裡存的 manifest —— artifact 清單、`SKIPPED_ARTIFACT_KEYS`、sourcePath 格式
 * 只要有一處不同，兩種來源的 evidence 就會分岔。
 *
 * `resolvedId` 決定 sourcePath 的快照目錄名；`dataDir` 只影響 `absolutePath`。
 */
export function parseAnalyticsManifest(
  manifest: Record<string, unknown>,
  dataDir: string,
  resolvedId: string,
): AnalyticsSnapshot {
  const snapshotRelativeDir = path.posix.join(ANALYTICS_DIR, PUBLISHED_DIR, resolvedId);
  return {
    snapshotId: asString(manifest.snapshot_id) ?? resolvedId,
    generatedAt: asString(manifest.generated_at),
    asOf: asString(manifest.as_of),
    schemaVersion: typeof manifest.schema_version === 'number' ? manifest.schema_version : null,
    artifacts: collectArtifacts(manifest.artifacts, dataDir, snapshotRelativeDir),
    warnings: asStringArray(manifest.warnings),
    upstreamDatasets: collectUpstreamDatasets(manifest.datasets),
  };
}

/**
 * 從 manifest 的 `artifacts` 組出 artifact 清單。
 *
 * 形狀是 `{ dashboard_overview: "dashboard_overview.json", district_details: "...",
 * analyses: { employment: "analyses/employment.json", ... } }`：頂層是字串值，
 * `analyses` 是巢狀一層的物件。
 *
 * **只採用 manifest 明確列出的 artifact。** 不去掃 `analyses/` 目錄 —— 目錄裡可能
 * 留著上一次發布的殘檔，而 manifest 才是這個快照宣告過的內容。
 */
function collectArtifacts(
  artifacts: unknown,
  dataDir: string,
  snapshotRelativeDir: string,
): AnalyticsArtifactRef[] {
  if (artifacts === null || typeof artifacts !== 'object' || Array.isArray(artifacts)) {
    return [];
  }

  const refs: AnalyticsArtifactRef[] = [];
  const push = (key: string, relativePath: unknown): void => {
    if (typeof relativePath !== 'string' || relativePath.length === 0) {
      return;
    }
    if (SKIPPED_ARTIFACT_KEYS.includes(key)) {
      return;
    }
    const sourcePath = path.posix.join(snapshotRelativeDir, toPosix(relativePath));
    refs.push({
      key,
      sourcePath,
      absolutePath: path.join(dataDir, ...sourcePath.split('/')),
    });
  };

  for (const [key, value] of Object.entries(artifacts as Record<string, unknown>)) {
    if (key === 'analyses') {
      if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
        for (const [analysisKey, analysisPath] of Object.entries(value as Record<string, unknown>)) {
          push(analysisKey, analysisPath);
        }
      }
      continue;
    }
    push(key, value);
  }
  return refs;
}

/** manifest `datasets[]` 裡的上游 dataset 名稱，去重後排序，用在 computation 說明。 */
function collectUpstreamDatasets(datasets: unknown): string[] {
  if (!Array.isArray(datasets)) {
    return [];
  }
  const names = new Set<string>();
  for (const item of datasets) {
    if (item === null || typeof item !== 'object' || Array.isArray(item)) {
      continue;
    }
    const dataset = (item as Record<string, unknown>).dataset;
    if (typeof dataset === 'string' && dataset.length > 0) {
      names.add(dataset);
    }
  }
  return [...names].sort((left, right) => left.localeCompare(right));
}

function toPosix(value: string): string {
  return value.split('\\').join('/');
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === 'string' && item.length > 0);
}
