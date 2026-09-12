import { readFile } from 'node:fs/promises';
import type { AiEvidence } from '../types/aiEvidence.js';
import {
  analyticsDatasetName,
  analyticsSnapshotNote,
  dedupeAnalyticsEvidence,
  flattenAnalyticsArtifact,
} from './analyticsRecord.js';
import { readAnalyticsSnapshot, type AnalyticsArtifactRef } from './analyticsSnapshot.js';
import {
  DEFAULT_LIMIT_PER_DATASET,
  applyEvidenceFilters,
  type EvidenceBundle,
  type EvidenceQuery,
  type EvidenceRepository,
} from './evidenceRepository.js';

/**
 * 讀 data-pipeline 的 **analytics published snapshot** 當 evidence 來源。
 *
 * 這是 `CuratedFileEvidenceRepository` 的姊妹實作，補上它拿不到的東西：
 * 已經彙總計算完成的複合指標（Youth Opportunity Index、各區房價中位數、
 * 生育率、留才風險等級、服務涵蓋率…）。
 *
 * 兩者的差別不只是檔案位置：
 *
 * | | curated | analytics |
 * |---|---|---|
 * | 內容 | 清理後的**原始**資料點 | **彙總計算後**的指標 |
 * | 形狀 | 平的 record 陣列 | 給 dashboard 用的巢狀結構 |
 * | index | `quality/dataset_index.json` | `analytics/published/current.json` |
 * | metricSource | `metric_id` / `record_field` | `analytics_metric` |
 * | 代表性 | 單筆不代表全區 | 就是全區水準，可跨區比較 |
 *
 * 為什麼這件事重要：在這個 repository 出現之前，AI 只看得到 curated 的逐筆資料，
 * 所以「板橋區的青年發展機會好不好」這個問題**根本沒有可引用的指標**——
 * 而 Youth Opportunity Index 早就算好了，只是躺在 analytics 快照裡沒人讀。
 * 同時 house_prices / rentals 因為是逐筆交易而被整組排除，居住負擔面向完全空白；
 * 現在 `house_price_median`、`rent_median`、`rent_wage_ratio` 都是彙總指標，
 * 可以正常進 context 了。
 */
export class AnalyticsSnapshotEvidenceRepository implements EvidenceRepository {
  readonly description: string;

  constructor(
    private readonly dataDir: string,
    /** 指定要讀哪個快照；省略時用 `published/current.json` 宣告的那個。 */
    private readonly snapshotId?: string,
  ) {
    this.description = `analytics-snapshot(${dataDir}${snapshotId ? `, ${snapshotId}` : ''})`;
  }

  async query(query: EvidenceQuery): Promise<EvidenceBundle> {
    const snapshot = await readAnalyticsSnapshot(this.dataDir, this.snapshotId);
    const limit = query.limitPerDataset ?? DEFAULT_LIMIT_PER_DATASET;
    const notes: string[] = [];

    const availableArtifactKeys = snapshot.artifacts.map((artifact) => artifact.key);
    const selected = selectArtifacts(snapshot.artifacts, query, notes);

    if (selected.length === 0) {
      return {
        evidence: [],
        totalMatched: 0,
        truncated: false,
        notes: [
          ...notes,
          `analytics 快照 ${snapshot.snapshotId} 在本次條件下沒有可讀的分析檔案。`,
        ],
      };
    }

    // pipeline 自己宣告的快照層級缺陷。不往上帶的話，AI 會把 partial 的資料當完整的講。
    for (const warning of snapshot.warnings) {
      notes.push(
        `analytics 快照 ${snapshot.snapshotId} 帶有警告 ${warning}，受影響的指標解讀時必須保留。`,
      );
    }

    const perDataset: AiEvidence[] = [];
    let totalMatched = 0;
    let truncated = false;

    for (const artifact of selected) {
      const payload = await readArtifact(artifact);
      const flattened = flattenAnalyticsArtifact(payload, {
        artifactKey: artifact.key,
        sourcePath: artifact.sourcePath,
        snapshotId: snapshot.snapshotId,
        generatedAt: snapshot.generatedAt,
        upstreamDatasets: snapshot.upstreamDatasets,
        availableArtifactKeys,
      });
      notes.push(...flattened.notes);

      const matched = applyEvidenceFilters(flattened.evidence, query);
      totalMatched += matched.length;

      if (matched.length === 0) {
        notes.push(
          `analytics 的 ${analyticsDatasetName(artifact.key)}（${artifact.sourcePath}）` +
            '在本次篩選條件下沒有符合的指標。',
        );
        continue;
      }
      if (matched.length > limit) {
        truncated = true;
        notes.push(
          `${analyticsDatasetName(artifact.key)} 僅取樣 ${limit} 筆，實際符合條件共 ${matched.length} 筆；` +
            '這是為了控制 prompt 長度而截斷，不代表資料只有這麼多，也不可據此推論全體分布。',
        );
      }
      perDataset.push(...matched.slice(0, limit));
    }

    // 跨 artifact 的重複收合放在最後：必須等所有 artifact 都攤平完才知道哪些重複。
    const { evidence, removed } = dedupeAnalyticsEvidence(perDataset);
    if (removed > 0) {
      notes.push(
        `analytics 各分析之間有 ${removed} 筆重複的指標值（同一個數字在多個分析裡各出現一次），` +
          '已收合成單一 evidence，避免同一個數字被當成多個獨立來源互相佐證。',
      );
    }

    if (evidence.length > 0) {
      // 這一句放在最前面：它界定了後面所有 analytics 數字的性質。
      notes.unshift(
        analyticsSnapshotNote(snapshot.snapshotId, snapshot.generatedAt, snapshot.upstreamDatasets),
      );
    }

    return { evidence, totalMatched, truncated, notes: unique(notes) };
  }
}

