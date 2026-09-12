import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import OpportunityIndexMap from "./OpportunityIndexMap";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";

function renderMap() {
  return render(
    <MemoryRouter>
      <OpportunityIndexMap />
    </MemoryRouter>,
  );
}

vi.mock("@/features/home/hooks/useDistrictSummary");
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
    district_id: "A",
    district_name: "測試甲區",
    opportunityIndex: 80,
    retentionRiskLevel: "low" as const,
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

describe("OpportunityIndexMap", () => {
  it("selects the clicked district in the shared store", async () => {
    renderMap();
    const districtPath = await screen.findByLabelText("測試甲區");

    fireEvent.click(districtPath);

    expect(useSelectedDistrict.getState().selectedDistrictId).toBe("A");
  });

  it("does not select a district after a drag gesture", async () => {
    renderMap();
    const districtPath = await screen.findByLabelText("測試甲區");
    const svg = districtPath.closest("svg") as SVGSVGElement;

    fireEvent.pointerDown(svg, { pointerId: 1, button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(svg, { pointerId: 1, clientX: 40, clientY: 40 });
    fireEvent.pointerUp(svg, { pointerId: 1 });
    fireEvent.click(districtPath);

    expect(useSelectedDistrict.getState().selectedDistrictId).toBeNull();
  });
});
