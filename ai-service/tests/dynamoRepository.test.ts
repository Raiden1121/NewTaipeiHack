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
});

describe('selectPlans（依主題決定讀哪些 item）', () => {
  it('沒指定主題時全讀', () => {
    expect(selectPlans({}).length).toBeGreaterThan(3);
  });

  it('employment 不會去讀生育趨勢', () => {
    const keys = selectPlans({ focusArea: 'employment' }).map((plan) => plan.key.sk);
    expect(keys).toContain('DISTRICTS');
    expect(keys).not.toContain('FERTILITY_TREND');
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
