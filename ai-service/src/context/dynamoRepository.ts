/**
 * 從 DynamoDB 的 AI Context / analytics 表讀 evidence。
 *
 * 這是架構圖上 `Deterministic Analytics → DynamoDB → AI Service` 的正式路徑。
 * `AnalyticsSnapshotEvidenceRepository`（讀本機發布的快照檔）是它的本機替代品，
 * 兩者產出**完全相同的 metricId 與 evidenceId**，所以切換來源不會讓預先算的
 * fingerprint 失效、也不會讓 prompt 長得不一樣。
 *
 * ## 表的形狀不是快照的鏡射
 *
 * schema 見 `infrastructure/dynamodb_schema.md`。關鍵差異：DynamoDB 存的是
 * **`api_contract.md` 實際要用的形狀**，而且刻意排除了村里層級明細
 * （`service_coverage.villages[]` 等，各約 200KB）。對 ai-service 來說這是好事 ——
 * 那些本來就在 `BLOCKED_KEYS` 裡被擋掉。
 *
 * ## 為什麼重用 `flattenAnalyticsArtifact`
 *
 * item 裡的逐區物件欄位名跟快照的 `dashboard_overview.districts[]` 幾乎一致
 * （`youth_18_35_total`、`salary_median`、`opportunityIndex`、`yoiComponents`…），
 * 所以把 item 包成快照的形狀再餵給同一個攤平函式，就能沿用：
 *
 * - `BLOCKED_KEYS` / `METADATA_KEYS`（擋掉 normalizedInputs、sourcePeriods、coverage…）
 * - `ANALYTICS_METRIC_META`（單位與青年適用性）
 * - evidenceId 格式 `{dataset}:{period}:{scope}:{metricId}`
 * - dedupe 規則與 notes
 *
 * 自己寫一套映射的話，這些行為會慢慢分岔，而分岔的症狀是「本機驗過但線上不一樣」。
 *
 * ## 一次 BatchGetItem
 *
 * 需要的 item 目前最多 13 筆，遠低於 BatchGetItem 的 100 筆上限，所以一次往返就夠。
 * 不用 Query 也不用 Scan（表沒有 GSI，schema 也刻意設計成只需要 key 查詢）。
 */
import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import { DynamoDBDocumentClient, BatchGetCommand } from '@aws-sdk/lib-dynamodb';
import type { AiEvidence } from '../types/aiEvidence.js';
import {
  DEFAULT_LIMIT_PER_DATASET,
  applyEvidenceFilters,
  describePeriodSelection,
  filterEvidenceByPeriod,
  type EvidenceBundle,
  type EvidenceQuery,
  type EvidenceRepository,
} from './evidenceRepository.js';
import {
  analyticsSnapshotNote,
  dedupeAnalyticsEvidence,
  flattenAnalyticsArtifact,
} from './analyticsRecord.js';
import { ANALYTICS_ARTIFACTS_BY_FOCUS_AREA } from './analyticsSnapshotRepository.js';

/** 表的 key。`pk`/`sk` 都是 String，見 `modules/analytics_table/main.tf`。 */
interface ItemKey {
  pk: string;
  sk: string;
}

/**
 * 一筆 DynamoDB item 要怎麼變成快照形狀。
 *
 * `wrap` 存在的理由是**讓 metricId 跟快照路徑一致**：快照裡年度人口在
 * `annual.population.years[]`，而 DynamoDB 的 `DASHBOARD/POPULATION_TREND`
 * 把它攤平成 item 根層的 `years`。不包回去的話 metricId 會變成
 * `years.people_total` 而不是 `annual.population.people_total`，
 * 於是 `ANALYTICS_METRIC_META`、關鍵字表、預先算的 fingerprint 全部對不上。
 */
interface ItemPlan {
  key: ItemKey;
  /** 對應快照的 artifact key，決定 dataset 名稱與 dedupe 規則。 */
  artifactKey: string;
  /** 把 item 內容包成快照的巢狀形狀。 */
  wrap: (item: Record<string, unknown>) => unknown;
  /** 這筆屬於哪些 focusArea（空陣列＝任何主題都讀）。 */
  focusAreas?: readonly string[];
}

const MANIFEST_KEY: ItemKey = { pk: 'META', sk: 'MANIFEST' };

