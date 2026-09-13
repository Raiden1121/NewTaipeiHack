/**
 * 直接問一個問題：`npm run dev:ask -- "問題" [行政區] [主題]`
 *
 * 走的是**跟線上完全一樣的路徑**（`buildAiContext` → `dataQa` → 同一份 prompt
 * 與同一套驗證），所以看到的回答就是接上前端之後使用者會看到的東西。
 *
 * 用法：
 *   npm run dev:ask -- "板橋區有多少青年？"
 *   npm run dev:ask -- "為何八里薪資排前面？" 八里區 employment
 *   npm run dev:ask -- "哪一區房價最貴？" 板橋區 housing
 *   npm run dev:ask -- "..." 板橋區 employment --no-search
 *
 * 主題（`focusArea`）決定讀哪些 analytics 分析，合法值見
 * `ANALYTICS_ARTIFACTS_BY_FOCUS_AREA`：employment / housing / transport /
 * population / retention / fertility / resources / participation / policy…
 *
 * 印出 `basis` 的每一筆 evidenceId 是刻意的：回答對不對要能追溯到具體哪個數字，
 * 只看一段中文沒辦法判斷它是引用還是編的。
 */
import { createBedrockClientFromEnv, MockBedrockClient } from '../bedrock/client.js';
import { buildAiContext, createEvidenceRepositoryFromEnv } from '../context/buildContext.js';
import { dataQa } from '../handlers/dataQa.js';
import { createWebSearchProviderFromEnv } from '../websearch/factory.js';
import { buildDataQaPrompt, QA_ANSWER_MAX_CHARS } from '../prompts/dataQa.js';
import { DisabledWebSearchProvider } from '../websearch/provider.js';

function estimateTokens(text: string): number {
  let cjk = 0;
  for (const char of text) {
    if (char.codePointAt(0)! > 0x2e80) {
      cjk += 1;
    }
  }
  return Math.round(cjk + (text.length - cjk) / 3.5);
}

const args = process.argv.slice(2);
const flags = new Set(args.filter((arg) => arg.startsWith('--')));
const positional = args.filter((arg) => !arg.startsWith('--'));

const question = positional[0];
if (question === undefined || question.trim().length === 0) {
  console.error('用法：npm run dev:ask -- "問題" [行政區] [主題]');
  process.exit(1);
}
const focusDistrict = positional[1] ?? '板橋區';
const focusArea = positional[2] ?? 'employment';
const noSearch = flags.has('--no-search');

const repository = createEvidenceRepositoryFromEnv();
const client = createBedrockClientFromEnv();
if (client instanceof MockBedrockClient) {
  console.error('沒讀到模型設定，會拿到假回覆。請確認 repo 根目錄的 .env。');
  process.exit(1);
}
const searchProvider = noSearch ? new DisabledWebSearchProvider() : createWebSearchProviderFromEnv();

const context = await buildAiContext(repository, {
  focusDistrict,
  focusArea,
  question,
  ...(noSearch ? { webSearch: { enabled: false, contextSize: 'low', scope: 'all' } } : {}),
});

const request = { ...context, question };
const prompt = buildDataQaPrompt(request);

console.log('='.repeat(78));
console.log(`問題    ：${question}`);
console.log(`行政區  ：${focusDistrict}　主題：${focusArea}`);
console.log(`模型    ：${client.description}`);
console.log(`evidence：${context.evidence.length} 筆　prompt≈${estimateTokens(prompt.system) + estimateTokens(prompt.user)} tok`);
console.log(`搜尋    ：${noSearch ? '關閉' : searchProvider.description}`);
console.log('='.repeat(78));

const startedAt = Date.now();
const { output, sources } = await dataQa(client, request, searchProvider);
const elapsed = Date.now() - startedAt;

const answerChars = output.answer?.length ?? 0;
console.log('');
console.log(`【回答】（${answerChars} 字，上限 ${QA_ANSWER_MAX_CHARS}${answerChars <= QA_ANSWER_MAX_CHARS ? ' OK' : ' 超出'}）`);
console.log('');
console.log(output.answer ?? '(空)');

const blocks = [
  ...output.issues.map((line) => ['issues', line] as const),
  ...output.strengths.map((line) => ['strengths', line] as const),
  ...output.resourceGaps.map((line) => ['resourceGaps', line] as const),
  ...output.policyDirections.map((line) => ['policyDirections', line] as const),
];
if (blocks.length > 0) {
  console.log('');
  console.log(`【四塊分析】${blocks.length} 條（政策類問題才會有）`);
  for (const [field, line] of blocks) {
    console.log(`  [${field}] ${line}`);
  }
}

// basis 是可追溯性的核心：每一條都必須對得上一筆真實 evidence，
// 對不上的話 runFeature() 會直接拒絕回傳（findUnknownEvidenceIds）。
console.log('');
console.log(`【判斷依據】${output.basis.length} 筆`);
for (const citation of output.basis) {
  console.log(`  ${citation.evidenceId}`);
  console.log(`    ${citation.note}`);
}

if (output.webReferences.length > 0) {
  console.log('');
  console.log(`【網路來源】${output.webReferences.length} 筆（未經驗證）`);
  // webReferences 只帶 findingId 與 note（模型不能自己寫網址，否則就是憑記憶編）。
  // 實際網址由程式從 sources 推導，所以要在那邊找。
  const webUrls = sources
    .filter((source) => source.kind === 'web')
    .flatMap((source) => [source.url, ...source.recordUrls])
    .filter((url): url is string => url !== null);
  for (const reference of output.webReferences) {
    console.log(`  ${reference.findingId}　${reference.note ?? ''}`);
  }
  for (const url of webUrls) {
    console.log(`    ${url}`);
  }
}

console.log('');
console.log(`【資料充足度】${output.dataSufficiency}`);
console.log(`【限制】${output.limitations.length} 條（前 6 條）`);
for (const line of output.limitations.slice(0, 6)) {
  console.log(`  - ${line}`);
}

console.log('');
console.log(`【資料來源】${sources.length} 筆`);
for (const source of sources) {
  console.log(`  ${source.organization ?? source.sourceId}　${source.url ?? ''}`);
}

console.log('');
console.log(
  `SUMMARY elapsedMs=${elapsed} evidence=${context.evidence.length} answerChars=${answerChars} ` +
    `blocks=${blocks.length} basis=${output.basis.length} webRefs=${output.webReferences.length} ` +
    `sufficiency=${output.dataSufficiency}`,
);
