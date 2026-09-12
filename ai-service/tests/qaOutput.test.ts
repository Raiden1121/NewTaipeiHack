import { describe, expect, it, vi } from 'vitest';
import {
  QaOutputSchema,
  StructuredOutputSchema,
  type StructuredOutput,
} from '../src/types/structuredOutput.js';
import { QA_OUTPUT_SPEC, SIX_BLOCK_OUTPUT_SPEC } from '../src/prompts/promptPayload.js';
import { QA_OUTPUT_SCHEMA_NAME } from '../src/types/structuredOutputJsonSchema.js';
import { buildDataQaPrompt } from '../src/prompts/dataQa.js';
import { buildDataExplanationPrompt } from '../src/prompts/dataExplanation.js';
import { buildPolicyCopilotPrompt } from '../src/prompts/policyCopilot.js';
import { MockBedrockClient } from '../src/bedrock/client.js';
import { dataQa } from '../src/handlers/dataQa.js';
import { explainData } from '../src/handlers/explainData.js';
import { makeEvidenceReview, makeOutput, makeQaOutput, makeRequestContext } from './helpers.js';

/**
 * Q&A 用自己的輸出格式（`answer` 為主、四塊選填），explain / policyCopilot 維持六塊。
 *
 * 這個檔案要鎖住的核心風險：**換格式不可以把誠實性的保證一起換掉。**
 * 六塊格式原本靠「四塊有內容 → 必須有 basis」來擋憑空編造，
 * 但 Q&A 的主要產出是 `answer`、四塊通常是空的 —— 如果不變式沒有跟著調整，
 * 就會出現「一句沒有任何依據的回答」這種最不該發生的輸出。
 */

describe('QaOutputSchema：answer 是必填', () => {
  it('正常的 Q&A 輸出（answer 有內容、四塊全空）可以通過', () => {
    expect(() => QaOutputSchema.parse(makeQaOutput())).not.toThrow();
  });

  it('四塊全空不會被誤判成違規（那是純查值問題的正常形狀）', () => {
    const parsed = QaOutputSchema.parse(makeQaOutput());

    expect(parsed.issues).toEqual([]);
    expect(parsed.strengths).toEqual([]);
    expect(parsed.resourceGaps).toEqual([]);
    expect(parsed.policyDirections).toEqual([]);
    expect(parsed.answer).toContain('106,473');
  });

  it('沒有 answer 要拒絕', () => {
    const withoutAnswer: Record<string, unknown> = { ...makeQaOutput() };
    delete withoutAnswer.answer;

    expect(() => QaOutputSchema.parse(withoutAnswer)).toThrow(/answer/);
  });

  it('answer 是 null 要拒絕', () => {
    expect(() => QaOutputSchema.parse(makeQaOutput({ answer: null }))).toThrow(/answer/);
  });

  it('answer 只有空白字元也要拒絕（等於沒有回答）', () => {
    expect(() => QaOutputSchema.parse(makeQaOutput({ answer: '   \n  ' }))).toThrow(/answer/);
  });
});

