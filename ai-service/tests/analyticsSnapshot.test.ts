import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { readFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';
import {
  ANALYTICS_ARTIFACTS_BY_FOCUS_AREA,
  ANALYTICS_SOURCE_ID,
  AnalyticsSnapshotEvidenceRepository,
  CompositeEvidenceRepository,
  CuratedFileEvidenceRepository,
  DEFAULT_MAX_CONTEXT_EVIDENCE,
  SKIPPED_ARTIFACT_KEYS,
  TRANSACTION_LEVEL_NOTE,
  TRANSACTION_LEVEL_SUPERSEDED_NOTE,
  analyticsDatasetName,
  buildAiContext,
  buildAnalyticsEvidenceId,
  dedupeAnalyticsEvidence,
  flattenAnalyticsArtifact,
  isAnalyticsDatasetName,
  prioritizeEvidenceForContext,
  readAnalyticsSnapshot,
  readCurrentSnapshotId,
} from '../src/context/buildContext.js';
import { AiEvidenceSchema, evidenceScopeLabel, type AiEvidence } from '../src/types/aiEvidence.js';
import { SOURCE_REGISTRY, collectSourceAttributions } from '../src/types/sourceAttribution.js';
import { formatEvidenceForPrompt } from '../src/prompts/guardrails.js';
import { makeEvidence, makeOutput } from './helpers.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDataDir = path.join(here, 'fixtures', 'data-pipeline-data');

/**
 * 這個檔案跑的是 **analytics published snapshot 真實輸出的切片**
 * （2 個行政區，見 fixtures/README.md），不是手寫 fixture。
 *
 * 這件事在這裡比 curated 更重要：analytics 的形狀是給 dashboard 用的巢狀結構，
 * 深度到 `annual.fertility.years[].districts[].fertilityRate`，而且 7 個 artifact
 * 每個都不一樣。照想像手寫的 fixture 只會驗證我對格式的想像，不會驗證程式跟
 * pipeline 相容 —— 而通用走訪最怕的就是「靜默地什麼都沒讀到」。
 */

async function loadFixtureArtifact(key: string): Promise<{ payload: unknown; sourcePath: string }> {
  const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
  const artifact = snapshot.artifacts.find((item) => item.key === key);
  if (artifact === undefined) {
    throw new Error(`fixture 沒有 artifact ${key}`);
  }
  return {
    payload: JSON.parse(await readFile(artifact.absolutePath, 'utf-8')) as unknown,
    sourcePath: artifact.sourcePath,
  };
}

async function flattenFixture(key: string): Promise<AiEvidence[]> {
  const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
  const { payload, sourcePath } = await loadFixtureArtifact(key);
  return flattenAnalyticsArtifact(payload, {
    artifactKey: key,
    sourcePath,
    snapshotId: snapshot.snapshotId,
    generatedAt: snapshot.generatedAt,
    upstreamDatasets: snapshot.upstreamDatasets,
    availableArtifactKeys: snapshot.artifacts.map((item) => item.key),
  }).evidence;
}

describe('readAnalyticsSnapshot（真實 published snapshot 格式）', () => {
  it('經由 current.json 決定 snapshot，不是掃目錄取最後一個', async () => {
    const snapshotId = await readCurrentSnapshotId(fixtureDataDir);
    expect(snapshotId).toBe('test-snapshot');

    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    expect(snapshot.snapshotId).toBe('test-snapshot');
  });

  it('解析 artifacts，包含巢狀的 analyses 物件', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    const keys = snapshot.artifacts.map((artifact) => artifact.key);

    expect(keys).toContain('dashboard_overview');
    expect(keys).toContain('employment');
    expect(keys).toContain('fertility');
    expect(keys).toContain('participation');
    expect(keys).toContain('policy_support');
  });

  it('跳過 district_details —— 它和 dashboard_overview 的 districts 是同一批數值', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);

    // manifest 裡確實有列它（否則這個測試等於什麼都沒驗）
    const manifestPath = path.join(
      fixtureDataDir,
      'analytics',
      'published',
      'test-snapshot',
      'manifest.json',
    );
    const manifest = JSON.parse(await readFile(manifestPath, 'utf-8')) as {
      artifacts: Record<string, unknown>;
    };
    expect(manifest.artifacts).toHaveProperty('district_details');

    expect(SKIPPED_ARTIFACT_KEYS).toContain('district_details');
    expect(snapshot.artifacts.map((artifact) => artifact.key)).not.toContain('district_details');
  });

  it('sourcePath 是相對 dataDir 的路徑，可以直接回頭開檔查證', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    const employment = snapshot.artifacts.find((artifact) => artifact.key === 'employment');

    expect(employment?.sourcePath).toBe(
      'analytics/published/test-snapshot/analyses/employment.json',
    );
    await expect(readFile(employment!.absolutePath, 'utf-8')).resolves.toBeTruthy();
  });

  it('帶出 manifest 的 warnings 與上游 dataset', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);

    expect(snapshot.warnings).toContain('incomplete_village_population_coverage');
    expect(snapshot.upstreamDatasets.length).toBeGreaterThan(0);
    expect(snapshot.generatedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it('current.json 不存在時，錯誤訊息要說得出怎麼修', async () => {
    await expect(readCurrentSnapshotId(path.join(here, 'fixtures', 'does-not-exist'))).rejects.toThrow(
      /current\.json/,
    );
  });

  it('指定不存在的 snapshotId 時明確報錯，不是靜默回空', async () => {
    await expect(readAnalyticsSnapshot(fixtureDataDir, 'no-such-snapshot')).rejects.toThrow(
      /manifest\.json/,
    );
  });
});

