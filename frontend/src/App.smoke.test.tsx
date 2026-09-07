import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import App from "./App";

describe("App smoke test", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ objects: {} }),
      }),
    );
  });

  it("renders the loading state before data arrives", () => {
    render(<App />);
    expect(screen.getByText("正在載入地圖資料")).toBeInTheDocument();
  });
});