/**
 * 要讀哪些 item。
 *
 * `DASHBOARD/DISTRICTS` 一定讀：它一筆就含 29 區的所有核心指標（約 86KB），
 * 同時滿足「焦點行政區」與「跨區比較」兩種需求。分開讀 `DISTRICT#<id>/SUMMARY`
 * 反而更貴 —— 那是同一份物件的副本，而跨區比較還是得再拿整包。
 */
const ITEM_PLANS: readonly ItemPlan[] = [
  {
    key: { pk: 'DASHBOARD', sk: 'DISTRICTS' },
    artifactKey: 'dashboard_overview',
    wrap: (item) => ({ districts: item.districts }),
  },
  {
    key: { pk: 'DASHBOARD', sk: 'KPIS' },
    artifactKey: 'dashboard_overview',
    wrap: (item) => ({ kpis: item.kpis, availability: item.availability }),
  },
  {
    key: { pk: 'DASHBOARD', sk: 'POPULATION_TREND' },
    artifactKey: 'dashboard_overview',
    // 包回快照的 annual.population.years[]，metricId 才會是
    // `annual.population.people_total` 而不是 `years.people_total`。
    wrap: (item) => ({ annual: { population: { years: item.years } } }),
  },
  {
    key: { pk: 'DASHBOARD', sk: 'FERTILITY_TREND' },
    artifactKey: 'dashboard_overview',
    wrap: (item) => ({ annual: { fertility: { years: item.years } } }),
  },
  {
    key: { pk: 'DASHBOARD', sk: 'SERVICE_COVERAGE' },
    artifactKey: 'dashboard_overview',
    wrap: (item) => ({ service_coverage: stripKeys(item) }),
  },
  {
    key: { pk: 'DASHBOARD', sk: 'POLICY' },
    artifactKey: 'dashboard_overview',
    wrap: (item) => ({ policy: stripKeys(item) }),
  },
  {
    key: { pk: 'DASHBOARD', sk: 'ELECTIONS' },
    artifactKey: 'dashboard_overview',
    wrap: (item) => ({ elections: stripKeys(item) }),
  },
  {
    key: { pk: 'ANALYSIS#employment-scatter', sk: 'DATA' },
    artifactKey: 'employment',
    wrap: wrapEmploymentScatter,
    focusAreas: ['employment', 'jobs', 'talent', 'housing', 'transport', 'retention'],
  },
  {
    key: { pk: 'ANALYSIS#fertility-overlay', sk: 'DATA' },
    artifactKey: 'fertility',
    wrap: (item) => ({ scatter: stripKeys(item) }),
    focusAreas: ['fertility'],
  },
  {
    key: { pk: 'ANALYSIS#fertility-family-friendliness', sk: 'DATA' },
    artifactKey: 'fertility',
    wrap: wrapFertilityFamilyFriendliness,
    focusAreas: ['fertility'],
  },
  {
    key: { pk: 'ANALYSIS#youth-keyword-frequency', sk: 'DATA' },
    artifactKey: 'keyword_frequency',
    wrap: (item) => stripKeys(item),
    focusAreas: ['resources', 'participation'],
  },
  {
    key: { pk: 'ANALYSIS#politics-resource-io', sk: 'DATA' },
    artifactKey: 'participation',
    wrap: wrapPoliticsResourceIo,
    focusAreas: ['resources', 'participation', 'policy'],
  },
  {
    key: { pk: 'ANALYSIS#policy-outcomes', sk: 'DATA' },
    artifactKey: 'policy_support',
    wrap: (item) => ({ policyOutcomes: stripKeys(item) }),
    focusAreas: ['employment', 'population', 'retention', 'policy'],
  },
];

const SCATTER_SOURCE_KEY_BY_PLOT_ID: Readonly<Record<string, string>> = {
  'knowledge-wage': 'knowledge_job_vs_estimated_wage',
  'wage-housing': 'monthly_wage_vs_house_price',
};

function wrapEmploymentScatter(item: Record<string, unknown>): unknown {
  const scatter: Record<string, unknown> = {};
  for (const plot of asRecordArray(item.plots)) {
    const id = asString(plot.id);
    const sourceKey = id === null ? undefined : SCATTER_SOURCE_KEY_BY_PLOT_ID[id];
    if (sourceKey === undefined) {
      continue;
    }
    const { id: _id, ...payload } = plot;
    scatter[sourceKey] = payload;
  }
  return {
    scatter,
    // projection 的 limitations 是 pipeline 對此 analysis 的品質說明，轉成
    // flattenAnalyticsArtifact 已知的 note 欄位，避免靜默丟失。
    warnings: item.limitations,
  };
}