describe('flattenAnalyticsArtifact（真實巢狀結構）', () => {
  it('讀到 dashboard_overview 的行政區複合指標，值與 api_contract 一致', async () => {
    const evidence = await flattenFixture('dashboard_overview');
    const yoi = evidence.find(
      (item) => item.metricId === 'opportunityIndex' && item.districtName === '板橋區',
    );

    expect(yoi).toBeDefined();
    expect(yoi?.value).toBeCloseTo(45.257169, 5);
    expect(yoi?.unit).toBe('分(0-100)');
    expect(yoi?.metricSource).toBe('analytics_metric');
    expect(yoi?.geoLevel).toBe('district');
    expect(yoi?.districtId).toBe('65000010');
  });

  it('原始指標帶正確單位（單位混用是實測踩過的錯）', async () => {
    const evidence = await flattenFixture('dashboard_overview');
    const byId = (metricId: string) =>
      evidence.find((item) => item.metricId === metricId && item.districtName === '板橋區');

    expect(byId('youth_18_35_total')?.value).toBe(107970);
    expect(byId('youth_18_35_total')?.unit).toBe('人');
    expect(byId('salary_median')?.unit).toBe('TWD/月');
    expect(byId('house_price_median')?.unit).toBe('TWD/坪');
    expect(byId('fertilityRate')?.unit).toBe('‰');
    // api_contract.md 明確警告這個不是 %
    expect(byId('youthCandidacyRatePer100k')?.unit).toBe('人/十萬青年');
  });

  it('複合指標一定帶 computation，否則就是黑箱', async () => {
    const evidence = await flattenFixture('dashboard_overview');

    for (const item of evidence) {
      expect(item.computation).not.toBeNull();
      expect(item.computation).toContain('analytics:');
      expect(item.computation).toContain('@test-snapshot');
    }
  });

  it('computation 不含上游 dataset 清單 —— 那是每筆重複的常數，改由 snapshot note 講一次', async () => {
    const evidence = await flattenFixture('dashboard_overview');

    for (const item of evidence) {
      expect(item.computation).not.toContain('upstream=');
    }
  });

  it('villages 整段排除（1032 筆村里明細不進 prompt）', async () => {
    // fixture 裡確實留著 villages，否則這個測試等於什麼都沒驗。
    const { payload } = await loadFixtureArtifact('participation');
    const serviceCoverage = (payload as { service_coverage?: { villages?: unknown[] } })
      .service_coverage;
    expect(Array.isArray(serviceCoverage?.villages)).toBe(true);
    expect(serviceCoverage!.villages!.length).toBeGreaterThan(0);

    const evidence = await flattenFixture('participation');
    expect(evidence.filter((item) => item.metricId.includes('villages'))).toHaveLength(0);
    expect(evidence.filter((item) => item.metricId.includes('village_code'))).toHaveLength(0);
  });

  it('normalizedInputs 整段排除（除錯用的標準化值會被誤讀成實際量綱）', async () => {
    const { payload } = await loadFixtureArtifact('dashboard_overview');
    const districts = (payload as { districts: Record<string, unknown>[] }).districts;
    expect(districts[0]).toHaveProperty('normalizedInputs');

    const evidence = await flattenFixture('dashboard_overview');
    expect(evidence.filter((item) => item.metricId.includes('normalizedInputs'))).toHaveLength(0);
  });

  it('scatter 的 points 排除，但 regression 保留（points 是既有指標重繪）', async () => {
    const evidence = await flattenFixture('employment');

    expect(evidence.filter((item) => item.metricId.includes('.points'))).toHaveLength(0);
    const regression = evidence.filter((item) => item.metricId.includes('regression.r_squared'));
    expect(regression.length).toBeGreaterThan(0);
    expect(typeof regression[0]?.value).toBe('number');
  });

  it('value 只會是 number / string / null，不會是物件或陣列', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    for (const artifact of snapshot.artifacts) {
      const evidence = await flattenFixture(artifact.key);
      for (const item of evidence) {
        expect(['number', 'string']).toContain(typeof item.value);
      }
    }
  });

  it('每一筆都通過 AiEvidenceSchema', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    for (const artifact of snapshot.artifacts) {
      const evidence = await flattenFixture(artifact.key);
      expect(evidence.length).toBeGreaterThan(0);
      for (const item of evidence) {
        expect(() => AiEvidenceSchema.parse(item)).not.toThrow();
      }
    }
  });

  it('以行政區代碼為 key 的物件也要補上行政區名稱（走訪機制）', async () => {
    // fixture 裡 fafi.districts 的 key 就是行政區代碼，物件內沒有 district_name。
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    const { payload, sourcePath } = await loadFixtureArtifact('fertility');
    const fafi = (payload as { fafi: { districts: Record<string, unknown> } }).fafi;
    expect(Object.keys(fafi.districts)).toContain('65000010');
    expect(fafi.districts['65000010']).not.toHaveProperty('district_name');

    // 用一個沒有規則的 artifactKey 跑，才驗得到走訪本身的行為 ——
    // 真正的 `fertility` 規則會把 fafi.districts 整段跳掉（見下一個測試）。
    const result = flattenAnalyticsArtifact(payload, {
      artifactKey: 'unruled_probe',
      sourcePath,
      snapshotId: snapshot.snapshotId,
      generatedAt: snapshot.generatedAt,
      upstreamDatasets: snapshot.upstreamDatasets,
      availableArtifactKeys: [],
    });

    const fafiScore = result.evidence.filter((item) => item.metricId === 'fafi.fafiScore');
    expect(fafiScore.length).toBeGreaterThan(0);
    // 沒補名稱的話，使用者選「板橋區」時這些分數會被 applyEvidenceFilters 整批濾掉。
    for (const item of fafiScore) {
      expect(item.geoLevel).toBe('district');
      expect(item.districtName).not.toBeNull();
      expect(KNOWN_DISTRICTS).toContain(item.districtName);
    }
  });

  it('fafi.districts 在 fertility 裡被跳過（與 districts[] 是同一組分數）', async () => {
    const evidence = await flattenFixture('fertility');

    // districts[] 上的版本保留
    const onDistricts = evidence.filter((item) => item.metricId === 'fafiScore');
    expect(onDistricts.length).toBeGreaterThan(0);
    expect(onDistricts.every((item) => item.districtName !== null)).toBe(true);

    // fafi.districts 的重排版本整段不進 evidence
    expect(evidence.filter((item) => item.metricId.startsWith('fafi.'))).toHaveLength(0);
  });

  it('議題與關鍵詞把標籤帶進 metricId，否則 100 個 weight 分不出誰是誰', async () => {
    const topics = await flattenFixture('topic_weight');
    const labelled = topics.filter((item) => item.metricId.startsWith('topics.weight#'));

    expect(labelled.length).toBeGreaterThan(0);
    expect(new Set(labelled.map((item) => item.metricId)).size).toBe(labelled.length);

    const keywords = await flattenFixture('keyword_frequency');
    expect(keywords.filter((item) => item.metricId.startsWith('keywords.weight#')).length).toBeGreaterThan(
      0,
    );
  });

  it('topic_weight / keyword_frequency 只取最新一年，且套用筆數上限', async () => {
    const { payload } = await loadFixtureArtifact('keyword_frequency');
    const years = (payload as { years: { year_roc: number }[] }).years;
    expect(years.length).toBeGreaterThan(1);
    const latest = Math.max(...years.map((year) => year.year_roc));

    const keywords = await flattenFixture('keyword_frequency');
    expect(new Set(keywords.map((item) => item.period))).toEqual(new Set([String(latest)]));
    // fieldAllowlist 只留 weight / term_frequency / document_count
    const leaves = new Set(
      keywords.map((item) => (item.metricId.split('#')[0] ?? '').split('.').pop()),
    );
    expect(leaves).toEqual(new Set(['weight', 'term_frequency', 'document_count']));
  });

  it('pipeline 宣告的品質問題變成 notes，不是變成可引用的 evidence', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    const { payload, sourcePath } = await loadFixtureArtifact('participation');
    const result = flattenAnalyticsArtifact(payload, {
      artifactKey: 'participation',
      sourcePath,
      snapshotId: snapshot.snapshotId,
      generatedAt: snapshot.generatedAt,
      upstreamDatasets: snapshot.upstreamDatasets,
      availableArtifactKeys: snapshot.artifacts.map((item) => item.key),
    });

    expect(result.notes.length).toBeGreaterThan(0);
    expect(result.notes.some((note) => note.includes('partial'))).toBe(true);
    // blocking_reasons / proxy_usage 不該變成 evidence
    expect(result.evidence.filter((item) => item.metricId.includes('blocking_reasons'))).toHaveLength(0);
    expect(result.evidence.filter((item) => item.metricId.includes('proxy_usage'))).toHaveLength(0);
  });

  it('選區層級的市議員資料不納入（選區與 29 行政區不對應）', async () => {
    const { payload } = await loadFixtureArtifact('participation');
    const t1 = (
      payload as {
        elections: { youth_candidacy: { city_councilor_t1?: unknown[] } };
      }
    ).elections.youth_candidacy.city_councilor_t1;
    expect(Array.isArray(t1)).toBe(true);
    expect(t1!.length).toBeGreaterThan(0);

    const evidence = await flattenFixture('participation');
    expect(evidence.filter((item) => item.metricId.includes('city_councilor_t1.'))).toHaveLength(0);
    // 全市合計版本仍然保留
    expect(
      evidence.filter((item) => item.metricId.includes('city_councilor_t1_citywide')).length,
    ).toBeGreaterThan(0);
  });

  it('布林值不產生 evidence（resolved=true 引用起來沒有意義）', async () => {
    const evidence = await flattenFixture('topic_weight');
    for (const item of evidence) {
      expect(item.value).not.toBe(true);
      expect(item.value).not.toBe(false);
    }
  });

  /**
   * 這一組是真模型實測踩到的：evidenceId 原本含一個走訪順序的流水號，
   * Policy Copilot 引用 `...:2:kpis.cityYouthPopulationYoY` 但正確的流水號是 3 ——
   * **指標名對、流水號差一**，於是 runFeature 判定引用了不存在的 evidenceId，
   * 整份分析被拒絕。流水號對模型沒有意義，它只能照抄，抄錯一位就作廢。
   */
  it('evidenceId 的每一段都能從 prompt 看得見的欄位重組出來', async () => {
    const evidence = await flattenFixture('dashboard_overview');
    const prompt = formatEvidenceForPrompt(evidence.slice(0, 40));

    for (const item of evidence.slice(0, 40)) {
      const scope = evidenceScopeLabel(item.districtName, item.geoLevel);
      expect(item.evidenceId).toBe(`${item.dataset}:${item.period}:${scope}:${item.metricId}`);
      // prompt 上真的看得到這四段
      expect(prompt).toContain(`dataset=${item.dataset}`);
      expect(prompt).toContain(`scope=${scope}`);
    }
  });

  it('evidenceId 不含無意義的流水號', async () => {
    const evidence = await flattenFixture('dashboard_overview');
    const yoi = evidence.find(
      (item) => item.metricId === 'opportunityIndex' && item.districtName === '板橋區',
    );

    expect(yoi?.evidenceId).toBe(
      'analytics_dashboard_overview:snapshot:test-snapshot:板橋區:opportunityIndex',
    );
  });

  it('evidenceId 必須唯一，碰撞時補上決定性的後綴', () => {
    const used = new Set<string>();
    const parts = {
      dataset: 'analytics_x',
      period: '114',
      scope: '板橋區',
      metricId: 'someMetric',
    };

    expect(buildAnalyticsEvidenceId(used, parts)).toBe('analytics_x:114:板橋區:someMetric');
    expect(buildAnalyticsEvidenceId(used, parts)).toBe('analytics_x:114:板橋區:someMetric~2');
    expect(buildAnalyticsEvidenceId(used, parts)).toBe('analytics_x:114:板橋區:someMetric~3');
  });

  it('真實快照裡沒有重複的 evidenceId', async () => {
    const snapshot = await readAnalyticsSnapshot(fixtureDataDir);
    for (const artifact of snapshot.artifacts) {
      const evidence = await flattenFixture(artifact.key);
      const ids = evidence.map((item) => item.evidenceId);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it('source 一律是 analytics 的來源識別碼，而且 registry 查得到', async () => {
    const evidence = await flattenFixture('dashboard_overview');

    for (const item of evidence) {
      expect(item.source).toBe(ANALYTICS_SOURCE_ID);
    }
    expect(SOURCE_REGISTRY[ANALYTICS_SOURCE_ID]).toBeDefined();
    // 這些是本專案算的，不是機關發布的官方統計，標註必須說清楚。
    expect(SOURCE_REGISTRY[ANALYTICS_SOURCE_ID]?.organization).toContain('非官方');
  });
});

const KNOWN_DISTRICTS = ['板橋區', '三重區'];

describe('dedupeAnalyticsEvidence', () => {
  it('同區同期同值同指標名只留一筆', () => {
    const base = makeEvidence({
      metricSource: 'analytics_metric',
      period: 'snapshot:test',
      metricId: 'opportunityIndex',
      value: 45.25,
      unit: '分(0-100)',
      computation: 'analytics:dashboard_overview.districts.opportunityIndex @test',
    });
    const duplicate = makeEvidence({
      ...base,
      evidenceId: 'analytics_employment:snapshot:test:0:opportunityIndex',
      dataset: 'analytics_employment',
      computation: 'analytics:employment.districts.opportunityIndex @test',
    });

    const result = dedupeAnalyticsEvidence([base, duplicate]);

    expect(result.evidence).toHaveLength(1);
    expect(result.removed).toBe(1);
    expect(result.evidence[0]?.dataset).toBe('population');
  });

  it('不同期間的同一指標不會被收合（那是趨勢，不是重複）', () => {
    const y113 = makeEvidence({ metricId: 'fertilityRate', period: '113', value: 26.3 });
    const y114 = makeEvidence({ metricId: 'fertilityRate', period: '114', value: 24.4 });

    expect(dedupeAnalyticsEvidence([y113, y114]).evidence).toHaveLength(2);
  });

  it('不同行政區的同一數值不會被收合', () => {
    const banqiao = makeEvidence({ metricId: 'vt_course_count', districtId: '65000010', value: 32 });
    const sanchong = makeEvidence({
      metricId: 'vt_course_count',
      districtId: '65000020',
      districtName: '三重區',
      value: 32,
    });

    expect(dedupeAnalyticsEvidence([banqiao, sanchong]).evidence).toHaveLength(2);
  });

  it('真實資料下同一個 opportunityIndex 不會出現兩次', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ districtNames: ['板橋區'] });

    const yoi = bundle.evidence.filter(
      (item) => item.metricId === 'opportunityIndex' && item.districtName === '板橋區',
    );
    expect(yoi).toHaveLength(1);
  });
});

