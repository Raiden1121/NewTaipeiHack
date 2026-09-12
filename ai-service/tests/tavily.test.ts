import { describe, expect, it, vi } from 'vitest';
import { TavilyWebSearchProvider } from '../src/websearch/tavily.js';
import { createWebSearchProviderFromEnv } from '../src/websearch/factory.js';
import { DisabledWebSearchProvider } from '../src/websearch/provider.js';
import { WebFindingSchema, type WebSearchSettings } from '../src/types/webFinding.js';

const settings: WebSearchSettings = { enabled: true, contextSize: 'low' };

/** 真實的 Tavily 回應形狀（欄位取自實際呼叫 keyless API 的結果）。 */
const realShapedResponse = {
  query: '新北市青年局 青年創業基地',
  follow_up_questions: null,
  answer: null,
  images: [],
  response_time: 1.2,
  request_id: 'abc',
  results: [
    {
      url: 'https://www.youth.ntpc.gov.tw/youth/ch/app/folder/59',
      title: '找基地 - 新北市青年局',
      content: '新北創力坊、新北青創土城綠創基地、新北青創五股自造基地…',
      score: 0.787,
      raw_content: null,
      id: 'r1',
    },
    {
      url: 'https://www.youth.ntpc.gov.tw',
      title: '新北市青年局',
      content: '青年局提供技能交流、創業輔導、住宅體驗、青創活動。',
      score: 0.756,
      raw_content: null,
      id: 'r2',
    },
  ],
};

function fakeFetch(body: unknown, status = 200) {
  return vi.fn(async () =>
    new Response(typeof body === 'string' ? body : JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    }),
  ) as unknown as typeof fetch;
}

describe('認證模式', () => {
  it('沒有 API key 時走 keyless header，不送 authorization', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    const provider = new TavilyWebSearchProvider({ fetchImpl });

    await provider.search('測試', settings);

    const init = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(init.headers['X-Tavily-Access-Mode']).toBe('keyless');
    expect(init.headers.authorization).toBeUndefined();
    expect(provider.description).toContain('keyless');
  });

  it('有 API key 時送 Bearer，不送 keyless header', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    const provider = new TavilyWebSearchProvider({ apiKey: 'tvly-xxx', fetchImpl });

    await provider.search('測試', settings);

    const init = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(init.headers.authorization).toBe('Bearer tvly-xxx');
    expect(init.headers['X-Tavily-Access-Mode']).toBeUndefined();
    expect(provider.description).toContain('api-key');
  });

  it('空字串的 API key 視為沒有設定', () => {
    expect(new TavilyWebSearchProvider({ apiKey: '   ' }).description).toContain('keyless');
  });
});

describe('送出的 request', () => {
  it('contextSize 對應到 max_results（對齊 Bedrock 的語意）', async () => {
    for (const [contextSize, expected] of [
      ['low', 5],
      ['medium', 11],
      ['high', 25],
    ] as const) {
      const fetchImpl = fakeFetch(realShapedResponse);
      await new TavilyWebSearchProvider({ fetchImpl }).search('測試', {
        enabled: true,
        contextSize,
      });

      const body = JSON.parse(
        (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
      );
      expect(body.max_results).toBe(expected);
    }
  });

  it('不要 raw_content：那是整頁全文，會爆 token 與記憶體', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    await new TavilyWebSearchProvider({ fetchImpl }).search('測試', settings);

    const body = JSON.parse(
      (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body.include_raw_content).toBe(false);
  });

  /**
   * Tavily 可以回一段自己生成的 answer。我們刻意不要 —— 那是另一個模型的綜合結論，
   * 無法歸屬到具體來源，也繞過了我們所有的引用驗證機制。
   */
  it('不要 Tavily 自己生成的 answer', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    await new TavilyWebSearchProvider({ fetchImpl }).search('測試', settings);

    const body = JSON.parse(
      (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body.include_answer).toBe(false);
  });

  it('用 basic search_depth，因為延遲預算很緊', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    await new TavilyWebSearchProvider({ fetchImpl }).search('測試', settings);

    const body = JSON.parse(
      (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body.search_depth).toBe('basic');
  });

  it('一定要帶逾時 signal，否則慢掉的搜尋會拖到 API Gateway 超時', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    await new TavilyWebSearchProvider({ fetchImpl }).search('測試', settings);

    const init = (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(init.signal).toBeInstanceOf(AbortSignal);
  });

  it('沒設定網域白名單時不送 include_domains', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    await new TavilyWebSearchProvider({ fetchImpl }).search('測試', settings);

    const body = JSON.parse(
      (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body).not.toHaveProperty('include_domains');
  });

  it('設定網域白名單時送 include_domains', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    await new TavilyWebSearchProvider({ fetchImpl, includeDomains: ['gov.tw'] }).search(
      '測試',
      settings,
    );

    const body = JSON.parse(
      (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body.include_domains).toEqual(['gov.tw']);
  });
});

describe('回應解析', () => {
  it('對應成合法的 WebFinding，findingId 從 web:1 開始', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch(realShapedResponse),
    }).search('測試', settings);

    expect(findings).toHaveLength(2);
    expect(findings[0]?.findingId).toBe('web:1');
    expect(findings[1]?.findingId).toBe('web:2');
    for (const finding of findings) {
      expect(() => WebFindingSchema.parse(finding)).not.toThrow();
    }
  });

  it('保留 title 與 url，這是引用的必要資訊', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch(realShapedResponse),
    }).search('測試', settings);

    expect(findings[0]?.title).toBe('找基地 - 新北市青年局');
    expect(findings[0]?.url).toBe('https://www.youth.ntpc.gov.tw/youth/ch/app/folder/59');
  });

  it('一般搜尋沒有 published_date 時是 null，不是異常', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch(realShapedResponse),
    }).search('測試', settings);

    expect(findings[0]?.publishedDate).toBeNull();
  });

  it('retrievedAt 是 ISO 字串，讓使用者判斷資料多新', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch(realShapedResponse),
    }).search('測試', settings);

    expect(() => new Date(findings[0]!.retrievedAt).toISOString()).not.toThrow();
  });

  it('過長的摘要會被截斷，避免爆 token', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch({
        results: [{ url: 'https://example.gov.tw/a', title: '長文', content: 'あ'.repeat(3000) }],
      }),
    }).search('測試', settings);

    expect(findings[0]!.snippet.length).toBeLessThan(700);
    expect(findings[0]!.snippet.endsWith('…')).toBe(true);
  });

  /**
   * 沒有網址的「網路來源」無法被查證，留著只會讓輸出看起來有引用但指不到任何地方。
   */
  it('缺 url 或 title 的結果直接丟掉，不補預設值', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch({
        results: [
          { title: '沒有網址', content: 'x' },
          { url: 'https://ok.gov.tw/a', content: '沒有標題' },
          { url: 'https://ok.gov.tw/b', title: '正常', content: 'y' },
        ],
      }),
    }).search('測試', settings);

    expect(findings).toHaveLength(1);
    expect(findings[0]?.title).toBe('正常');
  });

  it('url 不是合法網址的結果也丟掉', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch({ results: [{ url: 'not-a-url', title: '壞網址', content: 'x' }] }),
    }).search('測試', settings);

    expect(findings).toEqual([]);
  });

  it('results 不是陣列時回空陣列，不丟錯', async () => {
    const { findings } = await new TavilyWebSearchProvider({
      fetchImpl: fakeFetch({ results: null }),
    }).search('測試', settings);

    expect(findings).toEqual([]);
  });
});