function wrapFertilityFamilyFriendliness(item: Record<string, unknown>): unknown {
  return {
    // published fertility.json 的 fafi 分數同時出現在 districts[]；projection
    // 已把它整理成同樣可直接篩選的列表，因此不要包回 fafi.districts（那是
    // flattenAnalyticsArtifact 明確排除的重複形狀）。
    districts: asRecordArray(item.districts).map((row) => ({
      district_id: row.district_id,
      district_name: row.district_name,
      fafiScore: row.fafi_score,
      fafiLevel: row.fafi_level,
    })),
  };
}

function wrapPoliticsResourceIo(item: Record<string, unknown>): unknown {
  return {
    // 保留 published participation 的「預算項目」語意，並使用 projection 已轉成
    // 千元的欄位，不把 amount_thousand 誤當成原始 TWD amount。
    budget_allocation: { items: item.budget_by_department },
  };
}

/** 去掉 key 屬性，其餘照原樣。item 是 `{pk, sk, ...內容}` 的形狀。 */
function stripKeys(item: Record<string, unknown>): Record<string, unknown> {
  const { pk: _pk, sk: _sk, ...rest } = item;
  return rest;
}

export interface DynamoEvidenceRepositoryOptions {
  tableName: string;
  region?: string;
  /** 測試用：塞一個假的 document client。 */
  documentClient?: DynamoDBDocumentClient;
}

export class DynamoEvidenceRepository implements EvidenceRepository {
  readonly description: string;
  private readonly client: DynamoDBDocumentClient;
  private readonly tableName: string;

  constructor(options: DynamoEvidenceRepositoryOptions) {
    this.tableName = options.tableName;
    this.client =
      options.documentClient ??
      DynamoDBDocumentClient.from(
        new DynamoDBClient(options.region === undefined ? {} : { region: options.region }),
      );
    this.description = `dynamodb(${options.tableName})`;
  }

  async query(query: EvidenceQuery): Promise<EvidenceBundle> {
    const plans = selectPlans(query);
    const keys = [MANIFEST_KEY, ...plans.map((plan) => plan.key)];
    const items = await this.batchGet(keys);

    const manifest = items.get(keyOf(MANIFEST_KEY));
    if (manifest === undefined) {
      // 這正是 schema 文件說的「manifest 不存在就是還沒發布」。
      // 誠實回空集合＋說明，不要丟錯 —— 呼叫端會據此回「資料不足」。
      return {
        evidence: [],
        totalMatched: 0,
        truncated: false,
        notes: [
          `DynamoDB 表 ${this.tableName} 裡沒有 META/MANIFEST，` +
            '代表 data-pipeline 還沒發布任何 analytics snapshot，本次沒有可引用的資料。',
        ],
      };
    }

    const snapshotId = asString(manifest.snapshot_id) ?? '(unknown)';
    const generatedAt = asString(manifest.generated_at);
    const notes = new Set<string>();
    for (const warning of asStringArray(manifest.warnings)) {
      notes.add(`資料管線對這份快照的警告：${warning}`);
    }

    const collected: AiEvidence[] = [];
    const missing: string[] = [];
    for (const plan of plans) {
      const item = items.get(keyOf(plan.key));
      if (item === undefined) {
        missing.push(`${plan.key.pk}/${plan.key.sk}`);
        continue;
      }
      const result = flattenAnalyticsArtifact(plan.wrap(item), {
        artifactKey: plan.artifactKey,
        // 來源不是檔案，寫成表名＋key 才能回溯這個數字是從哪裡讀的。
        sourcePath: `dynamodb://${this.tableName}/${plan.key.pk}/${plan.key.sk}`,
        snapshotId,
        generatedAt,
        upstreamDatasets: asStringArray(manifest.source_datasets),
        availableArtifactKeys: uniqueArtifactKeys(plans),
      });
      collected.push(...result.evidence);
      for (const note of result.notes) {
        notes.add(note);
      }
    }
    if (missing.length > 0) {
      notes.add(
        `DynamoDB 表 ${this.tableName} 缺少這些 item：${missing.join('、')}。` +
          '相關面向本次沒有資料，不代表該面向的實際狀況。',
      );
    }

    // 跨 item 的重複收合：同一個數字在多個 item 裡各出現一次（例如逐區物件同時
    // 存在 DASHBOARD/DISTRICTS 與 DISTRICT#<id>/SUMMARY），不收合的話模型會拿
    // 兩個 evidenceId「互相佐證」同一個來源。
    const { evidence: deduped, removed } = dedupeAnalyticsEvidence(collected);
    if (removed > 0) {
      notes.add(
        `analytics 各 item 之間有 ${removed} 筆重複的指標值，已收合成單一 evidence，` +
          '避免同一個數字被當成多個獨立來源互相佐證。',
      );
    }
    notes.add(
      analyticsSnapshotNote(snapshotId, generatedAt, asStringArray(manifest.source_datasets)),
    );

    // 篩選重用快照那邊同一個函式 —— 自己寫一份的話行為會慢慢分岔，
    // 而分岔的症狀是「同一個查詢在兩種來源下拿到不同的 evidence」。
    const periodFiltered = filterEvidenceByPeriod(deduped, query.period);
    const periodNote = describePeriodSelection(periodFiltered.selectedPeriods, query.period);
    if (periodNote !== null) {
      notes.add(periodNote);
    }
    const filtered = applyEvidenceFilters(periodFiltered.evidence, query);
    const limit = query.limitPerDataset ?? DEFAULT_LIMIT_PER_DATASET;
    const truncated = filtered.length > limit;

    return {
      evidence: truncated ? filtered.slice(0, limit) : filtered,
      totalMatched: filtered.length,
      truncated,
      notes: [...notes],
    };
  }

