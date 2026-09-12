import {
  AgeScopeSchema,
  GeoLevelSchema,
  PeriodTypeSchema,
  YouthEligibilitySchema,
  type AgeScope,
  type AiEvidence,
  type GeoLevel,
  type PeriodType,
  type YouthEligibility,
} from '../types/aiEvidence.js';

/**
 * curated record → AiEvidence 的轉換規則。這裡是 snake_case（pipeline）→ camelCase
 * （ai-service）唯一的轉換點（決策 B）。
 *
 * 為什麼需要 dataset 專屬的 measure 對照表：
 * 跑過 `python src/run_pipeline.py --period 11507` 之後實測 11 個 dataset，只有
 * population / movement / vt_courses / youth_budgets 這 4 個會填 `metric_id` 與
 * `value`；其餘 7 個 dataset 的 `metric_id` 與 `value` **全部是 null**，真正的數字
 * 放在 dataset 專屬欄位裡（job_vacancies 的 position_count、house_prices 的
 * total_price、training_numbers 的 training_people…）。
 *
 * 所以「通用地讀 record.value」在真實資料下會產出一堆 value=null 的空 evidence。
 * 下面的對照表把每個寬表 dataset 明確列出來，欄位名就是 metricId，單位取同名的
 * `*_unit` 欄位。**這只是選欄位，沒有任何計算**——不做平均、中位數、YoY，
 * 那些屬於 data-pipeline 的 `analytics/`（見決策 A）。
 */
export interface MeasureFieldSpec {
  /** curated record 上的數值欄位名，會直接成為 evidence 的 metricId */
  field: string;
  /** 單位欄位名（record 上同名的 `*_unit`）；沒有就留空 */
  unitField?: string;
  /** 沒有 unitField 時使用的固定單位 */
  unit?: string;
}

/**
 * 寬表 dataset 的數值欄位對照表。key 是 canonical dataset 名稱。
 * 沒列在這裡、且 record 也沒有 `metric_id` 的 dataset，會產出 0 筆 evidence 並
 * 在 bundle 的 notes 裡回報，不會靜默變成 value=null。
 */
export const MEASURE_FIELDS_BY_DATASET: Readonly<Record<string, readonly MeasureFieldSpec[]>> = {
  job_vacancies: [
    { field: 'position_count', unitField: 'position_count_unit' },
    { field: 'salary_lower', unitField: 'salary_unit' },
    { field: 'salary_upper', unitField: 'salary_unit' },
    { field: 'salary_midpoint', unitField: 'salary_unit' },
  ],
  job_vacancy_salaries: [
    { field: 'position_count', unitField: 'position_count_unit' },
    { field: 'salary_lower', unitField: 'salary_unit' },
    { field: 'salary_upper', unitField: 'salary_unit' },
    { field: 'salary_midpoint', unitField: 'salary_unit' },
  ],
  house_prices: [
    { field: 'total_price', unitField: 'total_price_unit' },
    { field: 'price_per_ping', unitField: 'price_per_ping_unit' },
    { field: 'price_per_sqm', unitField: 'price_per_sqm_unit' },
    { field: 'building_area', unitField: 'building_area_unit' },
  ],
  rentals: [
    { field: 'rent_total', unitField: 'rent_total_unit' },
    { field: 'rent_per_ping', unitField: 'rent_per_ping_unit' },
    { field: 'rent_per_sqm', unitField: 'rent_per_sqm_unit' },
    { field: 'building_area', unitField: 'building_area_unit' },
  ],
  training_numbers: [
    { field: 'training_people', unitField: 'training_people_unit' },
    { field: 'training_hours', unitField: 'training_hours_unit' },
    { field: 'fee_per_person', unitField: 'fee_per_person_unit' },
  ],
  babysitting_places: [{ field: 'capacity', unitField: 'capacity_unit' }],
  talent_demand: [
    { field: 'new_demand_count', unitField: 'count_unit' },
    { field: 'new_hired_count', unitField: 'count_unit' },
    { field: 'valid_hired_count', unitField: 'count_unit' },
  ],
};