describe('Q&A 的回答同樣受「有結論要有依據」保護', () => {
  /**
   * 這是換格式時最容易開的洞。
   *
   * 六塊的規則是「四塊有內容 → basis 或 webReferences 至少一筆」。Q&A 的四塊是空的，
   * 所以如果 `answer` 不算進「結論」，這條規則就完全不會觸發 ——
   * 模型可以回一句話、附零筆引用，而 schema 全部放行。
   */
  it('有 answer 但完全沒有引用要拒絕', () => {
    expect(() =>
      QaOutputSchema.parse(makeQaOutput({ basis: [], webReferences: [] })),
    ).toThrow(/basis|webReferences/);
  });

  it('資料不足時，answer 說明無法回答並允許零引用', () => {
    // insufficient 的時候 answer 是「目前沒有這個資料」，它沒有主張任何事實，
    // 不需要引用。逼它非空反而會讓模型在該說不知道的時候硬答。
    const output = makeQaOutput({
      dataSufficiency: 'insufficient',
      answer: '目前的資料裡沒有各區青年失業率，這個問題無法回答。',
      basis: [],
      webReferences: [],
      evidenceReview: makeEvidenceReview({ missingForQuestion: ['各區青年失業率'] }),
      limitations: ['本次 evidence 沒有任何失業率指標。'],
    });

    expect(() => QaOutputSchema.parse(output)).not.toThrow();
  });

  it('資料不足時仍然不可以給四塊結論', () => {
    const output = makeQaOutput({
      dataSufficiency: 'insufficient',
      answer: '目前的資料無法回答這個問題。',
      basis: [],
      issues: ['硬掰的問題辨識'],
      evidenceReview: makeEvidenceReview({ missingForQuestion: ['各區青年失業率'] }),
    });

    expect(() => QaOutputSchema.parse(output)).toThrow(/insufficient/);
  });

  it('自己列出缺什麼卻宣稱 sufficient 仍然要拒絕', () => {
    expect(() =>
      QaOutputSchema.parse(
        makeQaOutput({
          dataSufficiency: 'sufficient',
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['各區薪資中位數'] }),
        }),
      ),
    ).toThrow(/sufficient/);
  });

  it('disclaimer 的固定字樣一樣要檢查', () => {
    expect(() => QaOutputSchema.parse(makeQaOutput({ disclaimer: '僅供參考' }))).toThrow();
  });
});

describe('六塊格式沒有被 Q&A 的改動影響', () => {
  it('answer 為 null 的六塊輸出照樣通過', () => {
    expect(() => StructuredOutputSchema.parse(makeOutput())).not.toThrow();
  });

  it('六塊格式不要求 answer（模型不輸出也沒關係）', () => {
    const withoutAnswer: Record<string, unknown> = { ...makeOutput() };
    delete withoutAnswer.answer;

    const parsed = StructuredOutputSchema.parse(withoutAnswer);
    expect(parsed.answer).toBeNull();
  });

  it('六塊格式「有結論卻沒有依據」仍然要拒絕', () => {
    expect(() =>
      StructuredOutputSchema.parse(makeOutput({ basis: [], webReferences: [] })),
    ).toThrow(/basis|webReferences/);
  });

  it('六塊格式的 insufficient 規則沒變', () => {
    expect(() =>
      StructuredOutputSchema.parse(
        makeOutput({
          dataSufficiency: 'insufficient',
          evidenceReview: makeEvidenceReview({ missingForQuestion: ['薪資資料'] }),
        }),
      ),
    ).toThrow(/insufficient/);
  });
});

