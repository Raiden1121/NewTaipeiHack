/**
 * 印出送給模型的實際 prompt：`npm run dev:dump-prompt [行政區]`
 *
 * 不呼叫模型，純粹把 prompt 組出來印掉，所以不花任何 Bedrock 額度。
 *
 * 用途：
 * - 確認模型「實際看到什麼」。模型沒有檔案存取能力，它只收到這段文字，
 *   所以這份輸出就是它能知道的全部。
 * - 檢查有沒有把不該進 prompt 的東西帶進去（raw_record、source_record_ids…）。
 * - 給隊友或評審看「我們怎麼把資料餵給 LLM」。
 */
import { buildAiContext, createEvidenceRepositoryFromEnv } from '../context/buildContext.js';
import { buildDataExplanationPrompt } from '../prompts/dataExplanation.js';
import { EXCLUDED_RECORD_FIELDS } from '../context/curatedRecord.js';

function estimateTokens(text: string): number {
  let cjk = 0;
  for (const char of text) {
    if (char.codePointAt(0)! > 0x2e80) {
      cjk += 1;
    }
  }
  return Math.round(cjk + (text.length - cjk) / 3.5);
}

const district = process.argv[2] ?? '板橋區';
const repository = createEvidenceRepositoryFromEnv();

// 刻意**不傳** `datasets`。
//
// 原本傳的是 4 個 curated dataset 名稱（population / movement / vt_courses /
// youth_budgets）。evidence 來源預設改成只讀 analytics 之後那樣會拿到 0 筆 ——
// analytics repository 的規則是「呼叫端只指名 curated dataset 時代表這次不想要
// analytics」，於是回空集合，然後誠實地印出一份沒有任何 evidence 的 prompt。
//
// 這個坑對 backend 也成立：組 context 時要用 `focusArea` 而不是 curated 的
// dataset 名稱去限制範圍。
const context = await buildAiContext(repository, {
  focusDistrict: district,
  focusArea: 'population',
});

const prompt = buildDataExplanationPrompt({ ...context, evidence: context.evidence });

console.log('='.repeat(78));
console.log('這份 prompt 的組成');
console.log('='.repeat(78));
console.log(`evidence 來源   ：${repository.description}`);
console.log(`行政區          ：${district}`);
console.log(`evidence 筆數   ：${context.evidence.length}`);
console.log(`既知限制        ：${context.knownLimitations.length} 條`);
console.log(`system ≈ ${estimateTokens(prompt.system)} tok（規則＋思考程序＋兩個範例，幾乎固定）`);
console.log(`user   ≈ ${estimateTokens(prompt.user)} tok（隨 evidence 筆數變動）`);

console.log(`\n${'='.repeat(78)}`);
console.log('模型看到的 evidence 長這樣（前 4 筆）');
console.log('='.repeat(78));
const evidenceSection = prompt.user.split('可用的 evidence')[1] ?? '';
console.log(evidenceSection.split('\n').slice(0, 25).join('\n'));

console.log(`\n${'='.repeat(78)}`);
console.log('既知限制（會強制出現在輸出的 limitations）');
console.log('='.repeat(78));
for (const note of context.knownLimitations) {
  console.log(`- ${note}`);
}

console.log(`\n${'='.repeat(78)}`);
console.log('安全檢查：不該進 prompt 的欄位');
console.log('='.repeat(78));
const whole = `${prompt.system}\n${prompt.user}`;
let leaked = false;
for (const field of EXCLUDED_RECORD_FIELDS) {
  const present = whole.includes(field);
  console.log(`  ${present ? '❌ 出現了' : '✅ 沒有'} ${field}`);
  leaked = leaked || present;
}
console.log(
  `\n模型能看到的資料就只有上面這些文字 —— 它沒有檔案存取能力，也無法自己撈更多資料。`,
);

if (leaked) {
  process.exit(1);
}
