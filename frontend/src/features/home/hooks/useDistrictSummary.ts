import { useQuery } from "@tanstack/react-query";
import { fetchDistrictSummaries } from "@/data/districts";

export function useDistrictSummary() {
  return useQuery({
    queryKey: ["district-summaries"],
    queryFn: fetchDistrictSummaries,
  });
}
