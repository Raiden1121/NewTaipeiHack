/**
 * shared 的對外入口。
 *
 * `PeriodType` / `YouthEligibility` 刻意只從 `metrics.ts` 匯出一次。
 *
 * 這兩個型別原本 `metrics.ts` 與 `aiContract.ts` 各自宣告了一份，值完全相同
 * （`'day' | 'month' | 'year' | 'snapshot'`、`'eligible' | 'proxy_only' |
 * 'context_only'`）—— 因為兩邊都是照 data-pipeline 的欄位 1:1 對過來的，
 * 不是有人協調過。用 `export *` 疊起來雖然編得過（ES 規則讓明確 re-export
 * 蓋過 star export），但 `YouthEligibility` 會靜默地以其中一份為準，
 * 哪天有人只改了另一份，壞掉的地方會離改動點很遠。
 *
 * 所以定義留在 `metrics.ts`（先進 main 的那份），`aiContract.ts` 從那裡
 * import。誰改都會撞在編譯期。
 */
export type { MetricStatus, MetricValue, PeriodType, YouthEligibility } from './metrics.js';
export * from './aiContract.js';
export * from './aiContextTable.js';
