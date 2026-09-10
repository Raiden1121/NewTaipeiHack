import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import DistrictChoroplethMap from "./DistrictChoroplethMap";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";

vi.mock("../hooks/useDistrictSummary");
vi.mock("topojson-client", () => ({
  feature: () => ({
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { id: "A", name: "測試甲區" },
        geometry: {
          type: "Polygon",
          coordinates: [[[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]],
        },
      },
      {
        type: "Feature",
        properties: { id: "B", name: "測試乙區" },
        geometry: {
          type: "Polygon",
          coordinates: [[[20, 0], [20, 10], [30, 10], [30, 0], [20, 0]]],
        },
      },
    ],
  }),
}));

const mockedUseDistrictSummary = vi.mocked(useDistrictSummary);

const SAMPLE_DISTRICTS = [
  {
    id: "A",
    name: "測試甲區",
    youthPopulation: 1000,
    opportunityIndex: 80,
    retentionRiskLevel: "low" as const,
    youthParticipationIndex: 60,
    fertilityRate: 40,
    policySupportScore: 70,
  },
  {
    id: "B",
    name: "測試乙區",
    youthPopulation: 500,
    opportunityIndex: 50,
    retentionRiskLevel: "high" as const,
    youthParticipationIndex: 40,
    fertilityRate: 45,
    policySupportScore: 50,
  },
];

beforeEach(() => {
  useSelectedDistrict.setState({ selectedDistrictId: null });
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ objects: { map: {} } }),
    }),
  );
  mockedUseDistrictSummary.mockReturnValue({
    data: SAMPLE_DISTRICTS,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useDistrictSummary>);
});

describe("DistrictChoroplethMap", () => {
  it("selects a district in the store when its path is clicked", async () => {
    render(<DistrictChoroplethMap />);
    const pathA = await screen.findByLabelText("測試甲區");

    fireEvent.click(pathA);

    expect(useSelectedDistrict.getState().selectedDistrictId).toBe("A");
  });

  it("shows a tooltip with the district name on hover", async () => {
    render(<DistrictChoroplethMap />);
    const pathB = await screen.findByLabelText("測試乙區");

    fireEvent.mouseEnter(pathB);
    expect(screen.getAllByText("測試乙區").length).toBeGreaterThan(0);

    fireEvent.mouseLeave(pathB);
  });

  it("renders an inline error state and retries via the reload button", async () => {
    const refetch = vi.fn();
    mockedUseDistrictSummary.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("模擬行政區資料失敗"),
      refetch,
    } as unknown as ReturnType<typeof useDistrictSummary>);

    render(<DistrictChoroplethMap />);

    expect(await screen.findByText("模擬行政區資料失敗")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新載入" }));
    expect(refetch).toHaveBeenCalled();
  });
});
