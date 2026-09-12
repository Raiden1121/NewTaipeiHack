import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import KpiSummaryRow from "./KpiSummaryRow";
import { useDashboardOverview } from "@/lib/api/queries";

vi.mock("@/lib/api/queries");
const mockedUseDashboardOverview = vi.mocked(useDashboardOverview);

const SAMPLE_OVERVIEW = {
  kpis: {
    nationalYouthPopulation: 4820000,
    nationalYouthPopulationQuality: "proxy" as const,
    cityYouthPopulationShare: 20.914,
    cityYouthPopulation: 845938,
    cityYouthPopulationYoY: -1.969,
    referenceYearRoc: 114,
  },
};

describe("KpiSummaryRow", () => {
  it("renders skeleton placeholders while loading", () => {
    mockedUseDashboardOverview.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDashboardOverview>);

    render(<KpiSummaryRow />);
    expect(screen.getByTestId("kpi-skeleton")).toBeInTheDocument();
  });

  it("renders an inline error state with a working reload button", () => {
    const refetch = vi.fn();
    mockedUseDashboardOverview.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("模擬 KPI 資料失敗"),
      refetch,
    } as unknown as ReturnType<typeof useDashboardOverview>);

    render(<KpiSummaryRow />);
    expect(screen.getByText("模擬 KPI 資料失敗")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新載入" }));
    expect(refetch).toHaveBeenCalled();
  });

  it("renders KPI values from the dashboard overview", () => {
    mockedUseDashboardOverview.mockReturnValue({
      data: SAMPLE_OVERVIEW,
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useDashboardOverview>);

    render(<KpiSummaryRow />);
    expect(screen.getByText("新北市青年人口 845,938 人")).toBeInTheDocument();
  });
});