describe('AnalyticsSnapshotEvidenceRepository', () => {
  it('回傳彙總指標，並在 notes 第一句界定它們不是官方統計', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ districtNames: ['板橋區'] });

    expect(bundle.evidence.length).toBeGreaterThan(0);
    expect(bundle.evidence.every((item) => item.metricSource === 'analytics_metric')).toBe(true);
    expect(bundle.notes[0]).toContain('不是任何機關發布的官方統計數字');
  });

  it('行政區篩選保留跨區脈絡（全市／機關層級不該被濾掉）', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ districtNames: ['板橋區'] });

    expect(bundle.evidence.some((item) => item.districtName === '板橋區')).toBe(true);
    expect(bundle.evidence.some((item) => item.geoLevel === 'county')).toBe(true);
    // 其他行政區要被濾掉
    expect(bundle.evidence.some((item) => item.districtName === '三重區')).toBe(false);
  });

  it('青年局預算標成 organization 而不是 county（那是機關預算，不是全市預算）', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ datasets: ['analytics_participation'] });

    const budget = bundle.evidence.filter((item) => item.metricId.startsWith('budget.'));
    expect(budget.length).toBeGreaterThan(0);
    expect(budget.every((item) => item.geoLevel === 'organization')).toBe(true);
  });

  it('focusArea 限縮讀取範圍，並說明沒讀哪些分析', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const all = await repository.query({ districtNames: ['板橋區'] });
    const scoped = await repository.query({ districtNames: ['板橋區'], focusArea: 'employment' });

    expect(scoped.evidence.length).toBeLessThan(all.evidence.length);
    expect(new Set(scoped.evidence.map((item) => item.dataset))).toEqual(
      new Set(
        ANALYTICS_ARTIFACTS_BY_FOCUS_AREA.employment.map((key) => analyticsDatasetName(key)),
      ),
    );
    expect(scoped.notes.some((note) => note.includes('未納入'))).toBe(true);
  });

  it('沒對應的 focusArea 就讀全部，並說明這件事', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ districtNames: ['板橋區'], focusArea: 'no-such-area' });

    expect(bundle.evidence.length).toBeGreaterThan(0);
    expect(bundle.notes.some((note) => note.includes('沒有對應的 analytics 範圍設定'))).toBe(true);
  });

  it('datasets 只指名 curated dataset 時不回傳 analytics 資料', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ datasets: ['population', 'job_vacancies'] });

    expect(bundle.evidence).toHaveLength(0);
  });

  it('把 snapshot 的 warnings 帶進 notes', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ districtNames: ['板橋區'] });

    expect(
      bundle.notes.some((note) => note.includes('incomplete_village_population_coverage')),
    ).toBe(true);
  });

  it('limitPerDataset 截斷時一定要說', async () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ limitPerDataset: 5 });

    expect(bundle.truncated).toBe(true);
    expect(bundle.notes.some((note) => note.includes('僅取樣 5 筆'))).toBe(true);
  });

  it('description 說得出讀的是哪個目錄', () => {
    const repository = new AnalyticsSnapshotEvidenceRepository(fixtureDataDir, 'test-snapshot');
    expect(repository.description).toContain('analytics-snapshot');
    expect(repository.description).toContain('test-snapshot');
  });
});