/**
 * curated record 上絕對不可以進入 prompt 的欄位。
 *
 * `raw_record` / `raw_records` 是原始來源整包（job_vacancies 一筆就含完整職缺描述），
 * `source_record_ids` 在 population 一筆裡有上千個 ID，`course_ids` 同理。
 * 這些東西進 prompt 只會爆 token 並讓模型看到未清理的原始欄位。
 *
 * 目前的轉換是白名單式（只讀明確指定的欄位），所以這份黑名單是第二層保險，
 * 用在把整筆 record 攤平的除錯路徑上。
 */
export const EXCLUDED_RECORD_FIELDS: readonly string[] = [
  'raw_record',
  'raw_records',
  'source_record_ids',
  'course_ids',
];

/**
 * 可以從 `raw_record` 裡撈出來當 `sourceUrl` 的欄位白名單。
 *
 * 這是對上面那條黑名單的**刻意窄例外**。理由：每個回應都必須附資料來源，而能點進去
 * 的連結遠勝過只有機關名稱；但這些連結偏偏只存在 `raw_record` 裡（實測確認：
 * youth_budgets 的 `source_document_url` / `source_pdf_url`、job_vacancies 的
 * `URL_QUERY（職缺資料URL）`）。
 *
 * 例外的範圍嚴格限制成：只取這幾個具名欄位、只取字串、只在值看起來是 http(s) 網址時採用。
 * 不是把 raw_record 打開來隨便找 —— 那就等於黑名單失效。
 */
const SOURCE_URL_FIELDS: readonly string[] = [
  'source_document_url',
  'source_pdf_url',
  'source_url',
  'URL_QUERY（職缺資料URL）',
];

export interface CuratedFilePayload {
  dataset: string;
  generated_at?: string;
  /** 只有 range mode（`--start-period`/`--end-period`）才有 */
  period?: string;
  records: Record<string, unknown>[];
}

export interface RecordToEvidenceOptions {
  /** dataset_index 的 `path` 原值，會成為 evidence 的 sourcePath */
  sourcePath: string;
  /** dataset_index 的 `output_key`，會成為 evidence 的 period */
  period: string;
  /** canonical dataset 名稱（dataset_index 的 map key） */
  dataset: string;
  /** 同一批轉換裡的序號，用來組出穩定的 evidenceId */
  recordIndex: number;
}

/**
 * 把一筆 curated record 轉成 0..n 筆 AiEvidence。
 *
 * - record 有 `metric_id` 且 `value` 不是 null → 1 筆 evidence（metricSource='metric_id'）
 * - 否則查 MEASURE_FIELDS_BY_DATASET，每個有值的數值欄位各產 1 筆
 *   （metricSource='record_field'）
 * - 都對不上 → 回傳空陣列，由呼叫端回報「這個 dataset 沒有可引用的數值欄位」
 */
export function recordToEvidence(
  record: Record<string, unknown>,
  options: RecordToEvidenceOptions,
): AiEvidence[] {
  const common = {
    dataset: asString(record.dataset) ?? options.dataset,
    source: asString(record.source),
    sourceRecordId: asString(record.source_record_id),
    geoLevel: asEnum<GeoLevel>(record.geo_level, GeoLevelSchema.options),
    districtId: asString(record.district_id),
    districtName: asString(record.district_name),
    period: options.period,
    periodStart: asString(record.period_start),
    periodEnd: asString(record.period_end),
    periodType: asEnum<PeriodType>(record.period_type, PeriodTypeSchema.options),
    ageScope: asEnum<AgeScope>(record.age_scope, AgeScopeSchema.options),
    youthEligibility: asEnum<YouthEligibility>(record.youth_eligibility, YouthEligibilitySchema.options),
    qualityFlags: asStringArray(record.quality_flags),
    sourcePath: options.sourcePath,
    fetchedAt: asString(record.fetched_at),
    sourceUrl: extractSourceUrl(record),
    // curated 的資料全部來自政府開放資料集；'web' 目前沒有產生者。
    sourceKind: 'dataset' as const,
    // curated 是照抄來源端的原始數字，沒有經過任何計算，所以沒有算法可以交代。
    // 只有 analytics 彙總出來的複合指標才會填這個欄位（見 analyticsRecord.ts）。
    computation: null,
  };

  const metricId = asString(record.metric_id);
  const directValue = asScalar(record.value);
  if (metricId !== null && directValue !== null) {
    return [
      {
        ...common,
        evidenceId: buildEvidenceId(options, metricId),
        metricId,
        metricSource: 'metric_id',
        value: directValue,
        unit: asString(record.unit),
      },
    ];
  }

  const specs = MEASURE_FIELDS_BY_DATASET[common.dataset] ?? [];
  const evidence: AiEvidence[] = [];
  for (const spec of specs) {
    const value = asScalar(record[spec.field]);
    if (value === null) {
      continue;
    }
    evidence.push({
      ...common,
      evidenceId: buildEvidenceId(options, spec.field),
      metricId: spec.field,
      metricSource: 'record_field',
      value,
      unit: spec.unitField ? asString(record[spec.unitField]) : (spec.unit ?? null),
    });
  }
  return evidence;
}

