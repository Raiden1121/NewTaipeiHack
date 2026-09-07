import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import KpiSummaryRow from "./KpiSummaryRow";
import { useDistrictSummary } from "../hooks/useDistrictSummary";

vi.mock("../hooks/useDistrictSummary");
const mockedUseDistrictSummary = vi.mocked(useDistrictSummary);

const SAMPLE_DISTRICTS = [
  {
    id: "A",
    name: "甲",
    youthPopulation: 1000,
    opportunityIndex: 80,
    retentionRiskLevel: "low" as const,
    youthParticipationIndex: 60,
    fertilityRate: 40,
    policySupportScore: 70,
  },
  {
    id: "B",
    name: "乙",
    youthPopulation: 2000,
    opportunityIndex: 60,
    retentionRiskLevel: "high" as const,
    youthParticipationIndex: 50,
    fertilityRate: 42,
    policySupportScore: 55,
  },
  {
    id: "C",
    name: "丙",
    youthPopulation: 1500,
    opportunityIndex: 70,
    retentionRiskLevel: "high" as const,
    youthParticipationIndex: 55,
    fertilityRate: 41,
    policySupportScore: 60,
  },
];

describe("KpiSummaryRow", () => {
  it("renders skeleton placeholders while loading", () => {
    mockedUseDistrictSummary.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<KpiSummaryRow />);
    expect(screen.getByTestId("kpi-skeleton")).toBeInTheDocument();
  });

  it("renders an inline error state with a working reload button", () => {
    const refetch = vi.fn();
    mockedUseDistrictSummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("模擬 KPI 資料失敗"),
      refetch,
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<KpiSummaryRow />);
    expect(screen.getByText("模擬 KPI 資料失敗")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新載入" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("renders aggregated KPI values and the most common retention risk level", () => {
    mockedUseDistrictSummary.mockReturnValue({
      data: SAMPLE_DISTRICTS,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<KpiSummaryRow />);
    expect(screen.getByText("新北市青年人口 4,500 人")).toBeInTheDocument();
    expect(screen.getByText("高風險")).toBeInTheDocument();
  });
});