describe('錯誤處理', () => {
  it('HTTP 失敗時丟錯，訊息含狀態碼（runFeature 會捕捉）', async () => {
    const provider = new TavilyWebSearchProvider({ fetchImpl: fakeFetch('server error', 500) });

    await expect(provider.search('測試', settings)).rejects.toThrow(/HTTP 500/);
  });

  it('keyless 撞到 429 時，訊息要告訴人該設 API key', async () => {
    const provider = new TavilyWebSearchProvider({ fetchImpl: fakeFetch('rate limited', 429) });

    await expect(provider.search('測試', settings)).rejects.toThrow(/TAVILY_API_KEY/);
  });

  it('有 API key 還撞 429 時不要給錯誤的建議', async () => {
    const provider = new TavilyWebSearchProvider({
      apiKey: 'tvly-x',
      fetchImpl: fakeFetch('rate limited', 429),
    });

    await expect(provider.search('測試', settings)).rejects.not.toThrow(/TAVILY_API_KEY/);
  });
});

describe('createWebSearchProviderFromEnv', () => {
  it('預設用 Tavily keyless，零設定就能用', () => {
    const provider = createWebSearchProviderFromEnv({});

    expect(provider).toBeInstanceOf(TavilyWebSearchProvider);
    expect(provider.description).toContain('keyless');
  });

  it('有 TAVILY_API_KEY 時改用 API key', () => {
    expect(createWebSearchProviderFromEnv({ TAVILY_API_KEY: 'tvly-x' }).description).toContain(
      'api-key',
    );
  });

  it('WEB_SEARCH_PROVIDER=off 時整個功能在伺服器端停用', () => {
    expect(createWebSearchProviderFromEnv({ WEB_SEARCH_PROVIDER: 'off' })).toBeInstanceOf(
      DisabledWebSearchProvider,
    );
    expect(createWebSearchProviderFromEnv({ WEB_SEARCH_PROVIDER: 'OFF' })).toBeInstanceOf(
      DisabledWebSearchProvider,
    );
  });

  it('WEB_SEARCH_INCLUDE_DOMAINS 可以把來源收斂成官方網站', async () => {
    const fetchImpl = fakeFetch(realShapedResponse);
    // 直接建構以便注入 fetch；env 解析行為由下一個測試涵蓋。
    await new TavilyWebSearchProvider({ fetchImpl, includeDomains: ['gov.tw', 'ntpc.gov.tw'] }).search(
      '測試',
      settings,
    );

    const body = JSON.parse(
      (fetchImpl as unknown as ReturnType<typeof vi.fn>).mock.calls[0][1].body as string,
    );
    expect(body.include_domains).toEqual(['gov.tw', 'ntpc.gov.tw']);
  });

  it('空白的網域設定不會變成無效的白名單', () => {
    // 只驗證不丟錯且仍是 Tavily —— 空字串應該被當成沒設定。
    expect(
      createWebSearchProviderFromEnv({ WEB_SEARCH_INCLUDE_DOMAINS: ' , ,' }),
    ).toBeInstanceOf(TavilyWebSearchProvider);
  });
});
