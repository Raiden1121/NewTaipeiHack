import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  AnalyticsSnapshotEvidenceRepository,
  CompositeEvidenceRepository,
  CuratedFileEvidenceRepository,
  CORE_CONTEXT_METRIC_IDS,
  FOCUSED_LIMIT_PER_DATASET,
  buildAiContext,
  hasComparisonIntent,
  inferComparisonMetrics,
  inferFocusMetrics,
} from '../src/context/buildContext.js';
import type { EvidenceBundle, EvidenceQuery } from '../src/context/evidenceRepository.js';
import { buildSearchQuery } from '../src/handlers/runFeature.js';
import { makeEvidence, makeRequestContext } from './helpers.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const fixtureDataDir = path.join(here, 'fixtures', 'data-pipeline-data');

/**
 * 「為何八里薪資第六高」這類問題需要全 29 區的同一個指標才答得出來，
 * 但 `focusDistrict` 的預設篩選會把 evidence 縮成一區。
 *
 * 這個檔案鎖住的是：跨區資料真的進得來，而且不會被 context 上限擠掉。
 * 沒有它的話模型只能照抄使用者的前提 —— 而實測那個前提是錯的
 * （八里是第 5 高，不是第 6）。
 */

describe('inferComparisonMetrics', () => {
  it('薪資類問題會帶出薪資相關的跨區指標', () => {
    const metrics = inferComparisonMetrics('為何八里薪資第六高？');

    expect(metrics).toContain('salary_median');
    // 解釋「為何高」需要的不只是被問的那個指標
    expect(metrics).toContain('high_salary_ratio');
  });

  it('租金與房價分得開', () => {
    expect(inferComparisonMetrics('哪一區租金最貴？')).toContain('rent_median');
    expect(inferComparisonMetrics('哪一區房價最高？')).toContain('house_price_median');
  });

  /**
   * 跨區指標刻意只放「真的需要排名」的那幾個，因為每個都會 ×29 筆 evidence，
   * 而 input token 直接影響延遲。
   *
   * 上限從 3 放寬到 4：薪資那條加了 `adjusted_youth_wage`。理由是使用者說
   * 「青年薪資」時，誠實的指標是它（youthEligibility=eligible），而
   * `salary_median` 是全體職缺統計（context_only）。只有它跨區可比，
   * 模型才能回答「這區的青年實質薪資排第幾」而不是拿全年齡數字代答。
   *
   * 這個上限是預算而不是禁令：要再加就要有同等級的理由，並重量延遲。
   */
  it('跨區指標保持精簡（每個都會乘上 29 區）', () => {
    for (const question of ['哪一區薪資最高？', '哪一區租金最貴？', '哪一區生育率最低？']) {
      expect(inferComparisonMetrics(question).length).toBeLessThanOrEqual(4);
    }
  });

  /**
   * 面向分數（`yoiComponents.*`）**要**跨區，輔助指標留在 focus。
   *
   * 實測踩到的：「為什麼八里區的青年薪資分數這麼高？」原本 `yoiComponents.salary`
   * 只在 focusMetricIds，模型只拿到八里自己的 68.12 分，於是回答「無法確認排名」——
   * 而它其實是 29 區第 2 高。使用者問「分數為什麼高」，問的就是那個分數的排名。
   */
  it('面向分數要跨區，但單位換算等輔助指標留在 focus', () => {
    const comparison = inferComparisonMetrics('哪一區房價最高？');
    expect(comparison).toContain('yoiComponents.housing');
    // house_price_median_wan 只是同一個數字換成「萬元」，不需要 29 區都拿
    expect(comparison).not.toContain('house_price_median_wan');
    expect(inferFocusMetrics('哪一區房價最高？')).toContain('house_price_median_wan');
  });

  /**
   * 這兩題是實測答錯的問法，直接寫成回歸測試。
   */
  it('「宜居度」要能命中機會指數（實測漏過）', () => {
    const metrics = inferComparisonMetrics('怎麼可能新莊的宜居度比板橋還低？板橋房價那麼貴耶');

    expect(metrics).toContain('opportunityIndex');
    // 句子裡有「房價」，所以住宅分數也要跨區才能比較兩區的居住面向
    expect(metrics).toContain('yoiComponents.housing');
  });

  it('房價與宜居度比較會帶出薪資中位數作為負擔脈絡', () => {
    const metrics = inferComparisonMetrics('為什麼新莊的宜居度比板橋還低？板橋房價不是比較貴嗎？');

    // 薪資中位數若只放在焦點指標，沒有 focusDistrict 時可能被每個 dataset 的
    // 取樣上限截掉，模型就會產生無法追溯的薪資 evidenceId。
    expect(metrics).toContain('salary_median');
  });

  it('「薪資分數」要把分數本身納入跨區（實測漏過）', () => {
    const metrics = inferComparisonMetrics('為什麼八里區的青年薪資分數這麼高？');

    expect(metrics).toContain('yoiComponents.salary');
  });

  it('「分數」「指數」本身就算比較意圖（一個 0-100 分單獨看沒有意義）', () => {
    expect(hasComparisonIntent('八里的薪資分數為什麼這麼高')).toBe(true);
    expect(hasComparisonIntent('樹林的機會指數怎麼算的')).toBe(true);
  });

  it('沒有指名指標但有比較意圖時，給頭條指標', () => {
    const metrics = inferComparisonMetrics('哪一區最適合青年？');

    expect(metrics).toContain('opportunityIndex');
    expect(metrics.length).toBeGreaterThan(0);
  });

  it('既沒有指標關鍵字也沒有比較意圖時回空陣列（維持單區行為）', () => {
    expect(inferComparisonMetrics('你好')).toEqual([]);
    expect(inferComparisonMetrics('這個 dashboard 怎麼用？')).toEqual([]);
  });

  it('沒有問題時回空陣列', () => {
    expect(inferComparisonMetrics(null)).toEqual([]);
    expect(inferComparisonMetrics(undefined)).toEqual([]);
    expect(inferComparisonMetrics('   ')).toEqual([]);
  });

  it('自然語言「哪一區有多少青年」仍會帶出青年人口跨區指標', () => {
    expect(inferComparisonMetrics('哪一區有多少青年？')).toContain('youth_18_35_total');
  });

  it('結果不重複（多條規則命中同一個指標時）', () => {
    const metrics = inferComparisonMetrics('租金和房價哪一區的居住負擔最重？');

    expect(new Set(metrics).size).toBe(metrics.length);
  });

  it('hasComparisonIntent 認得排名與比較的說法', () => {
    for (const question of ['哪一區最高？', '八里排第幾？', '跟板橋比起來呢？', '高於平均嗎？']) {
      expect(hasComparisonIntent(question)).toBe(true);
    }
    expect(hasComparisonIntent('板橋的租金中位數是多少？')).toBe(false);
  });
});

