import { TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ParticipationOverviewCard() {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Civic Participation
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          青年參政概況
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent-slate">
            青年參選密度
          </p>
          <div className="mt-1 flex items-end gap-2">
            <span className="text-3xl font-bold text-primary">12.8%</span>
            <span className="mb-1 inline-flex items-center gap-1 text-xs font-semibold text-accent-teal">
              <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
              1.5%
            </span>
          </div>
        </div>

        <div
          className="flex h-32 items-center justify-center rounded-xl border border-dashed border-slate-200 bg-slate-50 text-xs font-semibold text-slate-400"
          aria-hidden="true"
        >
          參政熱點圖佔位
        </div>
      </CardContent>
    </Card>
  );
}
