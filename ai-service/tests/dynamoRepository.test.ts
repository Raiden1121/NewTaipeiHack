import { describe, expect, it, vi } from 'vitest';
import { DynamoEvidenceRepository, selectPlans } from '../src/context/dynamoRepository.js';
import { createEvidenceRepositoryFromEnv } from '../src/context/buildContext.js';

/**
 * 假的 DynamoDBDocumentClient：只要有 `send` 就夠。
 *
 * 刻意不用 aws-sdk-client-mock 之類的套件 —— 這裡要驗的是「item 怎麼變成
 * evidence」，不是 SDK 的行為，多一個依賴只是多一個要維護的東西。
 */
function fakeClient(items: Record<string, unknown>[], options: { unprocessedOnce?: boolean } = {}) {
  let call = 0;
  const send = vi.fn(async (command: { input: { RequestItems: Record<string, { Keys: { pk: string; sk: string }[] }> } }) => {
    call += 1;
    const table = Object.keys(command.input.RequestItems)[0]!;
    const keys = command.input.RequestItems[table]!.Keys;
    const matched = items.filter((item) =>
      keys.some((key) => key.pk === item.pk && key.sk === item.sk),
    );
    // 第一次只回一半並宣告 UnprocessedKeys，用來驗證重試。
    if (options.unprocessedOnce === true && call === 1) {
      return {
        Responses: { [table]: matched.slice(0, 1) },
        UnprocessedKeys: { [table]: { Keys: keys.slice(1) } },
      };
    }
    return { Responses: { [table]: matched }, UnprocessedKeys: {} };
  });
  return { client: { send } as never, send };
}

const manifest = {
  pk: 'META',
  sk: 'MANIFEST',
  schema_version: 1,
  snapshot_id: 'dev-test-20260913',
  generated_at: '2026-09-13T00:00:00Z',
  calculation_version: 'test',
  districts_count: 2,
  warnings: ['incomplete_village_population_coverage'],
};

function district(id: string, name: string, opportunityIndex: number, salaryScore: number) {
  return {
    district_id: id,
    district_name: name,
    youth_18_35_total: 100_000,
    salary_median: 35_000,
    opportunityIndex,
    yoiComponents: { job: 70, salary: salaryScore, talent: 50, housing: 20, transport: 40 },
    retentionRiskLevel: 'low',
    // 這兩個應該被擋掉：normalizedInputs 在 BLOCKED_KEYS，qualityStatus 是狀態字串
    normalizedInputs: { salary_median: 88.8 },
    sourcePeriods: {},
  };
}

const districtsItem = {
  pk: 'DASHBOARD',
  sk: 'DISTRICTS',
  districts: [district('65000010', '板橋區', 100, 44.01), district('65000020', '三重區', 74.84, 30)],
};

const populationTrendItem = {
  pk: 'DASHBOARD',
  sk: 'POPULATION_TREND',
  years: [
    {
      year_roc: 110,
      districts: [{ district_id: '65000010', district_name: '板橋區', youth_18_35_total: 119102 }],
      city: { youth_18_35_total: 913345 },
    },
    {
      year_roc: 113,
      districts: [{ district_id: '65000010', district_name: '板橋區', youth_18_35_total: 110857 }],
      city: { youth_18_35_total: 862933 },
    },
    {
      year_roc: 114,
      districts: [{ district_id: '65000010', district_name: '板橋區', youth_18_35_total: 107970 }],
      city: { youth_18_35_total: 845938 },
    },
  ],
};