describe('buildAiContext 的跨區比較資料', () => {
  const repository = () =>
    new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
      new AnalyticsSnapshotEvidenceRepository(fixtureDataDir),
    ]);

  it('有 question 時自動撈跨區指標，不受 focusDistrict 限制', async () => {
    // fixture 只有 2 個行政區（板橋、三重），所以「跨區」在這裡是 2 區。
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資比三重高？',
    });

    const salary = context.evidence.filter((item) => item.metricId === 'salary_median');
    const districts = new Set(salary.map((item) => item.districtName));

    expect(districts).toContain('板橋區');
    // 這是重點：另一區的值也在，否則無法比較
    expect(districts).toContain('三重區');
  });

  it('房價與宜居度問題保留新莊與板橋的薪資 evidence', async () => {
    const districtNames = ['板橋區', '三重區', '新莊區'];
    const analyticsEvidence = (districtName: string, metricId: string, suffix: string) =>
      makeEvidence({
        evidenceId: `analytics_dashboard_overview:snapshot:test:${districtName}:${metricId}:${suffix}`,
        dataset: 'analytics_dashboard_overview',
        source: 'analytics_snapshot',
        sourceRecordId: `test:${districtName}:${metricId}:${suffix}`,
        sourceKind: 'analytics',
        districtName,
        period: 'snapshot:test',
        periodType: 'snapshot',
        metricId,
        metricSource: 'analytics_metric',
        value: 50,
        unit: 'score',
      });
    const limitedRepository = {
      description: 'limited-analytics-fixture',
      async query(query: EvidenceQuery): Promise<EvidenceBundle> {
        // 模擬正式資料：焦點查詢每個 dataset 只取前 30 筆，薪資剛好沒有新莊；
        // 跨區查詢則回傳完整的比較指標。
        const isComparisonQuery = query.limitPerDataset === 400;
        const wantsSalary = query.metricIds?.includes('salary_median') ?? false;
        const evidence = isComparisonQuery
          ? (wantsSalary
              ? districtNames.map((district) => analyticsEvidence(district, 'salary_median', 'comparison'))
              : [])
          : Array.from({ length: 30 }, (_, index) =>
              analyticsEvidence(index % 2 === 0 ? '板橋區' : '三重區', 'salary_median', `primary-${index}`),
            );
        return { evidence, totalMatched: evidence.length, truncated: false, notes: [] };
      },
    };

    const context = await buildAiContext(limitedRepository, {
      focusArea: 'policy',
      question: '為什麼新莊的宜居度比板橋還低？板橋房價不是比較貴嗎？',
    });

    const salaryDistricts = new Set(
      context.evidence
        .filter((item) => item.metricId === 'salary_median')
        .map((item) => item.districtName),
    );

    expect(salaryDistricts).toContain('新莊區');
    expect(salaryDistricts).toContain('板橋區');
  });

  it('未指定焦點區時仍取得問題點名兩區的完整子分數', async () => {
    const districts = ['三重區', '中和區', '永和區', '板橋區', '新莊區'];
    const metrics = [
      'youth_18_35_total', 'salary_median', 'house_price_median', 'rent_wage_ratio',
      'opportunityIndex', 'yoiRaw', 'yoiComponents.job', 'yoiComponents.salary',
      'yoiComponents.talent', 'yoiComponents.housing', 'retentionRiskLevel',
      'people_total', 'house_price_median_wan', 'price_per_ping', 'total_price',
      'yoiComponents.transport',
    ];
    const allEvidence = districts.flatMap((districtName) =>
      metrics.map((metricId) => makeEvidence({
        evidenceId: `analytics_dashboard_overview:snapshot:test:${districtName}:${metricId}`,
        dataset: 'analytics_dashboard_overview',
        districtName,
        period: 'snapshot:test',
        periodType: 'snapshot',
        metricId,
        metricSource: 'analytics_metric',
        value: 50,
        unit: 'score',
      })),
    );
    const repositoryWithOrderedDistricts = {
      description: 'ordered-district-fixture',
      async query(query: EvidenceQuery): Promise<EvidenceBundle> {
        const matched = allEvidence.filter((item) =>
          (query.districtNames === undefined || query.districtNames.includes(item.districtName ?? '')) &&
          (query.metricIds === undefined || query.metricIds.includes(item.metricId)),
        );
        const evidence = matched.slice(0, query.limitPerDataset ?? 200);
        return { evidence, totalMatched: matched.length, truncated: evidence.length < matched.length, notes: [] };
      },
    };

    const context = await buildAiContext(repositoryWithOrderedDistricts, {
      focusArea: 'policy',
      question: '為什麼新莊的宜居度比板橋還低？板橋房價不是比較貴嗎？',
    });
    for (const districtName of ['新莊區', '板橋區']) {
      expect(context.evidence.some((item) =>
        item.districtName === districtName && item.metricId === 'yoiComponents.transport',
      )).toBe(true);
      expect(context.evidence.some((item) =>
        item.districtName === districtName && item.metricId === 'yoiComponents.job',
      )).toBe(true);
    }
  });

  it('沒有 question 時不撈跨區資料（explain / policy 不需要）', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
    });

    const otherDistricts = context.evidence.filter(
      (item) => item.geoLevel === 'district' && item.districtName !== '板橋區',
    );

    expect(otherDistricts).toHaveLength(0);
  });

  it('明確傳 comparisonMetrics: [] 可以關掉', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資比三重高？',
      comparisonMetrics: [],
    });

    const otherDistricts = context.evidence.filter(
      (item) => item.geoLevel === 'district' && item.districtName !== '板橋區',
    );

    expect(otherDistricts).toHaveLength(0);
  });

  it('會在 limitations 說明納入了哪些跨區指標、涵蓋幾區', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      question: '為何板橋薪資第一高？',
    });

    const note = context.knownLimitations.find((item) => item.includes('跨行政區'));
    expect(note).toBeDefined();
    expect(note).toContain('salary_median');
    expect(note).toContain('個行政區');
  });

  /**
   * 這條測的是一個真的踩過的坑：`prioritizeEvidenceForContext()` 超過上限時是
   * 「每組取前 N 筆」，所以順序就是優先權。跨區資料排在焦點區後面的話，
   * 配額用完就被截掉，於是「答不出排名」的問題又回來了。
   */
  it('context 上限很小時，跨區比較資料優先保留', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資比三重高？',
      maxEvidence: 12,
    });

    const salary = context.evidence.filter((item) => item.metricId === 'salary_median');
    expect(new Set(salary.map((item) => item.districtName)).size).toBeGreaterThan(1);
  });

  it('不會因為跨區查詢而出現重複的 evidenceId', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資比三重高？',
    });

    const ids = context.evidence.map((item) => item.evidenceId);
    expect(new Set(ids).size).toBe(ids.length);
  });
});