describe('curated repository 與 analytics dataset 名稱共存', () => {
  it('analytics_ 前綴的 dataset 名稱不會被當成 curated 缺漏', async () => {
    expect(isAnalyticsDatasetName('analytics_employment')).toBe(true);
    expect(isAnalyticsDatasetName('population')).toBe(false);

    const repository = new CuratedFileEvidenceRepository(fixtureDataDir);
    const bundle = await repository.query({ datasets: ['analytics_employment', 'population'] });

    expect(bundle.notes.some((note) => note.includes('analytics_employment'))).toBe(false);
    expect(bundle.evidence.some((item) => item.dataset === 'population')).toBe(true);
  });
});

describe('CompositeEvidenceRepository', () => {
  const composite = () =>
    new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
      new AnalyticsSnapshotEvidenceRepository(fixtureDataDir),
    ]);

  it('同時給原始資料點與彙總指標', async () => {
    const bundle = await composite().query({ districtNames: ['板橋區'] });

    expect(bundle.evidence.some((item) => item.metricSource === 'metric_id')).toBe(true);
    expect(bundle.evidence.some((item) => item.metricSource === 'analytics_metric')).toBe(true);
  });

  it('有彙總房價指標時，「居住負擔缺漏」那句限制要被換掉', async () => {
    const bundle = await composite().query({ districtNames: ['板橋區'] });

    expect(bundle.evidence.some((item) => item.metricId === 'house_price_median')).toBe(true);
    // 不換掉的話，輸出會一邊引用房價中位數、一邊宣告沒有房價資料。
    expect(bundle.notes).not.toContain(TRANSACTION_LEVEL_NOTE);
    expect(bundle.notes).toContain(TRANSACTION_LEVEL_SUPERSEDED_NOTE);
  });

  it('只有 curated 時仍然保留原本的「居住負擔缺漏」說明', async () => {
    const curatedOnly = new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
    ]);
    const bundle = await curatedOnly.query({ districtNames: ['板橋區'] });

    expect(bundle.notes).toContain(TRANSACTION_LEVEL_NOTE);
  });

  it('一個來源掛掉不會讓整個請求失敗，但一定要寫進 notes', async () => {
    const broken = new AnalyticsSnapshotEvidenceRepository(
      path.join(here, 'fixtures', 'does-not-exist'),
    );
    const bundle = await new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
      broken,
    ]).query({ districtNames: ['板橋區'] });

    expect(bundle.evidence.length).toBeGreaterThan(0);
    expect(bundle.notes.some((note) => note.includes('讀取失敗'))).toBe(true);
  });

  it('全部來源都掛掉才丟錯（「沒有資料」與「讀不到資料」是不同的意思）', async () => {
    const missing = path.join(here, 'fixtures', 'does-not-exist');
    const allBroken = new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(missing),
      new AnalyticsSnapshotEvidenceRepository(missing),
    ]);

    await expect(allBroken.query({})).rejects.toThrow(/都讀取失敗/);
  });

  it('至少要有一個 repository', () => {
    expect(() => new CompositeEvidenceRepository([])).toThrow();
  });
});

