import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { PropsWithChildren } from "react";
import { useDistrictSummary } from "./useDistrictSummary";
import * as queries from "@/lib/api/queries";

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
  it("selects districts[] out of the dashboard overview query", async () => {
    vi.spyOn(queries, "useDashboardOverview").mockReturnValue({
      data: {
        districts: [
          {
            district_id: "65000010",
            district_name: "板橋區",
            opportunityIndex: 38.16,
            retentionRiskLevel: "medium",
          },
        ],
      },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof queries.useDashboardOverview>);

    const { result } = renderHook(() => useDistrictSummary(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.data?.[0].district_name).toBe("板橋區"));
  });
});