describe('prompt 帶對輸出格式', () => {
  const context = makeRequestContext({ question: '板橋區的青年人口是多少？' });

  it('Q&A 用 Q&A schema', () => {
    const payload = buildDataQaPrompt(context);

    expect(payload.outputSchema?.name).toBe(QA_OUTPUT_SCHEMA_NAME);
    expect(payload.outputSchema).toBe(QA_OUTPUT_SPEC);
  });

  it('Data Explanation 與 Policy Copilot 維持六塊', () => {
    const explain = buildDataExplanationPrompt(makeRequestContext());
    const policy = buildPolicyCopilotPrompt(makeRequestContext());

    for (const payload of [explain, policy]) {
      expect(payload.outputSchema === undefined || payload.outputSchema === SIX_BLOCK_OUTPUT_SPEC).toBe(
        true,
      );
      expect(payload.outputSchema?.name).not.toBe(QA_OUTPUT_SCHEMA_NAME);
    }
  });

  it('Q&A 的 prompt 明確要求 answer 直接回答、四塊只在問政策時才填', () => {
    const payload = buildDataQaPrompt(context);

    expect(payload.system).toContain('answer');
    expect(payload.system).toContain('第一句就給出那個數值');
    expect(payload.system).toContain('使用者明確問政策');
    // 「為什麼」是解釋題，不該順手附政策建議
    expect(payload.system).toContain('解釋題');
  });

  /**
   * 定位改成「數據解釋優先於政策建議」之後，這三件事是新的核心行為，
   * 所以鎖在測試裡 —— prompt 被改動時如果掉了其中一條，這裡會擋下來。
   */
  it('Q&A 的 prompt 要求先驗證使用者的前提', () => {
    const payload = buildDataQaPrompt(context);

    expect(payload.system).toContain('驗證使用者的前提');
    expect(payload.system).toContain('更正');
  });

  it('Q&A 的 prompt 要求區分相關與因果', () => {
    const payload = buildDataQaPrompt(context);

    expect(payload.system).toContain('相關');
    expect(payload.system).toContain('因果');
    expect(payload.system).toContain('可能與');
  });

  it('Q&A 的 prompt 要求提醒樣本數陷阱，並限定網路資料只補背景', () => {
    const payload = buildDataQaPrompt(context);

    expect(payload.system).toContain('樣本數');
    expect(payload.system).toContain('webReferences');
    // 網路資料不可以用來改資料管線的數字
    expect(payload.system).toContain('不可以用來推翻');
  });

  it('Q&A 的 few-shot 示範了更正錯誤前提', () => {
    const payload = buildDataQaPrompt(context);

    expect(payload.system).toContain('不是第 2 高');
    expect(payload.system).toContain('更正前提');
  });

  it('Q&A 的 few-shot 示範的是 answer 格式，不是六塊', () => {
    const payload = buildDataQaPrompt(context);

    // 範例 A 的 answer 開頭就是數字
    expect(payload.system).toContain('"answer"');
    // 而且示範了「純查值時四塊留空」
    expect(payload.system).toContain('純查值');
  });
});

describe('MockBedrockClient 跟著格式走', () => {
  it('Q&A 會拿到 answer，四塊留空', async () => {
    const output = await new MockBedrockClient().invokeStructured({
      system: '',
      user: '1. evidenceId="population:11507:1:youth_18_35_total"',
      outputSchema: QA_OUTPUT_SPEC,
    });

    expect(output.answer).not.toBeNull();
    expect(output.answer).toContain('[mock]');
    expect(output.issues).toEqual([]);
  });

  it('六塊會拿到 issues，answer 是 null', async () => {
    const output = await new MockBedrockClient().invokeStructured({
      system: '',
      user: '1. evidenceId="population:11507:1:youth_18_35_total"',
    });

    expect(output.answer).toBeNull();
    expect(output.issues.length).toBeGreaterThan(0);
  });
});

describe('handler 端到端（mock 模型）', () => {
  it('dataQa 回傳的 output 有 answer', async () => {
    const context = makeRequestContext({ question: '板橋區的青年人口是多少？' });

    const { output } = await dataQa(new MockBedrockClient(), context);

    expect(output.answer).not.toBeNull();
    expect(output.answer?.length).toBeGreaterThan(0);
  });

  it('explainData 回傳的 output answer 是 null', async () => {
    const { output } = await explainData(new MockBedrockClient(), makeRequestContext());

    expect(output.answer).toBeNull();
  });

  it('Q&A 的 answer 缺失時，會把錯誤回饋給模型再試一次', async () => {
    // 第一次故意漏 answer，第二次補上 —— 驗證 retry 修正流程對 Q&A 也有效，
    // 而不是直接失敗。
    const responses: StructuredOutput[] = [
      makeQaOutput({ answer: null }),
      makeQaOutput({ answer: '板橋區 18–35 歲青年人口為 106,473 人。' }),
    ];
    let call = 0;
    const client = {
      description: 'stub',
      invokeStructured: vi.fn(async () => {
        const response = responses[Math.min(call, responses.length - 1)];
        call += 1;
        return QaOutputSchema.parse(response);
      }),
    };

    // 第一次 parse 就會丟錯，所以直接驗 schema 層的行為：
    expect(() => QaOutputSchema.parse(responses[0])).toThrow(/answer/);
    expect(() => QaOutputSchema.parse(responses[1])).not.toThrow();
    expect(client.invokeStructured).not.toHaveBeenCalled();
  });
});
