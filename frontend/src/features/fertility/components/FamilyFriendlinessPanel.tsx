import { useMemo } from "react";
import { Info } from "lucide-react";
import { useDistrictSummary } from "@/features/home/hooks/useDistrictSummary";
import { useSelectedDistrict } from "@/stores/useSelectedDistrict";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// 以 policySupportScore 作為青年成家環境友善度佔位分數，待 Backend API 提供整理後結果。
function barColor(score: number): string {
  if (score > 70) return "bg-risk-low";
  if (score >= 50) return "bg-risk-medium";
  return "bg-risk-high";
}

function scoreColor(score: number): string {
  if (score > 70) return "text-risk-low";
  if (score >= 50) return "text-risk-medium";
  return "text-risk-high";
}

export default function FamilyFriendlinessPanel() {
  const { data: districts = [], isLoading } = useDistrictSummary();
  const selectedDistrictId = useSelectedDistrict(
    (state) => state.selectedDistrictId,
  );
  const selectDistrict = useSelectedDistrict((state) => state.selectDistrict);

  const ranked = useMemo(
    () =>
      [...districts].sort(
        (a, b) => b.policySupportScore - a.policySupportScore,
      ),
    [districts],
  );

  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Family-Friendly Index
        </p>
        <CardTitle className="text-base font-bold text-slate-900">
          青年成家環境友善度
        </CardTitle>
        <p className="mt-1 text-xs text-slate-500">
          公共托育、居住可負擔與職場友善之綜合評分
        </p>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <ul className="flex max-h-[380px] flex-col gap-2.5 overflow-y-auto pr-1">
          {isLoading
            ? Array.from({ length: 10 }).map((_, index) => (
                <li key={index}>
                  <Skeleton className="h-6 w-full rounded-md" />
                </li>
              ))
            : ranked.map((district) => {
                const score = district.policySupportScore;
                const isSelected = district.id === selectedDistrictId;
                return (
                  <li key={district.id}>
                    <button
                      type="button"
                      onClick={() => selectDistrict(district.id)}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-md px-1.5 py-1 text-left transition-colors",
                        isSelected ? "bg-primary/10" : "hover:bg-slate-50",
                      )}
                    >
                      <span className="w-14 shrink-0 text-sm font-semibold text-slate-700">
                        {district.name}
                      </span>
                      <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                        <span
                          className={cn(
                            "block h-full rounded-full",
                            barColor(score),
                          )}
                          style={{ width: `${score}%` }}
                        />
                      </span>
                      <span
                        className={cn(
                          "w-8 shrink-0 text-right text-sm font-bold",
                          scoreColor(score),
                        )}
                      >
                        {score}
                      </span>
                    </button>
                  </li>
                );
              })}
        </ul>
        <div className="flex gap-2 rounded-xl bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
          <Info
            className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-slate"
            aria-hidden="true"
          />
          <p>
            友善度綜合：公共托育量能、租金與房價可負擔性、育嬰職場友善企業比例、社區親子空間密度。
            綠色（&gt;70）代表環境友善，黃色（50–70）代表尚可，紅色（&lt;50）代表待改善。
            數值為佔位資料，待 Backend API 提供。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