  /**
   * BatchGetItem。刻意處理 `UnprocessedKeys`：DynamoDB 在被節流時會回傳部分結果
   * 而**不報錯**，不重試的話症狀是「有些指標時有時無」，非常難查。
   */
  private async batchGet(keys: readonly ItemKey[]): Promise<Map<string, Record<string, unknown>>> {
    const found = new Map<string, Record<string, unknown>>();
    let pending: ItemKey[] = [...keys];

    for (let attempt = 0; attempt < 3 && pending.length > 0; attempt += 1) {
      const response = await this.client.send(
        new BatchGetCommand({ RequestItems: { [this.tableName]: { Keys: pending } } }),
      );
      for (const item of response.Responses?.[this.tableName] ?? []) {
        const record = item as Record<string, unknown>;
        const pk = asString(record.pk);
        const sk = asString(record.sk);
        if (pk !== null && sk !== null) {
          found.set(keyOf({ pk, sk }), record);
        }
      }
      const unprocessed = response.UnprocessedKeys?.[this.tableName]?.Keys ?? [];
      pending = unprocessed.map((key) => ({
        pk: String(key.pk),
        sk: String(key.sk),
      }));
    }

    return found;
  }
}

function keyOf(key: ItemKey): string {
  return `${key.pk}\u0000${key.sk}`;
}

/** 依 focusArea 決定要讀哪些 item。沒指定主題就全讀。 */
export function selectPlans(query: EvidenceQuery): ItemPlan[] {
  const focusArea = query.focusArea?.trim().toLowerCase();
  if (focusArea === undefined || focusArea.length === 0) {
    return [...ITEM_PLANS];
  }
  // 主題沒有對應設定時全讀 —— 跟 analytics 快照那邊同一個保守作法：
  // 寧可多讀一點，也不要讓模型缺它需要的資料。
  if (ANALYTICS_ARTIFACTS_BY_FOCUS_AREA[focusArea] === undefined) {
    return [...ITEM_PLANS];
  }
  return ITEM_PLANS.filter(
    (plan) => plan.focusAreas === undefined || plan.focusAreas.includes(focusArea),
  );
}

function uniqueArtifactKeys(plans: readonly ItemPlan[]): string[] {
  return [...new Set(plans.map((plan) => plan.artifactKey))];
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value)
    ? value.filter(
        (item): item is Record<string, unknown> =>
          item !== null && typeof item === 'object' && !Array.isArray(item),
      )
    : [];
}