/**
 * evidenceId 格式：`{dataset}:{period}:{recordIndex}:{metricId}`。
 *
 * 用 recordIndex 而不是 `source_record_id`：一筆 record 可能攤成多筆 evidence
 * （例如 job_vacancies 的 position_count 與 salary_lower 共用同一個
 * source_record_id），必須加上 metricId 才唯一；同時 index 讓人可以直接回頭
 * 在 curated 檔案裡定位到第幾筆。
 */
export function buildEvidenceId(options: RecordToEvidenceOptions, metricId: string): string {
  return `${options.dataset}:${options.period}:${options.recordIndex}:${metricId}`;
}

/**
 * 解析 curated 檔案外層。
 * 形狀來自 io.py 的 `write_curated()`：`{dataset, generated_at, records, period?}`。
 */
export function parseCuratedFile(parsed: unknown, sourcePath: string): CuratedFilePayload {
  if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`curated 檔案外層必須是物件 { dataset, generated_at, records }：${sourcePath}`);
  }
  const envelope = parsed as Record<string, unknown>;
  const records = envelope.records;
  if (!Array.isArray(records)) {
    throw new Error(`curated 檔案缺少 records 陣列：${sourcePath}`);
  }
  const dataset = asString(envelope.dataset);
  if (dataset === null) {
    throw new Error(`curated 檔案缺少 dataset 欄位：${sourcePath}`);
  }
  return {
    dataset,
    generated_at: asString(envelope.generated_at) ?? undefined,
    period: asString(envelope.period) ?? undefined,
    records: records.filter(
      (record): record is Record<string, unknown> =>
        record !== null && typeof record === 'object' && !Array.isArray(record),
    ),
  };
}

/**
 * 找出這筆 record 的來源網址：先看 record 頂層，再看 `raw_record` 裡的白名單欄位。
 * 只接受 http(s) 開頭的字串，避免把「無」、「-」之類的佔位值當成網址。
 */
function extractSourceUrl(record: Record<string, unknown>): string | null {
  const fromTopLevel = pickUrl(record);
  if (fromTopLevel !== null) {
    return fromTopLevel;
  }
  const rawRecord = record.raw_record;
  if (rawRecord !== null && typeof rawRecord === 'object' && !Array.isArray(rawRecord)) {
    return pickUrl(rawRecord as Record<string, unknown>);
  }
  return null;
}

function pickUrl(source: Record<string, unknown>): string | null {
  for (const field of SOURCE_URL_FIELDS) {
    const value = source[field];
    if (typeof value === 'string' && /^https?:\/\//.test(value)) {
      return value;
    }
  }
  return null;
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

/** curated 的缺失值一律是 JSON null，不會用 0 代替，所以 null 就是「沒有這個數字」。 */
function asScalar(value: unknown): number | string | null {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.length > 0) {
    return value;
  }
  return null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function asEnum<T extends string>(value: unknown, allowed: readonly string[]): T | null {
  return typeof value === 'string' && allowed.includes(value) ? (value as T) : null;
}
