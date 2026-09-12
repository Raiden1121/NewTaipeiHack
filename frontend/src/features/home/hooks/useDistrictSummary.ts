import { useDashboardOverview } from "@/lib/api/queries";

/**
 * 取 dashboard/overview 裡的 districts[]。保留這個 hook 名稱與 useQuery 回傳形狀，
 * 讓既有消費它的元件只需改欄位名（district_id 等），不用改資料流結構。
 */
export function useDistrictSummary() {
  const query = useDashboardOverview();
  return { ...query, data: query.data?.districts };
}
