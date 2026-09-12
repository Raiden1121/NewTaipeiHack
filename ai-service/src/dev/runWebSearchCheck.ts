/**
 * 端到端驗證上網搜尋：`npm run dev:websearch-check`
 *
 * 打真的 Tavily（keyless，不需要 API key）＋ 真的 Bedrock。
 *
 * 兩個情境刻意都是「資料管線完全沒有 evidence」，因為那正是這個功能存在的理由：
 * DB 查不到的時候使用者按下開關，應該要真的搜到東西。
 *
 * 預期結果：
 *   A（開啟搜尋）→ dataSufficiency=partial、basis 為空、webReferences 有內容、
 *                  limitations 明確說「沒有官方統計、僅來自網路」、sources 有真實網址
 *   B（關閉搜尋）→ dataSufficiency=insufficient、四塊全空
 */
import { createBedrockClientFromEnv, MockBedrockClient } from '../bedrock/client.js';
import { createWebSearchProviderFromEnv } from '../websearch/factory.js';
import { dataQa } from '../handlers/dataQa.js';
import { formatSourceAttributions } from '../types/sourceAttribution.js';
import type { AiRequestContext } from '../types/aiEvidence.js';

const question = '新北市青年局有哪些青年創業基地？提供什麼資源？';

function contextWith(enabled: boolean): AiRequestContext {
  return {
    question,
    focusDistrict: null,
    focusArea: 'resources',
    // 刻意完全沒有 evidence：模擬 DB 查不到的情況。
    evidence: [],
    knownLimitations: [],
    webFindings: [],
    webSearch: { enabled, contextSize: 'low' },
  };
}

const client = createBedrockClientFromEnv();
if (client instanceof MockBedrockClient) {
  console.error('要驗證真實行為，請先設定好 .env 的模型與 region。');
  process.exit(1);
}

const provider = createWebSearchProviderFromEnv();
console.log(`模型：${client.description}`);
console.log(`搜尋：${provider.description}`);
console.log(`問題：${question}\n`);

let failures = 0;

// ---- 情境 A：開啟搜尋 ----
console.log('='.repeat(70));
console.log('A. 沒有 evidence + 開啟上網搜尋');
console.log('='.repeat(70));

const startedA = Date.now();
const resultA = await dataQa(client, contextWith(true), provider);
console.log(`耗時 ${Date.now() - startedA} ms\n`);

console.log(`dataSufficiency : ${resultA.output.dataSufficiency}`);
console.log(`basis           : ${resultA.output.basis.length} 筆（預期 0）`);
console.log(`webReferences   : ${resultA.output.webReferences.length} 筆`);
const conclusionsA =
  resultA.output.issues.length +
  resultA.output.strengths.length +
  resultA.output.resourceGaps.length +
  resultA.output.policyDirections.length;
console.log(`結論條數        : ${conclusionsA}`);

console.log('\n【內容】');
for (const line of [
  ...resultA.output.issues,
  ...resultA.output.strengths,
  ...resultA.output.resourceGaps,
  ...resultA.output.policyDirections,
]) {
  console.log(`  - ${line}`);
}

console.log('\n【資料限制】');
for (const line of resultA.output.limitations) {
  console.log(`  - ${line}`);
}

console.log('\n【資料來源】');
console.log(formatSourceAttributions(resultA.sources));

if (resultA.output.basis.length !== 0) {
  console.error('\n❌ basis 應該為空（沒有任何 evidence）');
  failures += 1;
}
if (resultA.output.webReferences.length === 0 && conclusionsA > 0) {
  console.error('\n❌ 有結論卻沒有引用任何網路來源');
  failures += 1;
}
if (resultA.output.dataSufficiency === 'sufficient') {
  console.error('\n❌ 用了網路資料不可宣稱 sufficient');
  failures += 1;
}
if (resultA.sources.length > 0 && !resultA.sources.every((source) => source.kind === 'web')) {
  console.error('\n❌ 來源的 kind 應該全部是 web');
  failures += 1;
}
if (resultA.output.webReferences.length > 0 && failures === 0) {
  console.log('\n✅ 純網路回答的形狀正確');
}

// ---- 情境 B：關閉搜尋 ----
console.log(`\n${'='.repeat(70)}`);
console.log('B. 沒有 evidence + 關閉上網搜尋');
console.log('='.repeat(70));

const startedB = Date.now();
const resultB = await dataQa(client, contextWith(false), provider);
console.log(`耗時 ${Date.now() - startedB} ms（預期很快，因為不呼叫模型）\n`);
console.log(`dataSufficiency : ${resultB.output.dataSufficiency}`);
console.log(`sources         : ${resultB.sources.length} 筆`);
console.log('\n【資料限制】');
for (const line of resultB.output.limitations) {
  console.log(`  - ${line}`);
}

if (resultB.output.dataSufficiency !== 'insufficient') {
  console.error(`\n❌ 關閉搜尋且無 evidence 時應該是 insufficient，實際 ${resultB.output.dataSufficiency}`);
  failures += 1;
} else {
  console.log('\n✅ 關閉搜尋時正確回報資料不足');
}

console.log(`\n${'='.repeat(70)}`);
if (failures > 0) {
  console.error(`${failures} 項未通過`);
  process.exit(1);
}
console.log('全部通過');