describe('人口查詢的自然語言焦點', () => {
  it('「板橋區有多少青年」會收斂到人口指標', () => {
    const focus = inferFocusMetrics('板橋區有多少青年？');

    expect(focus).toContain('youth_18_35_total');
    expect(focus).toContain('annual.population.youth_18_35_total');
  });
});

describe('網路搜尋預設開啟', () => {
  const repository = () =>
    new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
      new AnalyticsSnapshotEvidenceRepository(fixtureDataDir),
    ]);

  it('預設 enabled 是 true', async () => {
    const context = await buildAiContext(repository(), { focusDistrict: '板橋區' });

    expect(context.webSearch.enabled).toBe(true);
    expect(context.webSearch.contextSize).toBe('low');
  });

  it('呼叫端仍然可以關掉', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      webSearch: { enabled: false },
    });

    expect(context.webSearch.enabled).toBe(false);
  });

  it('可以只覆寫 contextSize', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      webSearch: { contextSize: 'high' },
    });

    expect(context.webSearch.enabled).toBe(true);
    expect(context.webSearch.contextSize).toBe('high');
  });
});

describe('buildSearchQuery：搜尋 query 要有地理脈絡', () => {
  /**
   * 實測踩到的：「為何八里薪資第六高？」直接拿去搜，Tavily 回的是**雲林與台中**
   * 薪資比較的 Threads 討論 —— 因為那句話沒有任何地理脈絡。
   * 對照組「為何坪林薪資是全新北最高？」（問句自帶「全新北」）搜到的是
   * 水利署的坪林專題報導。差別只在 query 有沒有地理脈絡。
   */
  it('問句沒有地理脈絡時補上新北市與行政區', () => {
    const query = buildSearchQuery(
      makeRequestContext({ question: '為何八里薪資第六高？', focusDistrict: '八里區' }),
    );

    expect(query).toContain('為何八里薪資第六高？');
    expect(query).toContain('新北市');
  });

  it('問句已經提到新北就不重複加', () => {
    const query = buildSearchQuery(
      makeRequestContext({ question: '為何坪林薪資是全新北最高？', focusDistrict: '坪林區' }),
    );

    // 「新北」已在問句裡，不該再多一個「新北市」把權重稀釋掉
    expect(query.match(/新北/g)?.length).toBe(1);
  });

  it('問句已經提到行政區名就不重複加', () => {
    const query = buildSearchQuery(
      makeRequestContext({ question: '八里區的薪資為什麼偏高？', focusDistrict: '八里區' }),
    );

    expect(query.match(/八里/g)?.length).toBe(1);
  });

  it('沒有 question 時用情境組主題（explain / policy 走這條）', () => {
    const query = buildSearchQuery(
      makeRequestContext({ question: null, focusDistrict: '板橋區', focusArea: 'employment' }),
    );

    expect(query).toContain('新北市');
    expect(query).toContain('板橋區');
    expect(query).toContain('青年');
  });
});

