import { describe, expect, it } from 'vitest';
import { StructuredOutputSchema, findUnknownEvidenceIds } from '../src/types/structuredOutput.js';
import { makeEvidenceReview, makeOutput } from './helpers.js';

const validOutput = makeOutput();

describe('StructuredOutputSchema', () => {
  it('接受符合格式的內容', () => {
    expect(() => StructuredOutputSchema.parse(validOutput)).not.toThrow();
  });

  it('disclaimer 沒有包含固定關鍵字時要拒絕', () => {
    expect(() => StructuredOutputSchema.parse({ ...validOutput, disclaimer: '僅供參考' })).toThrow();
  });

  it('缺少 limitations 欄位時要拒絕（不可省略，即使是空陣列）', () => {
    const { limitations: _omit, ...rest } = validOutput;
    expect(() => StructuredOutputSchema.parse(rest)).toThrow();
  });

  it('缺少 dataSufficiency 時要拒絕', () => {
    const { dataSufficiency: _omit, ...rest } = validOutput;
    expect(() => StructuredOutputSchema.parse(rest)).toThrow();
  });

  it('缺少 evidenceReview 時要拒絕：思考步驟不是選填', () => {
    const { evidenceReview: _omit, ...rest } = validOutput;
    expect(() => StructuredOutputSchema.parse(rest)).toThrow(/evidenceReview/);
  });
});

/**
 * 這一組是整個 schema 最重要的部分：擋掉「有結論但沒有依據」與「說資料不足卻還是給結論」
 * 這兩種自相矛盾的輸出。這正是 LLM 在資料不足時最容易產生的失敗模式。
 */
describe('有結論就必須有依據', () => {
  it('有 issues 但 basis 為空時要拒絕', () => {
    expect(() => StructuredOutputSchema.parse(makeOutput({ basis: [] }))).toThrow(/basis/);
  });

  it('policyDirections 有內容但 basis 為空時也要拒絕', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({ issues: [], policyDirections: ['建議補齊分區職缺彙總指標'], basis: [] }),
      ),
    ).toThrow(/basis/);
  });

  it('四塊全空且 basis 為空時可以通過（前提是標示資料不足）', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'insufficient',
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺薪資資料'] }),
          issues: [],
          basis: [],
          limitations: ['目前沒有可引用的資料。'],
        }),
      ),
    ).not.toThrow();
  });
});

describe('dataSufficiency 與內容必須一致', () => {
  it('標示 insufficient 卻還是給結論時要拒絕', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'insufficient',
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺薪資資料'] }),
          limitations: ['資料不足'],
        }),
      ),
    ).toThrow(/insufficient/);
  });

  it('標示 partial 卻沒有說明缺什麼時要拒絕', () => {
    expect(() =>
      StructuredOutputSchema.parse(makeOutput({ dataSufficiency: 'partial', limitations: [] })),
    ).toThrow(/limitations/);
  });

  it('標示 sufficient 時 limitations 允許為空', () => {
    expect(() =>
      StructuredOutputSchema.parse(makeOutput({ dataSufficiency: 'sufficient', limitations: [] })),
    ).not.toThrow();
  });
});

/**
 * evidenceReview 存在的主要價值：讓「充足度判斷」變成可檢查的，
 * 而不是模型隨口給一個標籤。這三條是模型最常見的自我矛盾。
 */