describe('DynamoEvidenceRepository', () => {
  it('把 DASHBOARD/DISTRICTS 攤平成 evidence，並保留 29 區可比的形狀', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    const ids = bundle.evidence.map((item) => item.metricId);
    expect(ids).toContain('opportunityIndex');
    expect(ids).toContain('yoiComponents.salary');
    // 兩個行政區都要在，跨區比較才成立
    const districts = new Set(bundle.evidence.map((item) => item.districtName));
    expect(districts).toContain('板橋區');
    expect(districts).toContain('三重區');
  });

  /**
   * metricId 與 evidenceId 必須跟本機快照那條路徑一致。
   * 不一致的話切換來源會讓預先算的 fingerprint 全部失效（每次 miss →
   * 即時算 50 秒 → 被 API Gateway 切斷），而且關鍵字表也會對不上指標。
   */
  it('evidenceId 用跟快照相同的格式', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });
    const item = bundle.evidence.find(
      (candidate) => candidate.metricId === 'opportunityIndex' && candidate.districtName === '板橋區',
    );

    expect(item).toBeDefined();
    expect(item!.evidenceId).toContain('dev-test-20260913');
    expect(item!.evidenceId).toContain('opportunityIndex');
    expect(item!.dataset).toContain('analytics');
  });

  it('sourcePath 指回表與 key，數字才回溯得到', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.evidence[0]!.sourcePath).toBe(
      'dynamodb://test-analytics/DASHBOARD/DISTRICTS',
    );
  });

  it('BLOCKED_KEYS 的欄位不會變成 evidence（normalizedInputs）', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.evidence.map((item) => item.metricId)).not.toContain('normalizedInputs.salary_median');
  });

  /**
   * schema 文件說得很明白：manifest 不存在就代表 pipeline 還沒發布。
   * 這種情況要誠實回空集合＋說明，**不要丟錯** —— 丟錯的話呼叫端會變成 502，
   * 而正確的行為是回「資料不足」。
   */
  it('沒有 META/MANIFEST 時回空集合與說明，不丟錯', async () => {
    const { client } = fakeClient([districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.evidence).toEqual([]);
    expect(bundle.notes.join('\n')).toContain('還沒發布');
  });

  it('manifest 的 warnings 會進 notes（必須出現在輸出的 limitations）', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(bundle.notes.join('\n')).toContain('incomplete_village_population_coverage');
  });

  it('缺少的 item 會寫進 notes，不會靜默少一個面向', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    // KPIS / POLICY 沒有塞進假資料，所以應該被列為缺少
    expect(bundle.notes.join('\n')).toContain('DASHBOARD/KPIS');
  });

  /**
   * DynamoDB 被節流時會回傳部分結果**而不報錯**。不重試的話症狀是
   * 「有些指標時有時無」，那是最難查的一種 bug。
   */
  it('UnprocessedKeys 會重試', async () => {
    const { client, send } = fakeClient([manifest, districtsItem], { unprocessedOnce: true });
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment' });

    expect(send.mock.calls.length).toBeGreaterThan(1);
    expect(bundle.evidence.length).toBeGreaterThan(0);
  });

  it('limitPerDataset 會截斷並標記 truncated', async () => {
    const { client } = fakeClient([manifest, districtsItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({ focusArea: 'employment', limitPerDataset: 2 });

    expect(bundle.evidence).toHaveLength(2);
    expect(bundle.truncated).toBe(true);
    expect(bundle.totalMatched).toBeGreaterThan(2);
  });

  it('年度 evidence 預設只取最新期，指定 period 時不混入其他年度', async () => {
    const { client } = fakeClient([manifest, districtsItem, populationTrendItem]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });
    const query = {
      districtNames: ['板橋區'],
      metricIds: ['annual.population.youth_18_35_total'],
    };

    const latest = await repo.query(query);
    expect(latest.evidence.map((item) => item.period)).toEqual(['114']);
    expect(latest.notes.join('\n')).toContain('114');

    const requested = await repo.query({ ...query, period: '113' });
    expect(requested.evidence.map((item) => item.period)).toEqual(['113']);
    expect(requested.notes.join('\n')).toContain('113');
  });

  it('讀取六類 analysis projection，並產生可回溯的 evidence', async () => {
    const analysisItems = [
      {
        pk: 'ANALYSIS#employment-scatter',
        sk: 'DATA',
        analysis_id: 'employment-scatter',
        geo_level: 'district',
        plots: [
          {
            id: 'knowledge-wage',
            title: '起薪與知識型職缺密度相關性',
            x_label: '知識型職缺比例',
            y_label: '估算起薪',
            regression: { slope: 0.8, intercept: 28.7, r_squared: 0.05, sample_size: 29 },
          },
        ],
        limitations: [],
      },
      {
        pk: 'ANALYSIS#fertility-overlay',
        sk: 'DATA',
        analysis_id: 'fertility-overlay',
        geo_level: 'district',
        regression: { slope: 0.49, intercept: 8.5, r_squared: 0.12, sample_size: 29 },
      },
      {
        pk: 'ANALYSIS#fertility-family-friendliness',
        sk: 'DATA',
        analysis_id: 'fertility-family-friendliness',
        geo_level: 'district',
        districts: [
          { district_id: '65000010', district_name: '板橋區', fafi_score: 68.6, fafi_level: 'high' },
        ],
      },
      {
        pk: 'ANALYSIS#youth-keyword-frequency',
        sk: 'DATA',
        analysis_id: 'youth-keyword-frequency',
        calculation_version: '7',
        period_scope: 'all_available',
        keywords: [{ term: '心理健康', weight: 5, term_frequency: 10 }],
      },
      {
        pk: 'ANALYSIS#politics-resource-io',
        sk: 'DATA',
        analysis_id: 'politics-resource-io',
        geo_level: 'county',
        budget_by_department: [{ label: '綜合規劃業務', amount_thousand: 38960, share_percent: 24.42 }],
      },
      {
        pk: 'ANALYSIS#policy-outcomes',
        sk: 'DATA',
        analysis_id: 'policy-outcomes',
        geo_level: 'county',
        wageTrend: [{ year_roc: 113, wage: 59.9, yoy: 4.54 }],
        currentWageGrowth: 4.54,
        currentPopGrowth: -2.55,
        desiredDirection: { wageGrowth: 'up', populationChange: 'up' },
      },
    ];
    const { client } = fakeClient([manifest, districtsItem, ...analysisItems]);
    const repo = new DynamoEvidenceRepository({ tableName: 'test-analytics', documentClient: client });

    const bundle = await repo.query({});
    const datasets = new Set(bundle.evidence.map((item) => item.dataset));
    for (const artifact of [
      'employment',
      'fertility',
      'participation',
      'policy_support',
      'keyword_frequency',
    ]) {
      expect(datasets).toContain(`analytics_${artifact}`);
    }

    expect(bundle.evidence).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          dataset: 'analytics_employment',
          metricId: 'scatter.knowledge_job_vs_estimated_wage.regression.slope',
          evidenceId: expect.stringContaining('analytics_employment:snapshot:dev-test-20260913'),
          sourcePath: 'dynamodb://test-analytics/ANALYSIS#employment-scatter/DATA',
        }),
        expect.objectContaining({
          dataset: 'analytics_fertility',
          metricId: 'scatter.regression.slope',
        }),
        expect.objectContaining({
          dataset: 'analytics_fertility',
          metricId: 'fafiScore',
          districtName: '板橋區',
        }),
        expect.objectContaining({
          dataset: 'analytics_keyword_frequency',
          metricId: 'keywords.weight#心理健康',
        }),
        expect.objectContaining({
          dataset: 'analytics_participation',
          metricId: 'budget_allocation.items.amount_thousand#綜合規劃業務',
        }),
        expect.objectContaining({
          dataset: 'analytics_policy_support',
          metricId: 'policyOutcomes.wageTrend.wage',
          period: '113',
        }),
      ]),
    );
  });
});