describe('inferFocusMetrics：依主題收斂焦點行政區的指標', () => {
  it('薪資問題帶出薪資相關指標，含 curated 的母體欄位', () => {
    const metrics = inferFocusMetrics('為何八里薪資第六高？');

    expect(metrics).toContain('salary_median');
    expect(metrics).toContain('high_salary_ratio');
    // curated 逐筆職缺的薪資欄位 —— 讓模型能判斷中位數是不是被少數幾筆拉高的
    expect(metrics).toContain('salary_midpoint');
    expect(metrics).toContain('position_count');
  });

  /**
   * 這是收斂機制的安全網：關鍵字判斷錯的時候，模型至少還有基本背景。
   */
  it('永遠包含核心背景指標', () => {
    for (const question of ['為何八里薪資第六高？', '哪一區租金最貴？', '生育率最低的區是？']) {
      const metrics = inferFocusMetrics(question);
      for (const core of CORE_CONTEXT_METRIC_IDS) {
        expect(metrics).toContain(core);
      }
    }
  });

  it('主題對不上時回空陣列（代表不要限制，維持原本行為）', () => {
    expect(inferFocusMetrics('你好')).toEqual([]);
    expect(inferFocusMetrics('這個 dashboard 怎麼用？')).toEqual([]);
    expect(inferFocusMetrics(null)).toEqual([]);
  });

  /**
   * 「哪一區最適合青年」有比較意圖但沒指名指標。
   * 跨區用頭條指標，但**焦點範圍不收斂** —— 這種開放式問題可能牽涉任何面向，
   * 收斂反而會讓模型缺資料。
   */
  it('只有比較意圖、沒有主題時不收斂焦點範圍', () => {
    expect(inferComparisonMetrics('哪一區最適合青年？').length).toBeGreaterThan(0);
    expect(inferFocusMetrics('哪一區最適合青年？')).toEqual([]);
  });

  it('多主題問題會合併兩邊的指標', () => {
    const metrics = inferFocusMetrics('薪資和租金哪個是板橋青年更大的問題？');

    expect(metrics).toContain('salary_median');
    expect(metrics).toContain('rent_median');
  });
});

