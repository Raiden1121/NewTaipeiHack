import { describe, expect, it } from 'vitest';
import { REASONING_PROCEDURE, UNIT_HANDLING_RULES } from '../src/prompts/reasoningProcedure.js';
import { buildDataExplanationPrompt } from '../src/prompts/dataExplanation.js';
import { buildDataQaPrompt } from '../src/prompts/dataQa.js';
import { buildPolicyCopilotPrompt } from '../src/prompts/policyCopilot.js';
import { StructuredOutputSchema } from '../src/types/structuredOutput.js';
import { FEW_SHOT_INSUFFICIENT_OUTPUT } from '../src/prompts/fewShotExample.js';
import type { AiContext } from '../src/types/aiEvidence.js';
import { makeEvidence } from './helpers.js';

const context: AiContext = {
  question: '板橋區青年薪資水準如何？',
  focusDistrict: '板橋區',
  focusArea: 'employment',
  evidence: [makeEvidence()],
  knownLimitations: [],
  webFindings: [],
};

const builders = [
  ['dataExplanation', () => buildDataExplanationPrompt(context)],
  ['dataQa', () => buildDataQaPrompt(context)],
  ['policyCopilot', () => buildPolicyCopilotPrompt(context)],
] as const;

/**
 * 思考程序如果只寫在一個功能的 prompt 裡，另兩個功能就會有不同的行為 ——
 * 而那種不一致在 demo 現場最難解釋。所以三個功能都要有。
 */
describe('三個功能都必須帶上思考程序', () => {
  for (const [name, build] of builders) {
    it(`${name} 的 system prompt 含思考程序`, () => {
      expect(build().system).toContain(REASONING_PROCEDURE);
    });

    it(`${name} 的 system prompt 含單位處理規則`, () => {
      expect(build().system).toContain(UNIT_HANDLING_RULES);
    });
  }

  /**
   * 順序有意義：先給程序、再給禁止事項。只有禁止事項時，模型仍然可以
   * 「先寫結論再回頭湊 basis」—— 那個順序寫出來的東西表面合規但實質是先有立場。
   */
  for (const [name, build] of builders) {
    it(`${name} 的思考程序排在禁止事項之前`, () => {
      const system = build().system;
      expect(system.indexOf('思考程序')).toBeGreaterThan(-1);
      expect(system.indexOf('思考程序')).toBeLessThan(system.indexOf('規則（務必遵守'));
    });
  }
});

describe('REASONING_PROCEDURE 內容', () => {
  it('五個步驟都在，且要求依序執行', () => {
    for (const step of ['第 1 步', '第 2 步', '第 3 步', '第 4 步', '第 5 步']) {
      expect(REASONING_PROCEDURE).toContain(step);
    }
    expect(REASONING_PROCEDURE).toContain('不可跳步');
    expect(REASONING_PROCEDURE).toContain('不可先寫結論再回頭找依據');
  });

  it('明確給出 dataSufficiency 三個值的判斷標準，而不是讓模型憑感覺', () => {
    expect(REASONING_PROCEDURE).toContain('不要憑感覺');
    for (const level of ['insufficient', 'partial', 'sufficient']) {
      expect(REASONING_PROCEDURE).toContain(level);
    }
    // 最關鍵的那條規則：列出缺什麼就不能宣稱充足。
    expect(REASONING_PROCEDURE).toContain('missingForQuestion 非空就至少是 partial');
  });

  it('要求盤點時區分 eligible 與 context_only', () => {
    // 指標清單改由程式盤點之後，這裡不再出現 youthSpecificMetrics /
    // contextOnlyMetrics 這兩個欄位名 —— 但**區分的要求必須留著**，
    // 因為那是模型解讀資料時的判斷依據，不是輸出格式。
    expect(REASONING_PROCEDURE).toContain('eligible');
    expect(REASONING_PROCEDURE).toContain('context_only');
    expect(REASONING_PROCEDURE).toContain('proxy_only');
  });

  it('明確叫模型不要把指標逐條列出來（那佔了 35% 的輸出）', () => {
    expect(REASONING_PROCEDURE).toContain('不需要也不能把指標逐條列出來');
    expect(REASONING_PROCEDURE).toContain('missingForQuestion');
  });

  it('仍然要求 limitations 只寫新的限制，不重複抄寫既知限制', () => {
    expect(REASONING_PROCEDURE).toContain('沒有重複抄寫');
  });

  it('資料不足時明確要求停止，不要硬答', () => {
    expect(REASONING_PROCEDURE).toContain('然後停止');
    expect(REASONING_PROCEDURE).toContain('誠實說無法回答，比硬答有價值');
  });

  it('第 5 步的自我檢查涵蓋所有硬性不變式', () => {
    // 這些對應 StructuredOutputSchema 的 superRefine 與 runFeature 的驗證。
    // prompt 沒提到的規則，模型只能靠重試才會發現，那是浪費一次呼叫。
    for (const check of [
      'basis 找到對應的 evidenceId',
      '沒有自己組的',
      '加總、平均、相除',
      '沒有自行換算單位',
      'missingForQuestion 非空時',
      '資料提供者',
      '既知限制',
      'disclaimer',
    ]) {
      expect(REASONING_PROCEDURE, `自我檢查缺少：${check}`).toContain(check);
    }
  });
});

