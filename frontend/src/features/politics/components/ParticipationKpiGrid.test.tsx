import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import ParticipationKpiGrid from "./ParticipationKpiGrid";
import { useDashboardOverview } from "@/lib/api/queries";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";

vi.mock("@/lib/api/queries");
const mockedUseDashboardOverview = vi.mocked(useDashboardOverview);

function mockOverview(data: unknown) {
  mockedUseDashboardOverview.mockReturnValue({
    data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useDashboardOverview>);
}

const SAMPLE_OVERVIEW = {
  districts: [
    {
      district_id: "65000010",
      district_name: "板橋區",
      serviceCoverageRate: 50,
      youthBoroughChiefRatioPercent: 2.380952,
      yrr: 0.112823,
    },
  ],
  service_coverage: { value: 49.2 },
  elections: {
    borough_chief_v1_citywide: {
      year_roc: 111,
      elected_count: 1032,
      youth_elected_count: 31,
      ratio_percent: 3.003876,
      yrr: 0.133961,
      denominator_type: "population_proxy",
      proxy: true,
    },
  },
};

describe("ParticipationKpiGrid", () => {
  afterEach(() => {
    // Unmount first so resetting the store does not re-render outside act().
    cleanup();
    useSelectedDistrict.setState({ selectedDistrictId: null });
  });

  it("shows the citywide YRR scalar when no district is selected", () => {
    mockOverview(SAMPLE_OVERVIEW);

    render(<ParticipationKpiGrid />);

    expect(screen.getByText("0.13")).toBeInTheDocument();
    expect(screen.getByText("3.0%")).toBeInTheDocument();
  });

  it("shows the selected district's YRR scalar", () => {
    mockOverview(SAMPLE_OVERVIEW);
    useSelectedDistrict.setState({ selectedDistrictId: "65000010" });

    render(<ParticipationKpiGrid />);

    expect(screen.getByText("0.11")).toBeInTheDocument();
    expect(screen.getByText("2.4%")).toBeInTheDocument();
  });

  it("falls back to 資料待補 when YRR is missing", () => {
    mockOverview({ districts: [], service_coverage: { value: 49.2 }, elections: {} });

    render(<ParticipationKpiGrid />);

    expect(screen.getAllByText("資料待補").length).toBeGreaterThanOrEqual(2);
  });
});
