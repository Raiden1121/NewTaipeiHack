import { useQuery } from "@tanstack/react-query";
import { apiFetch, ApiError } from "./client";
import type {
  DashboardOverview,
  DistrictDetail,
  EmploymentScatterAnalysis,
  FamilyFriendlinessAnalysis,
  FertilityOverlayAnalysis,
  PoliticsResourceIoAnalysis,
  PolicyOutcomesAnalysis,
  YouthKeywordFrequencyAnalysis,
} from "./types";

// 404 / 503 是「這個 endpoint 現在就是沒有資料」，重試沒有意義。
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError && (error.status === 404 || error.status === 503)) {
    return false;
  }
  return failureCount < 2;
}

export function useDashboardOverview() {
  return useQuery({
    queryKey: ["dashboard-overview"],
    queryFn: async () => (await apiFetch<DashboardOverview>("/api/v1/dashboard/overview")).data,
    retry: shouldRetry,
  });
}

export function useDistrictDetail(districtId: string | null) {
  return useQuery({
    queryKey: ["district-detail", districtId],
    queryFn: async () =>
      (await apiFetch<DistrictDetail>(`/api/v1/districts/${districtId}`)).data,
    enabled: districtId !== null,
    retry: shouldRetry,
  });
}

export function useEmploymentScatter() {
  return useQuery({
    queryKey: ["analysis", "employment-scatter"],
    queryFn: async () =>
      (await apiFetch<EmploymentScatterAnalysis>("/api/v1/analyses/employment-scatter")).data,
    retry: shouldRetry,
  });
}

export function usePoliticsResourceIo() {
  return useQuery({
    queryKey: ["analysis", "politics-resource-io"],
    queryFn: async () =>
      (await apiFetch<PoliticsResourceIoAnalysis>("/api/v1/analyses/politics-resource-io")).data,
    retry: shouldRetry,
  });
}

// 見 api_contract.md §6.4：canonical 全期間 keywords[]；舊 youth-topic-weight URL 只是相容 alias。
export function useYouthKeywordFrequency() {
  return useQuery({
    queryKey: ["analysis", "youth-keyword-frequency"],
    queryFn: async () =>
      (await apiFetch<YouthKeywordFrequencyAnalysis>("/api/v1/analyses/youth-keyword-frequency")).data,
    retry: shouldRetry,
  });
}

export function useFertilityOverlay() {
  return useQuery({
    queryKey: ["analysis", "fertility-overlay"],
    queryFn: async () =>
      (await apiFetch<FertilityOverlayAnalysis>("/api/v1/analyses/fertility-overlay")).data,
    retry: shouldRetry,
  });
}

export function useFamilyFriendliness() {
  return useQuery({
    queryKey: ["analysis", "fertility-family-friendliness"],
    queryFn: async () =>
      (
        await apiFetch<FamilyFriendlinessAnalysis>(
          "/api/v1/analyses/fertility-family-friendliness",
        )
      ).data,
    retry: shouldRetry,
  });
}

export function usePolicyOutcomes() {
  return useQuery({
    queryKey: ["analysis", "policy-outcomes"],
    queryFn: async () =>
      (await apiFetch<PolicyOutcomesAnalysis>("/api/v1/analyses/policy-outcomes")).data,
    retry: shouldRetry,
  });
}
