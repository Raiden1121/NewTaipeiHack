import { createHash } from "node:crypto";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiRequestError, askPolicyQuestion } from "./ai";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("askPolicyQuestion", () => {
  it("POST qa 到 /api/ai，並帶 CloudFront OAC 簽章需要的 body SHA-256", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, {
        action: "qa",
        generatedBy: "bedrock(test)",
        output: { answer: "八里區的薪資分數排在前段。" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await askPolicyQuestion("為什麼八里區的青年薪資分數這麼高？", "trusted");

    expect(result).toEqual({ answer: "八里區的薪資分數排在前段。", generatedBy: "bedrock(test)" });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit & { body: string }];
    expect(url).toBe("/api/ai");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      action: "qa",
      question: "為什麼八里區的青年薪資分數這麼高？",
      webSearch: { scope: "trusted" },
    });
    const headers = init.headers as Record<string, string>;
    expect(headers["x-amz-content-sha256"]).toBe(
      createHash("sha256").update(init.body, "utf8").digest("hex"),
    );
  });

  it("伺服器回錯誤 JSON 時帶出錯誤訊息", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(502, { error: "Bedrock 不可用" })));

    const error = await askPolicyQuestion("問題", "all").catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(AiRequestError);
    expect((error as AiRequestError).status).toBe(502);
    expect((error as AiRequestError).message).toContain("Bedrock 不可用");
  });

  it("拿到 HTML（CloudFront 把 403 換成 index.html）時不當成成功", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<!doctype html>", { status: 200, headers: { "content-type": "text/html" } }),
      ),
    );

    await expect(askPolicyQuestion("問題", "all")).rejects.toThrow("AI 服務目前無法使用");
  });

  it("回應沒有 answer 時視為格式錯誤", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, { output: { answer: null } })));

    await expect(askPolicyQuestion("問題", "all")).rejects.toThrow("格式不正確");
  });

  it("網路失敗與逾時給不同的訊息", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(askPolicyQuestion("問題", "all")).rejects.toThrow("無法連線");

    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(Object.assign(new Error("aborted"), { name: "AbortError" })),
    );
    await expect(askPolicyQuestion("問題", "all")).rejects.toThrow("逾時");
  });
});