describe('selectPlans（依主題決定讀哪些 item）', () => {
  it('沒指定主題時全讀', () => {
    expect(selectPlans({}).length).toBeGreaterThan(3);
  });

  it('全讀時包含六類 analysis projection item', () => {
    const keys = selectPlans({}).map((plan) => `${plan.key.pk}/${plan.key.sk}`);
    expect(keys).toEqual(
      expect.arrayContaining([
        'ANALYSIS#employment-scatter/DATA',
        'ANALYSIS#fertility-overlay/DATA',
        'ANALYSIS#fertility-family-friendliness/DATA',
        'ANALYSIS#youth-keyword-frequency/DATA',
        'ANALYSIS#politics-resource-io/DATA',
        'ANALYSIS#policy-outcomes/DATA',
      ]),
    );
  });

  it('focus-area selection 以 dashboard_overview 為共同背景，analysis 依主題選取', () => {
    const keys = selectPlans({ focusArea: 'employment' }).map((plan) => `${plan.key.pk}/${plan.key.sk}`);
    expect(keys).toContain('DASHBOARD/DISTRICTS');
    expect(keys).toContain('DASHBOARD/FERTILITY_TREND');
    expect(keys).toContain('ANALYSIS#employment-scatter/DATA');
    expect(keys).toContain('ANALYSIS#policy-outcomes/DATA');
    expect(keys).not.toContain('ANALYSIS#fertility-overlay/DATA');
  });

  it('fertility 會讀生育趨勢', () => {
    const keys = selectPlans({ focusArea: 'fertility' }).map((plan) => plan.key.sk);
    expect(keys).toContain('FERTILITY_TREND');
  });

  /**
   * 主題沒有對應設定時全讀 —— 跟 analytics 快照那邊同一個保守作法：
   * 寧可多讀一點，也不要讓模型缺它需要的資料。
   */
  it('沒見過的主題全讀，不是回空的', () => {
    expect(selectPlans({ focusArea: '完全沒見過的主題' }).length).toBe(selectPlans({}).length);
  });
});

describe('createEvidenceRepositoryFromEnv 的 dynamo 模式', () => {
  it('AI_EVIDENCE_SOURCE=dynamo 需要 ANALYTICS_TABLE_NAME', () => {
    expect(() => createEvidenceRepositoryFromEnv({ AI_EVIDENCE_SOURCE: 'dynamo' })).toThrow(
      'ANALYTICS_TABLE_NAME',
    );
  });

  it('設了表名就用 DynamoDB', () => {
    const repo = createEvidenceRepositoryFromEnv({
      AI_EVIDENCE_SOURCE: 'dynamo',
      ANALYTICS_TABLE_NAME: 'newtaipei-youth-analytics',
      AWS_DEFAULT_REGION: 'us-west-2',
    });
    expect(repo.description).toBe('dynamodb(newtaipei-youth-analytics)');
  });

  it('dynamodb 也是合法的寫法', () => {
    const repo = createEvidenceRepositoryFromEnv({
      AI_EVIDENCE_SOURCE: 'dynamodb',
      ANALYTICS_TABLE_NAME: 't',
    });
    expect(repo.description).toContain('dynamodb');
  });
});