describe('buildAiContext 的焦點收斂', () => {
  const repository = () =>
    new CompositeEvidenceRepository([
      new CuratedFileEvidenceRepository(fixtureDataDir),
      new AnalyticsSnapshotEvidenceRepository(fixtureDataDir),
    ]);

  it('主題明確時，焦點行政區的 evidence 明顯變少', async () => {
    const unscoped = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '板橋區的青年狀況如何？', // 對不到主題關鍵字 → 不收斂
      maxEvidence: 0,
    });
    const scoped = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資這麼高？', // 命中薪資主題 → 收斂
      maxEvidence: 0,
    });

    expect(scoped.evidence.length).toBeLessThan(unscoped.evidence.length);
  });

  it('收斂之後只留下主題相關與核心指標', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資這麼高？',
      maxEvidence: 0,
    });

    const allowed = new Set(inferFocusMetrics('為何板橋薪資這麼高？'));
    const comparison = new Set(inferComparisonMetrics('為何板橋薪資這麼高？'));
    for (const item of context.evidence) {
      expect(allowed.has(item.metricId) || comparison.has(item.metricId)).toBe(true);
    }
  });

  it('核心背景指標在收斂後仍然存在', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資這麼高？',
      maxEvidence: 0,
    });

    expect(context.evidence.some((item) => item.metricId === 'youth_18_35_total')).toBe(true);
  });

  it('收斂一定要寫進 limitations（不可靜默縮小範圍）', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資這麼高？',
    });

    const note = context.knownLimitations.find((item) => item.includes('收斂了取用範圍'));
    expect(note).toBeDefined();
    expect(note).toContain(String(FOCUSED_LIMIT_PER_DATASET));
  });

  it('呼叫端自己傳 metricIds 時不套用收斂（明確指定優先）', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      question: '為何板橋薪資這麼高？',
      metricIds: ['youth_18_35_total'],
      maxEvidence: 0,
    });

    expect(context.evidence.every((item) => item.metricId === 'youth_18_35_total')).toBe(true);
    expect(context.knownLimitations.some((item) => item.includes('收斂了取用範圍'))).toBe(false);
  });

  it('明確傳 focusMetricIds: [] 可以關掉收斂', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      question: '為何板橋薪資這麼高？',
      focusMetricIds: [],
      maxEvidence: 0,
    });

    expect(context.knownLimitations.some((item) => item.includes('收斂了取用範圍'))).toBe(false);
  });

  it('沒有 question 時不收斂（explain / policy 不受影響）', async () => {
    const context = await buildAiContext(repository(), {
      focusDistrict: '板橋區',
      focusArea: 'employment',
      maxEvidence: 0,
    });

    expect(context.knownLimitations.some((item) => item.includes('收斂了取用範圍'))).toBe(false);
  });
});
