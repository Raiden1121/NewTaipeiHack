import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { useDistrictSummary } from "./useDistrictSummary";
import * as districtsData from "@/data/districts";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

describe("useDistrictSummary", () => {
  it("exposes the data returned by fetchDistrictSummaries", async () => {
    vi.spyOn(districtsData, "fetchDistrictSummaries").mockResolvedValue([
      {
        id: "65000010",
        name: "板橋區",
        youthPopulation: 148000,
        opportunityIndex: 86,
        retentionRiskLevel: "low",
        youthParticipationIndex: 72,
        fertilityRate: 42.1,
        policySupportScore: 81,
      },
    ]);

    const { result } = renderHook(() => useDistrictSummary(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0].name).toBe("板橋區");
  });
});
