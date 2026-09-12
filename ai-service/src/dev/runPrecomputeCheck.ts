/**
 * 驗證預先算真的會被命中：`npm run dev:precompute-check`
 *
 * ## 為什麼需要這支
 *
 * 預先算整套的價值完全押在一件事上：**線上請求算出的 fingerprint，要跟批次
 * 當初寫進去的那個一樣**。對不上就是每次都 miss，等於白做，而且症狀很安靜 ——
 * 回應照樣正確，只是每次都花 50 秒，然後在 API Gateway 那裡被切斷。
 *
 * 這支腳本用一個**呼叫就丟錯的 client**：命中的話它永遠不會被呼叫，
 * 一旦 miss 就會立刻炸出來。用 Mock client 是不行的 —— miss 時它會安靜地
 * 回一份假分析，測試看起來就過了。
 *
 * 用法：
 *   npm run dev:precompute-check                    # 板橋區 / employment
 *   npm run dev:precompute-check -- 八里區 employment
 */
import type { BedrockClient } from '../bedrock/client.js';
import { buildAiContext, createEvidenceRepositoryFromEnv } from '../context/buildContext.js';
import { dispatch } from '../handlers/lambda.js';
import { contextFingerprint } from '../precompute/fingerprint.js';
import { dispatchWithPrecompute, PRECOMPUTABLE_ACTIONS } from '../precompute/servePrecomputed.js';
import { createPrecomputedStoreFromEnv, DisabledPrecomputedStore } from '../precompute/store.js';

const positional = process.argv.slice(2).filter((arg) => !arg.startsWith('--'));
const focusDistrict = positional[0] ?? '板橋區';
const focusArea = positional[1] ?? 'employment';

const store = createPrecomputedStoreFromEnv();
if (store instanceof DisabledPrecomputedStore) {
  console.error('沒有設 AI_PRECOMPUTE_DIR，沒有快取可以驗。先跑 npm run precompute。');
  process.exit(1);
}

/**
 * 被呼叫就代表沒命中。刻意不用 MockBedrockClient：
 * 它會安靜地回一份假分析，讓「其實每次都 miss」看起來像成功。
 */
const poisonClient: BedrockClient = {
  description: 'poison(呼叫到就代表快取沒命中)',
  invokeStructured: async () => {
    throw new Error(
      '快取沒有命中 —— 線上請求的 fingerprint 跟批次寫進去的不一樣。' +
        '常見原因：context 的組法不同（evidence 筆數上限、focusArea、搜尋開關），' +
        '或 analytics 快照換了但沒重跑 npm run precompute。',
    );
  },
};

// 跟批次腳本走同一個來源決定，否則指紋一定對不上（那正是這支要驗的事）。
const repository = createEvidenceRepositoryFromEnv();

const context = await buildAiContext(repository, { focusDistrict, focusArea });
console.log(`快取        : ${store.description}`);
console.log(`行政區／主題: ${focusDistrict} / ${focusArea}`);
console.log(`evidence    : ${context.evidence.length} 筆`);
console.log('');

let failures = 0;

for (const action of PRECOMPUTABLE_ACTIONS) {
  const fingerprint = contextFingerprint(action, context);
  const startedAt = Date.now();
  try {
    const result = await dispatchWithPrecompute(action, dispatch, poisonClient, context, { store });
    const elapsed = Date.now() - startedAt;

    if (result.cache !== 'hit') {
      console.error(`❌ ${action}：cache=${result.cache}（預期 hit）`);
      failures += 1;
      continue;
    }
    console.log(`✅ ${action}`);
    console.log(`   fingerprint : ${fingerprint.slice(0, 16)}…`);
    console.log(`   耗時        : ${elapsed} ms（沒有呼叫模型）`);
    console.log(`   產生於      : ${result.precomputedAt}`);
    console.log(`   basis       : ${result.output.basis.length} 筆　sources ${result.sources.length} 筆`);
    console.log(`   SUMMARY action=${action} cache=hit elapsedMs=${elapsed}`);
  } catch (error) {
    console.error(`❌ ${action}：${error instanceof Error ? error.message : String(error)}`);
    failures += 1;
  }
  console.log('');
}

if (failures > 0) {
  console.error(`${failures} 項未命中`);
  process.exit(1);
}
console.log('全部命中');
