import { useMemo } from "react";
import { Info } from "lucide-react";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useFamilyFriendliness } from "@/lib/api/queries";
import type { FamilyFriendlinessDistrict } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import MetricInfoTooltip from "@/components/shared/MetricInfoTooltip";
import { FAMILY_FRIENDLINESS_INDEX_FORMULA } from "@/lib/metricFormulas";

const BAR_CLASS: Record<FamilyFriendlinessDistrict["fafi_level"], string> = {
  high: "bg-risk-low",
  medium: "bg-risk-medium",
  low: "bg-risk-high",
};

const TEXT_CLASS: Record<FamilyFriendlinessDistrict["fafi_level"], string> = {
  high: "text-risk-low",
  medium: "text-risk-medium",
  low: "text-risk-high",
};

export default function FamilyFriendlinessPanel() {
  const { data: analysis, isLoading, isError, error, refetch } = useFamilyFriendliness();
  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const selectDistrict = useSelectedDistrict((state) => state.selectDistrict);

  const ranked = useMemo(
    () => (analysis ? [...analysis.districts].sort((a, b) => b.fafi_score - a.fafi_score) : []),
    [analysis],
  );

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Family-Friendly Index
        </p>
        <CardTitle className="flex items-center gap-1.5 text-base font-bold text-slate-900">
          青年成家環境友善度
          <MetricInfoTooltip formula={FAMILY_FRIENDLINESS_INDEX_FORMULA} />
        </CardTitle>
        <p className="mt-1 text-xs text-slate-500">
          公共托育、居住可負擔與薪資水準之綜合評分（FaFI）
        </p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        {isLoading ? (
          <ul className="flex flex-col gap-2.5">
            {Array.from({ length: 10 }).map((_, index) => (
              <li key={index}>
                <Skeleton className="h-6 w-full rounded-md" />
              </li>
            ))}
          </ul>
        ) : isError || !analysis ? (
          <section
            role="alert"
            className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 p-6 text-center"
          >
            <p className="text-sm text-red-600">
              {error instanceof Error ? error.message : "友善度資料載入失敗，請稍後再試。"}
            </p>
            <Button variant="destructive" onClick={() => refetch()}>
              重新載入
            </Button>
          </section>
        ) : (
          <ul className="flex max-h-[380px] flex-col gap-2.5 overflow-y-auto pr-1">
            {ranked.map((district) => {
              const isSelected = district.district_id === selectedDistrictId;
              return (
                <li key={district.district_id}>
                  <button
                    type="button"
                    onClick={() => selectDistrict(district.district_id)}
                    className={cn(
                      "flex w-full items-center gap-3 rounded-md px-1.5 py-1 text-left transition-colors",
                      isSelected ? "bg-primary/10" : "hover:bg-slate-50",
                    )}
                  >
                    <span className="w-14 shrink-0 text-sm font-semibold text-slate-700">
                      {district.district_name}
                    </span>
                    <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                      <span
                        className={cn("block h-full rounded-full", BAR_CLASS[district.fafi_level])}
                        style={{ width: `${district.fafi_score}%` }}
                      />
                    </span>
                    <span
                      className={cn(
                        "w-10 shrink-0 text-right text-sm font-bold",
                        TEXT_CLASS[district.fafi_level],
                      )}
                    >
                      {district.fafi_score.toFixed(0)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        <div className="flex gap-2 rounded-xl bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
          <Info
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-slate"
            aria-hidden="true"
          />
          <p>
            綠色代表環境友善，黃色代表尚可，紅色代表待改善（依全市分位數分級）。托育資源覆蓋率待
            geocoding 完成後納入計算，目前分數由居住友善度與薪資推估，見
            api_contract.md §7.4。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
