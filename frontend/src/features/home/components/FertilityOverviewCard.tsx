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
      <CardContent>
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
      </CardContent>
    </Card>
  );
}