describe('盤點結果與充足度判斷必須一致', () => {
  it('自己列出缺什麼卻宣稱 sufficient 時要拒絕', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'sufficient',
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺各區薪資中位數'] }),
        }),
      ),
    ).toThrow(/sufficient/);
  });

  it('列出缺什麼但標 partial 是允許的', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'partial',
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺各區薪資中位數'] }),
          limitations: ['缺各區薪資中位數'],
        }),
      ),
    ).not.toThrow();
  });

  it('標 insufficient 卻說不出缺什麼時要拒絕：等於沒有真的判斷過', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'insufficient',
          evidenceReview: makeEvidenceReview({ missingForQuestion: [] }),
          issues: [],
          basis: [],
          limitations: ['資料不足'],
        }),
      ),
    ).toThrow(/missingForQuestion/);
  });

  /**
   * 原本這裡有一條「availableMetrics 為空卻寫出結論 → 拒絕」。
   *
   * 那條規則抓的是「模型說自己沒看到指標卻還是寫結論」這種自我矛盾。但
   * `availableMetrics` 現在是程式從 `context.evidence` 盤點的（見
   * `handlers/evidenceInventory.ts`），模型碰不到，所以它不可能在這件事上矛盾。
   *
   * 留著反而有害：模型的原始回應裡那個欄位一定是空的（它不輸出），
   * 於是每個有結論的正常回應都會被誤判成違規。下面這個測試就是在鎖住這件事。
   */
  it('模型沒輸出指標清單時不可以被誤判成違規（那三個欄位由程式填）', () => {
    const review: Record<string, unknown> = {
      missingForQuestion: ['缺少就業面向資料'],
    };

    const parsed = StructuredOutputSchema.parse(
      makeOutput({ dataSufficiency: 'partial', evidenceReview: review as never }),
    );

    expect(parsed.evidenceReview.availableMetrics).toEqual([]);
    expect(parsed.evidenceReview.youthSpecificMetrics).toEqual([]);
    expect(parsed.evidenceReview.contextOnlyMetrics).toEqual([]);
    expect(parsed.evidenceReview.missingForQuestion).toEqual(['缺少就業面向資料']);
  });

  it('missingForQuestion 仍然是必填（那是唯一需要模型判斷的欄位）', () => {
    const review: Record<string, unknown> = { ...makeEvidenceReview() };
    delete review.missingForQuestion;

    expect(() =>
      StructuredOutputSchema.parse(makeOutput({ evidenceReview: review as never })),
    ).toThrow();
  });

  it('三個列舉欄位可以省略，因為它們由程式盤點', () => {
    for (const field of ['availableMetrics', 'youthSpecificMetrics', 'contextOnlyMetrics'] as const) {
      const review: Record<string, unknown> = { ...makeEvidenceReview() };
      delete review[field];
      expect(() =>
        StructuredOutputSchema.parse(makeOutput({ evidenceReview: review as never })),
      ).not.toThrow();
    }
  });

  /**
   * 這條是改動後最容易出事的地方，所以特別鎖住。
   *
   * 模型現在不需要把既知限制抄進 limitations，所以在「既知限制已經說明了缺什麼、
   * 模型沒有額外要補的」這種正常情況下，模型的 limitations 會是空的。
   * 如果規則還是「not sufficient → limitations 不可為空」，那個合法輸出會被擋掉。
   */
  it('not sufficient 時，用 missingForQuestion 說明缺什麼也算交代', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'partial',
          limitations: [],
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['缺少交通可及性資料'] }),
        }),
      ),
    ).not.toThrow();
  });

  it('not sufficient 卻兩邊都空，還是要拒絕', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'partial',
          limitations: [],
          evidenceReview: makeEvidenceReview({ missingForQuestion: [] }),
        }),
      ),
    ).toThrow(/missingForQuestion/);
  });
});

/**
 * evidenceId 是否真的存在沒辦法寫進 schema（schema 看不到當次 context），
 * 但這是「不可捏造」最容易被違反的地方，所以必須有獨立檢查。
 */
describe('findUnknownEvidenceIds', () => {
  const output = StructuredOutputSchema.parse(validOutput);

  it('basis 只引用存在的 evidenceId 時回空陣列', () => {
    expect(findUnknownEvidenceIds(output, ['population:11507:1:youth_18_35_total'])).toEqual([]);
  });

  it('引用了不存在的 evidenceId 時要抓出來', () => {
    expect(findUnknownEvidenceIds(output, ['population:11507:0:people_total'])).toEqual([
      'population:11507:1:youth_18_35_total',
    ]);
  });

  it('完全沒有 evidence 時，所有引用都算不存在', () => {
    expect(findUnknownEvidenceIds(output, [])).toHaveLength(1);
  });
});
