import { describe, expect, it, vi } from 'vitest';
import {
  TavilyWebSearchProvider,
  filterByDomains,
  resolveIncludeDomains,
} from '../src/websearch/tavily.js';
import { createWebSearchProviderFromEnv } from '../src/websearch/factory.js';
import { DisabledWebSearchProvider } from '../src/websearch/provider.js';
import {
  TRUSTED_SOURCE_DOMAINS,
  WebFindingSchema,
  type WebFinding,
  type WebSearchSettings,
} from '../src/types/webFinding.js';

const settings: WebSearchSettings = { enabled: true, contextSize: 'low', scope: 'all' };

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

describe('搜尋範圍開關：全網 vs 只信任來源', () => {
  function fakeFetch(captured: { body?: Record<string, unknown> }) {
    return (async (_url: string, init?: RequestInit) => {
      captured.body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ results: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }) as unknown as typeof fetch;
  }

  it('scope=all 時不限制網域', async () => {
    const captured: { body?: Record<string, unknown> } = {};
    const provider = new TavilyWebSearchProvider({ fetchImpl: fakeFetch(captured) });

    await provider.search('八里 薪資', { enabled: true, contextSize: 'low', scope: 'all' });

    expect(captured.body).not.toHaveProperty('include_domains');
  });

  it('scope=trusted 時限定在 gov.tw / edu.tw', async () => {
    const captured: { body?: Record<string, unknown> } = {};
    const provider = new TavilyWebSearchProvider({ fetchImpl: fakeFetch(captured) });

    await provider.search('八里 薪資', { enabled: true, contextSize: 'low', scope: 'trusted' });

    expect(captured.body?.include_domains).toEqual([...TRUSTED_SOURCE_DOMAINS]);
    expect(TRUSTED_SOURCE_DOMAINS).toContain('gov.tw');
  });

  /**
   * `trusted` 模式搜不到東西是**常態**（很多產業背景不在 gov.tw 上），
   * 而「網路上沒有」跟「我限制了範圍所以沒找到」對使用者是完全不同的意思。
   */
  it('scope=trusted 時一定要在 notes 說明限制了範圍', async () => {
    const captured: { body?: Record<string, unknown> } = {};
    const provider = new TavilyWebSearchProvider({ fetchImpl: fakeFetch(captured) });

    const result = await provider.search('八里 薪資', {
      enabled: true,
      contextSize: 'low',
      scope: 'trusted',
    });

    // note 要講出實際限定的網域，而不是只說「限定了」——
    // 使用者要能判斷「我想找的東西是不是本來就不在這些網域上」。
    expect(result.notes.join('')).toContain('限定在下列網域');
    expect(result.notes.join('')).toContain('gov.tw');
    expect(result.notes.join('')).toContain('edu.tw');
  });

  it('scope=all 時不加那條 note（沒有限制就不用解釋）', async () => {
    const captured: { body?: Record<string, unknown> } = {};
    const provider = new TavilyWebSearchProvider({ fetchImpl: fakeFetch(captured) });

    const result = await provider.search('八里 薪資', {
      enabled: true,
      contextSize: 'low',
      scope: 'all',
    });

    expect(result.notes).toEqual([]);
  });
});

describe('resolveIncludeDomains：使用者選擇與營運者硬限制的關係', () => {
  it('scope=all 且沒設硬限制 → 不限制', () => {
    expect(resolveIncludeDomains('all', [])).toEqual([]);
  });

  it('scope=all 但營運者設了硬限制 → 仍然套用硬限制', () => {
    // 使用者不該能用「全網」把營運者的政策繞掉。
    expect(resolveIncludeDomains('all', ['gov.tw', 'ntpc.gov.tw'])).toEqual([
      'gov.tw',
      'ntpc.gov.tw',
    ]);
  });

  it('scope=trusted 且沒設硬限制 → 用可信清單', () => {
    expect(resolveIncludeDomains('trusted', [])).toEqual([...TRUSTED_SOURCE_DOMAINS]);
  });

  it('兩者都有時取交集（以較嚴格的為準）', () => {
    const resolved = resolveIncludeDomains('trusted', ['gov.tw']);

    expect(resolved).toContain('gov.tw');
    // edu.tw 不在營運者的白名單裡，所以不該出現
    expect(resolved).not.toContain('edu.tw');
  });

  it('交集為空時以營運者的硬限制為準，不可退回「不限制」', () => {
    // 營運者只允許 example.com，跟可信清單完全沒有重疊。
    // 回空陣列會變成「全網搜尋」—— 那是最糟的結果。
    const resolved = resolveIncludeDomains('trusted', ['example.com']);

    expect(resolved).toEqual(['example.com']);
    expect(resolved.length).toBeGreaterThan(0);
  });
});

