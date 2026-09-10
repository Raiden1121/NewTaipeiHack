import { TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// 佔位資料，待施政協助板塊與 Backend API 提供。
const TOTAL_BUDGET = "NT$ 3.24 億";
const BUDGET_YOY = "+8.5%";
const BUDGET_EXECUTION_RATE = 72;
const ACHIEVEMENT_RATE = 85;

export default function PolicySupportPanel() {
  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Annual Budget
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            青年總預算
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex items-end gap-2">
            <span className="text-3xl font-bold text-slate-900">
              {TOTAL_BUDGET}
            </span>
            <span className="mb-1 inline-flex items-center gap-1 text-xs font-semibold text-accent-teal">
              <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
              較前年 {BUDGET_YOY}
            </span>
          </div>
          <p className="text-sm text-slate-500">2026 年度青年政策總預算</p>
          <div>
            <div className="mb-1 flex items-center justify-between text-xs font-semibold">
              <span className="text-slate-600">預算執行率</span>
              <span className="text-primary">{BUDGET_EXECUTION_RATE}%</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${BUDGET_EXECUTION_RATE}%` }}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Achievement Rate
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            達成率
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <span className="text-3xl font-bold text-primary">
            {ACHIEVEMENT_RATE}%
          </span>
          <p className="text-sm text-slate-500">年度政策目標平均達成率</p>
          <div className="h-3 w-full overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${ACHIEVEMENT_RATE}%` }}
            />
          </div>
          <p className="text-xs text-slate-400">涵蓋 4 項青年政策</p>
        </CardContent>
      </Card>
    </section>
  );
}
