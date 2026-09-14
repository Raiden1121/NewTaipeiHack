import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PolicyDecisionAssistant from "./PolicyDecisionAssistant";

describe("PolicyDecisionAssistant", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends the question to the AI API and renders its answer", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        action: "qa",
        generatedBy: "bedrock(test)",
        output: { answer: "板橋區青年人口約 10 萬人。" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });

    const user = userEvent.setup();
    render(<PolicyDecisionAssistant />);

    await user.type(
      screen.getByPlaceholderText("輸入政策問題，按 Enter 送出"),
      "板橋區有多少青年？",
    );
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByText("板橋區青年人口約 10 萬人。"))
        .toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/ai/query");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      action: "qa",
      question: "板橋區有多少青年？",
      focusArea: "policy",
      webSearch: {
        enabled: true,
        scope: "all",
        contextSize: "low",
      },
    });
  });

  it("uses the trusted search scope when the source toggle is enabled", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        action: "qa",
        generatedBy: "bedrock(test)",
        output: { answer: "這是可信任來源回答。" },
      }),
    });
    vi.stubGlobal("fetch", fetchMock);
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });

    const user = userEvent.setup();
    render(<PolicyDecisionAssistant />);
    await user.click(screen.getByRole("switch", { name: "僅引用可信任來源" }));
    await user.type(
      screen.getByPlaceholderText("輸入政策問題，按 Enter 送出"),
      "八里區的青年薪資如何？",
    );
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(screen.getByText("這是可信任來源回答。"))
        .toBeInTheDocument();
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body)).webSearch.scope).toBe("trusted");
  });

  it("shows the AI Service error message when the API returns a string error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => ({ error: "Bedrock 回應無法通過語意驗證" }),
    }));
    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn(),
    });

    const user = userEvent.setup();
    render(<PolicyDecisionAssistant />);
    await user.type(screen.getByPlaceholderText("輸入政策問題，按 Enter 送出"), "你好");
    await user.keyboard("{Enter}");

    expect(await screen.findByText("AI 回覆失敗：Bedrock 回應無法通過語意驗證"))
      .toBeInTheDocument();
  });
});