/**
 * 單位規則是為了修一個**實測抓到的真實錯誤**：模型把 `value=220101 unit=TWD_thousand`
 * 寫成「約 2 億 2,010 萬千元」—— 換算對了但單位標籤沿用原本的，差 1000 倍。
 */
describe('UNIT_HANDLING_RULES', () => {
  it('要求直接使用 unit 原值，不要自行換算', () => {
    expect(UNIT_HANDLING_RULES).toContain('不要自行換算單位');
  });

  it('允許換算但要求同時寫出原值，讓人可以核對', () => {
    expect(UNIT_HANDLING_RULES).toContain('必須同時寫出原值與換算後的值');
    expect(UNIT_HANDLING_RULES).toContain('不要換算後還沿用原本的單位');
  });

  it('unit 為 null 時不可自己猜', () => {
    expect(UNIT_HANDLING_RULES).toContain('不要自己猜單位');
  });

  it('列出真實資料實際出現的單位', () => {
    // 這些是實測 curated 輸出裡真的出現過的值，不是想像的。
    for (const unit of ['TWD_thousand', 'people', 'positions', 'person_times']) {
      expect(UNIT_HANDLING_RULES).toContain(unit);
    }
  });
});

/**
 * insufficient 範例是最重要的那個 —— 模型天生傾向「總得說點什麼」，
 * 光靠文字規則講「資料不足要說不知道」效果有限。
 */
describe('資料不足的 few-shot 範例', () => {
  it('本身符合 schema（範例違規的話模型會照著違規）', () => {
    expect(() => StructuredOutputSchema.parse(FEW_SHOT_INSUFFICIENT_OUTPUT)).not.toThrow();
  });

  it('四塊結論全空，示範「不要硬答」', () => {
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.issues).toEqual([]);
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.strengths).toEqual([]);
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.resourceGaps).toEqual([]);
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.policyDirections).toEqual([]);
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.basis).toEqual([]);
  });

  it('limitations 具體說出缺哪個指標，不是只寫「資料有限」', () => {
    const text = FEW_SHOT_INSUFFICIENT_OUTPUT.limitations.join('\n');
    expect(text).toContain('薪資');
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.evidenceReview.missingForQuestion.length).toBeGreaterThan(0);
  });

  it('明確示範不用其他地區或年度的資料代答', () => {
    expect(FEW_SHOT_INSUFFICIENT_OUTPUT.limitations.join('\n')).toContain('不會引用其他地區');
  });

  it('兩個範例都出現在 prompt 裡，且標明 A / B', () => {
    const system = buildDataExplanationPrompt(context).system;
    expect(system).toContain('範例 A');
    expect(system).toContain('範例 B');
    expect(system).toContain('dataSufficiency=insufficient');
  });
});

describe('Q&A 的比較規則', () => {
  it('允許比大小，禁止算差值', () => {
    const system = buildDataQaPrompt(context).system;
    expect(system).toContain('直接比大小（誰多誰少、誰最高）是允許的');
    expect(system).toContain('算差值');
    expect(system).toContain('僅提供原始數字');
  });

  it('缺區的排名是誤導，必須列出缺哪些區', () => {
    expect(buildDataQaPrompt(context).system).toContain('少了幾區的排名是誤導');
  });
});

describe('Policy Copilot 的複合指標限制', () => {
  it('說明複合指標未產出，且幾乎不可能是 sufficient', () => {
    const system = buildPolicyCopilotPrompt(context).system;
    expect(system).toContain('Opportunity Index');
    expect(system).toContain('幾乎不可能是 sufficient');
  });

  it('禁止自己估資源缺口的數字', () => {
    expect(buildPolicyCopilotPrompt(context).system).toContain('不可以自己估一個數字或比例');
  });
});