describe('filterByDomains：不相信 Tavily 的 include_domains', () => {
  /**
   * 實測（真 API key、include_domains: ['gov.tw','edu.tw']）Tavily 回來的五筆
   * 全部不在白名單內（blog.salary.tw、news.ttv.com.tw、bo6s.com.tw…）。
   * 所以 include_domains 至少對裸網域後綴不是硬過濾。
   *
   * 「只接受可信來源」是使用者的政策選擇，不能外包給外部 API 的行為細節。
   */
  const finding = (url: string): WebFinding => ({
    findingId: 'web:1',
    title: 't',
    url,
    snippet: 's',
    publishedDate: null,
    retrievedAt: '2026-09-12T00:00:00.000Z',
  });

  it('沒有網域限制時原封不動回傳', () => {
    const findings = [finding('https://blog.salary.tw/a'), finding('https://www.ris.gov.tw/b')];
    expect(filterByDomains(findings, [])).toHaveLength(2);
  });

  it('留下符合後綴的，濾掉不符合的', () => {
    const findings = [
      finding('https://www.ris.gov.tw/b'),
      finding('https://blog.salary.tw/a'),
      finding('https://news.ttv.com.tw/c'),
      finding('https://www.bali.ntpc.gov.tw/d'),
    ];

    const kept = filterByDomains(findings, ['gov.tw']);

    expect(kept.map((f) => new URL(f.url).hostname)).toEqual([
      'www.ris.gov.tw',
      'www.bali.ntpc.gov.tw',
    ]);
  });

  it('比對 hostname 而不是整個 URL（擋掉把網域塞在 query string 的網址）', () => {
    const spoofed = [finding('https://evil.example.com/?ref=gov.tw')];

    expect(filterByDomains(spoofed, ['gov.tw'])).toHaveLength(0);
  });

  it('後綴要對齊到點的邊界（notgov.tw 不算 gov.tw）', () => {
    expect(filterByDomains([finding('https://notgov.tw/a')], ['gov.tw'])).toHaveLength(0);
    expect(filterByDomains([finding('https://gov.tw/a')], ['gov.tw'])).toHaveLength(1);
  });

  it('解析不出 hostname 的一律排除', () => {
    expect(filterByDomains([finding('not-a-url')], ['gov.tw'])).toHaveLength(0);
  });
});

describe('trusted 模式在真實回應形狀下會濾掉不合格的來源', () => {
  it('Tavily 回非白名單網域時，findings 為空並在 notes 說明', async () => {
    // 這就是實測到的情況：include_domains 送了，Tavily 還是回 blog.salary.tw 等等。
    const fetchImpl = (async () =>
      new Response(
        JSON.stringify({
          results: [
            { url: 'https://blog.salary.tw/a', title: 'A', content: 'x' },
            { url: 'https://news.ttv.com.tw/b', title: 'B', content: 'y' },
          ],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )) as unknown as typeof fetch;

    const provider = new TavilyWebSearchProvider({ fetchImpl });
    const result = await provider.search('八里 薪資', {
      enabled: true,
      contextSize: 'low',
      scope: 'trusted',
    });

    expect(result.findings).toHaveLength(0);
    expect(result.notes.join('')).toContain('2 筆');
    expect(result.notes.join('')).toContain('全網搜尋');
  });

  it('白名單內的來源會留下', async () => {
    const fetchImpl = (async () =>
      new Response(
        JSON.stringify({
          results: [
            { url: 'https://www.bali.ntpc.gov.tw/report.pdf', title: '八里區社會救助分析', content: 'x' },
            { url: 'https://blog.salary.tw/a', title: 'A', content: 'y' },
          ],
        }),
        { status: 200, headers: { 'content-type': 'application/json' } },
      )) as unknown as typeof fetch;

    const provider = new TavilyWebSearchProvider({ fetchImpl });
    const result = await provider.search('八里 薪資', {
      enabled: true,
      contextSize: 'low',
      scope: 'trusted',
    });

    expect(result.findings).toHaveLength(1);
    expect(result.findings[0]?.url).toContain('bali.ntpc.gov.tw');
  });
});

describe('有網域限制時多抓再過濾', () => {
  /**
   * 只要 5 筆再自己濾，實測結果是 **0 筆**（「為何八里薪資第六高？ 新北市」
   * 限定 gov.tw 時 5 筆全被濾掉）。而同一個查詢不限制時，第 4 名就是
   * `www.bali.ntpc.gov.tw` —— 官方來源找得到，只是被前幾名擠掉。
   */
  it('限定網域時向 Tavily 要更多筆（4 倍）', async () => {
    const captured: { body?: Record<string, unknown> } = {};
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      captured.body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ results: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }) as unknown as typeof fetch;

    const provider = new TavilyWebSearchProvider({ fetchImpl });
    await provider.search('八里 薪資', { enabled: true, contextSize: 'low', scope: 'trusted' });

    // low 是 5 筆，限定網域時要 20 筆
    expect(captured.body?.max_results).toBe(20);
  });

  it('沒有網域限制時就要原本的筆數', async () => {
    const captured: { body?: Record<string, unknown> } = {};
    const fetchImpl = (async (_url: string, init?: RequestInit) => {
      captured.body = JSON.parse(String(init?.body)) as Record<string, unknown>;
      return new Response(JSON.stringify({ results: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      });
    }) as unknown as typeof fetch;

    const provider = new TavilyWebSearchProvider({ fetchImpl });
    await provider.search('八里 薪資', { enabled: true, contextSize: 'low', scope: 'all' });

    expect(captured.body?.max_results).toBe(5);
  });

  it('多抓之後仍然只回呼叫端要的筆數（不要讓 prompt 吃到 4 倍內容）', async () => {
    const results = Array.from({ length: 20 }, (_, index) => ({
      url: `https://unit${index}.gov.tw/a`,
      title: `T${index}`,
      content: 'x',
    }));
    const fetchImpl = (async () =>
      new Response(JSON.stringify({ results }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })) as unknown as typeof fetch;

    const provider = new TavilyWebSearchProvider({ fetchImpl });
    const result = await provider.search('八里 薪資', {
      enabled: true,
      contextSize: 'low',
      scope: 'trusted',
    });

    // 20 筆全部符合白名單，但 low 只要 5 筆
    expect(result.findings).toHaveLength(5);
  });
});
