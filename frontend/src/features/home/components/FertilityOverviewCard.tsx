import { Bot } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function FertilityOverviewCard() {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Fertility & Family
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          青年生育與成家
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-semibold text-accent-slate">平均生育率</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">
              78.5<span className="text-sm font-semibold">‰</span>
            </p>
          </div>
          <div className="rounded-xl bg-slate-50 p-3">
            <p className="text-xs font-semibold text-accent-slate">
              對全市平均比
            </p>
            <p className="mt-1 text-2xl font-bold text-primary">92%</p>
          </div>
        </div>

        <div className="flex items-start gap-2 rounded-xl border border-slate-200 bg-primary/5 p-3">
          <Bot className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
          <p className="text-xs leading-relaxed text-slate-600">
            AI 數據洞察佔位：歸納資源投入與生育回升之因果特徵，待 AI Service API
            提供結構化分析文本。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