describe('prioritizeEvidenceForContext（context window 上限）', () => {
  const analytics = (index: number) =>
    makeEvidence({
      evidenceId: `analytics:${index}`,
      metricSource: 'analytics_metric',
      metricId: `metric_${index}`,
    });
  const metric = (index: number) =>
    makeEvidence({ evidenceId: `metric:${index}`, metricSource: 'metric_id' });
  const record = (index: number) =>
    makeEvidence({ evidenceId: `record:${index}`, metricSource: 'record_field' });

  it('沒超過上限時原封不動', () => {
    const evidence = [analytics(1), metric(1), record(1)];
    const result = prioritizeEvidenceForContext(evidence, 10);

    expect(result.evidence).toHaveLength(3);
    expect(result.dropped).toBe(0);
  });

  it('上限 0 或負數代表不限制', () => {
    const evidence = [analytics(1), metric(1), record(1)];
    expect(prioritizeEvidenceForContext(evidence, 0).evidence).toHaveLength(3);
    expect(prioritizeEvidenceForContext(evidence, -1).evidence).toHaveLength(3);
  });

  it('彙總指標很多時不會把 curated 整批擠掉（逐筆來源網址只存在 curated）', () => {
    const evidence = [
      ...Array.from({ length: 500 }, (_, index) => analytics(index)),
      ...Array.from({ length: 200 }, (_, index) => metric(index)),
      ...Array.from({ length: 800 }, (_, index) => record(index)),
    ];

    const result = prioritizeEvidenceForContext(evidence, 100);

    expect(result.evidence).toHaveLength(100);
    const bySource = new Map<string, number>();
    for (const item of result.evidence) {
      bySource.set(item.metricSource, (bySource.get(item.metricSource) ?? 0) + 1);
    }
    expect(bySource.get('analytics_metric')).toBe(50);
    expect(bySource.get('metric_id')).toBe(30);
    expect(bySource.get('record_field')).toBe(20);
  });

  it('某一組用不完的額度會還給其他組，不會浪費', () => {
    const evidence = [
      ...Array.from({ length: 500 }, (_, index) => analytics(index)),
      metric(1),
      record(1),
    ];

    const result = prioritizeEvidenceForContext(evidence, 100);

    expect(result.evidence).toHaveLength(100);
    expect(result.evidence.filter((item) => item.metricSource === 'analytics_metric')).toHaveLength(98);
    expect(result.evidence.filter((item) => item.metricSource === 'metric_id')).toHaveLength(1);
    expect(result.evidence.filter((item) => item.metricSource === 'record_field')).toHaveLength(1);
  });

  it('保留原本的來源順序，同樣輸入得到同樣輸出', () => {
    const evidence = [record(1), analytics(1), metric(1), analytics(2), record(2)];

    const first = prioritizeEvidenceForContext(evidence, 3);
    const second = prioritizeEvidenceForContext(evidence, 3);

    expect(first.evidence.map((item) => item.evidenceId)).toEqual(
      second.evidence.map((item) => item.evidenceId),
    );
    const ids = first.evidence.map((item) => item.evidenceId);
    expect(ids).toEqual([...ids].sort((left, right) => evidenceOrder(evidence, left) - evidenceOrder(evidence, right)));
  });

  it('回報每一組各丟了幾筆', () => {
    const evidence = [
      ...Array.from({ length: 10 }, (_, index) => analytics(index)),
      ...Array.from({ length: 10 }, (_, index) => record(index)),
    ];

    const result = prioritizeEvidenceForContext(evidence, 10);
    expect(result.dropped).toBe(10);
    expect(Object.keys(result.droppedBySource).length).toBeGreaterThan(0);
  });
});

