import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import YouthTopicWordCloud from "./YouthTopicWordCloud";
import { useYouthKeywordFrequency } from "@/lib/api/queries";

vi.mock("@/lib/api/queries");
const mockedUseYouthKeywordFrequency = vi.mocked(useYouthKeywordFrequency);

function mockQuery(data: unknown) {
  mockedUseYouthKeywordFrequency.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useYouthKeywordFrequency>);
}

const SAMPLE_ANALYSIS = {
  analysis_id: "youth-keyword-frequency",
  period_scope: "all_available",
  source_periods: {
    youth_council_minutes: ["110", "112", "114"],
    join_proposals: ["109", "110", "115"],
  },
  keywords: [
    { term: "心理", weight: 5 },
    { term: "健康", weight: 4 },
  ],
};

describe("YouthTopicWordCloud", () => {
  it("renders canonical keywords[].term with the covered year range", () => {
    mockQuery(SAMPLE_ANALYSIS);

    render(<YouthTopicWordCloud />);

    expect(screen.getByText("心理")).toBeInTheDocument();
    expect(screen.getByText("健康")).toBeInTheDocument();
    expect(screen.getByText(/民國 109–115 年/)).toBeInTheDocument();
  });

  it("shows the error state instead of crashing when keywords are missing", () => {
    mockQuery({ analysis_id: "youth-keyword-frequency", period_scope: "all_available", source_periods: {} });

    render(<YouthTopicWordCloud />);

    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