/**
 * 主題 → 要讀哪些 analysis artifact。
 *
 * key 是 `AiRequestContext.focusArea` 可能出現的值（`ai-service.md` 列的是
 * employment、housing、fertility、resources），value 是 manifest 的 artifact key。
 *
 * `dashboard_overview` 每個主題都在，因為 29 區的核心指標（青年人口、機會指數、
 * 留才風險）是任何主題的共同背景 —— 少了它，AI 連「這區有多少青年」都答不出來。
 */
export const ANALYTICS_ARTIFACTS_BY_FOCUS_AREA: Readonly<Record<string, readonly string[]>> = {
  employment: ['dashboard_overview', 'employment', 'policy_support'],
  jobs: ['dashboard_overview', 'employment', 'policy_support'],
  talent: ['dashboard_overview', 'employment'],
  housing: ['dashboard_overview', 'employment'],
  transport: ['dashboard_overview', 'employment'],
  population: ['dashboard_overview', 'policy_support'],
  retention: ['dashboard_overview', 'employment', 'policy_support'],
  fertility: ['dashboard_overview', 'fertility'],
  resources: ['dashboard_overview', 'participation', 'topic_weight', 'keyword_frequency'],
  participation: ['dashboard_overview', 'participation', 'topic_weight', 'keyword_frequency'],
  policy: ['dashboard_overview', 'policy_support', 'participation'],
};

/**
 * 決定這次要讀哪些 artifact。優先順序：
 *
 * 1. `query.datasets` 明確指名（可以用 `analytics_employment` 或 `employment` 兩種寫法）
 * 2. `query.focusArea` 對應的主題範圍
 * 3. 全部讀
 *
 * 第 1 順位讓呼叫端能完全控制；第 2 順位是實務上最常用的路徑；
 * 第 3 順位是「使用者問了一個跨主題的問題」，該付的成本就付。
 */
function selectArtifacts(
  artifacts: readonly AnalyticsArtifactRef[],
  query: EvidenceQuery,
  notes: string[],
): AnalyticsArtifactRef[] {
  if (query.datasets !== undefined) {
    const wanted = new Set(query.datasets);
    const selected = artifacts.filter(
      (artifact) => wanted.has(analyticsDatasetName(artifact.key)) || wanted.has(artifact.key),
    );
    // 呼叫端只指名 curated dataset（population 等）時，代表這次不想要 analytics。
    // 這種情況不該偷偷把全部 analytics 塞進去。
    return selected;
  }

  const focusArea = query.focusArea?.trim().toLowerCase();
  if (focusArea !== undefined && focusArea.length > 0) {
    const wanted = ANALYTICS_ARTIFACTS_BY_FOCUS_AREA[focusArea];
    if (wanted !== undefined) {
      const selected = artifacts.filter((artifact) => wanted.includes(artifact.key));
      if (selected.length > 0) {
        const omitted = artifacts
          .filter((artifact) => !wanted.includes(artifact.key))
          .map((artifact) => artifact.key);
        if (omitted.length > 0) {
          notes.push(
            `本次依主題「${query.focusArea}」讀取 analytics 的 ${selected.map((a) => a.key).join('、')} 分析；` +
              `未納入 ${omitted.join('、')}。若問題涉及這些面向，本次回應無法涵蓋。`,
          );
        }
        return selected;
      }
    } else {
      notes.push(
        `主題「${query.focusArea}」沒有對應的 analytics 範圍設定，本次讀取全部分析。`,
      );
    }
  }

  return [...artifacts];
}

async function readArtifact(artifact: AnalyticsArtifactRef): Promise<unknown> {
  let raw: string;
  try {
    raw = await readFile(artifact.absolutePath, 'utf-8');
  } catch (error) {
    throw new Error(
      `manifest 宣告了 artifact ${artifact.key}（${artifact.sourcePath}）但讀不到檔案：` +
        `${artifact.absolutePath}` +
        `（原始錯誤：${error instanceof Error ? error.message : String(error)}）`,
    );
  }
  return JSON.parse(raw) as unknown;
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}