function evidenceOrder(evidence: readonly AiEvidence[], evidenceId: string): number {
  return evidence.findIndex((item) => item.evidenceId === evidenceId);
}

describe('buildAiContext 串接 analytics（端到端）', () => {
  const composite = () =>
    new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
      new AnalyticsSnapshotEvidenceRepository(fixtureDataDir),
    ]);

  it('一個行政區的請求同時拿到原始資料與彙總指標', async () => {
    const context = await buildAiContext(composite(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
    });

    expect(context.evidence.some((item) => item.metricSource === 'analytics_metric')).toBe(true);
    expect(context.evidence.some((item) => item.metricSource !== 'analytics_metric')).toBe(true);
    expect(context.evidence.length).toBeLessThanOrEqual(DEFAULT_MAX_CONTEXT_EVIDENCE);
  });

  it('focusArea 會傳到 repository，不會在 buildAiContext 被丟掉', async () => {
    const all = await buildAiContext(composite(), { focusDistrict: '板橋區', maxEvidence: 0 });
    const scoped = await buildAiContext(composite(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      maxEvidence: 0,
    });

    const analyticsDatasets = (context: { evidence: AiEvidence[] }) =>
      new Set(
        context.evidence
          .filter((item) => item.metricSource === 'analytics_metric')
          .map((item) => item.dataset),
      );

    expect(analyticsDatasets(scoped).size).toBeLessThan(analyticsDatasets(all).size);
  });

  it('超過上限時一定在 limitations 說明省略了多少', async () => {
    const context = await buildAiContext(composite(), {
      focusDistrict: '板橋區',
      maxEvidence: 20,
    });

    expect(context.evidence).toHaveLength(20);
    expect(
      context.knownLimitations.some(
        (note) => note.includes('超過單次 context 上限') && note.includes('已省略'),
      ),
    ).toBe(true);
  });

  it('彙總指標可以被 prompt 格式化，且 computation 有出現', async () => {
    const context = await buildAiContext(composite(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
    });

    const prompt = formatEvidenceForPrompt(context.evidence);
    expect(prompt).toContain('(analytics_metric)');
    expect(prompt).toContain('computation=analytics:');
  });

  it('引用彙總指標時，來源標註查得到而且標明非官方統計', async () => {
    const context = await buildAiContext(composite(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
    });
    const yoi = context.evidence.find((item) => item.metricId === 'opportunityIndex');
    expect(yoi).toBeDefined();

    const sources = collectSourceAttributions(
      context.evidence,
      makeOutput({ basis: [{ evidenceId: yoi!.evidenceId, note: '引用機會指數' }] }),
    );

    expect(sources).toHaveLength(1);
    expect(sources[0]?.sourceId).toBe(ANALYTICS_SOURCE_ID);
    expect(sources[0]?.organization).toContain('非官方');
    expect(sources[0]?.sourcePaths[0]).toContain('analytics/published/test-snapshot');
  });
});
