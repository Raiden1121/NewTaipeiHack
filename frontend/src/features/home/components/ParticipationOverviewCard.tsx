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
      <CardContent>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-semibold text-accent-slate">
              青年參選熱度
            </p>
            <div className="mt-1 flex items-end gap-1.5">
              <span className="text-2xl font-bold text-primary">12.8%</span>
              <span className="mb-1 inline-flex items-center gap-0.5 text-xs font-semibold text-accent-teal">
                <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
                1.5%
              </span>
            </div>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-semibold text-accent-slate">
              整體服務涵蓋率
            </p>
            <p className="mt-1 text-2xl font-bold text-slate-900">68%</p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
