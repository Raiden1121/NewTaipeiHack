import { useEffect, useMemo, useRef } from "react";
import { useDistrictSummary } from "../hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function DistrictHighlightsTable() {
  const {
    data: districts = [],
    isLoading,
    isError,
    error,
    refetch,
  } = useDistrictSummary();

  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const selectDistrict = useSelectedDistrict((state) => state.selectDistrict);

  const scrollRef = useRef<HTMLOListElement>(null);

  const ranked = useMemo(
    () => [...districts].sort((a, b) => b.opportunityIndex - a.opportunityIndex),
    [districts],
  );

  // 地圖點選 → store 更新 → 對應排名列捲入卡片內的可視範圍（僅捲動清單容器，不動頁面）。
  useEffect(() => {
    if (!selectedDistrictId) return;
    const container = scrollRef.current;
    const row = container?.querySelector<HTMLElement>(
      `[data-district-id="${selectedDistrictId}"]`,
    );
    if (!container || !row) return;
    const containerRect = container.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    if (rowRect.top < containerRect.top) {
      container.scrollBy({
        top: rowRect.top - containerRect.top - 8,
        behavior: "smooth",
      });
    } else if (rowRect.bottom > containerRect.bottom) {
      container.scrollBy({
        top: rowRect.bottom - containerRect.bottom + 8,
        behavior: "smooth",
      });
    }
  }, [selectedDistrictId]);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Highlights
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          重點行政區分析
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col">
        {isLoading ? (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 8 }).map((_, index) => (
              <Skeleton key={index} className="h-9 w-full rounded-lg" />
            ))}
          </div>
        ) : isError ? (
          <section
            role="alert"
            className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-red-200 bg-red-50 p-6 text-center"
          >
            <p className="text-sm text-red-600">
              {error instanceof Error
                ? error.message
                : "行政區資料載入失敗，請稍後再試。"}
            </p>
            <Button variant="destructive" onClick={() => refetch()}>
              重新載入
            </Button>
          </section>
        ) : (
          <ol
            ref={scrollRef}
            className="-mr-2 flex max-h-[460px] flex-col gap-0.5 overflow-y-auto pr-2"
          >
            {ranked.map((district, index) => {
              const isSelected = district.district_id === selectedDistrictId;
              return (
                <li key={district.district_id} data-district-id={district.district_id}>
                  <button
                    type="button"
                    onClick={() => selectDistrict(district.district_id)}
                    className={cn(
                      "flex w-full items-center justify-between gap-3 rounded-lg px-2.5 py-2 text-left transition-colors",
                      isSelected ? "bg-primary/10" : "hover:bg-slate-50",
                    )}
                  >
                    <span className="flex items-center gap-2.5">
                      <span
                        className={cn(
                          "flex h-6 w-6 items-center justify-center rounded-md text-xs font-bold",
                          index < 3
                            ? "bg-primary text-primary-foreground"
                            : "bg-slate-100 text-slate-500",
                        )}
                      >
                        {index + 1}
                      </span>
                      <span
                        className={cn(
                          "text-sm font-semibold",
                          isSelected ? "text-primary" : "text-slate-800",
                        )}
                      >
                        {district.district_name}
                      </span>
                    </span>
                    <span className="text-sm font-bold text-slate-900">
                      {district.opportunityIndex}
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
