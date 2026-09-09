import { Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

// 佔位資料，待 Backend API 提供整理後結果。
const SCORES = [
  { name: "板橋區", score: 85 },
  { name: "新莊區", score: 78 },
  { name: "林口區", score: 65 },
  { name: "淡水區", score: 58 },
  { name: "三芝區", score: 32 },
];

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

export default function ResourceInvestmentScore() {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Investment Score
        </p>
        <CardTitle className="text-base font-bold text-slate-900">
          政府資源投入評分
        </CardTitle>
        <p className="mt-1 text-xs text-slate-500">
          青年生育補助與托育資源綜合指標
        </p>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <ul className="flex flex-col gap-3">
          {SCORES.map((item) => (
            <li key={item.name} className="flex items-center gap-3">
              <span className="w-14 shrink-0 text-sm font-semibold text-slate-700">
                {item.name}
              </span>
              <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                <span
                  className={cn("block h-full rounded-full", barColor(item.score))}
                  style={{ width: `${item.score}%` }}
                />
              </span>
              <span
                className={cn(
                  "w-8 shrink-0 text-right text-sm font-bold",
                  scoreColor(item.score),
                )}
              >
                {item.score}
              </span>
            </li>
          ))}
        </ul>
        <div className="flex gap-2 rounded-xl bg-slate-50 p-3 text-[11px] leading-relaxed text-slate-500">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent-slate" aria-hidden="true" />
          <p>
            評分基準包含：公托中心數量、整合生育津貼線、友善職場環境企業比例。
            綠色（&gt;70）代表資源充足，黃色（50–70）代表資源達標，紅色（&lt;50）代表需加強投入。
            數值為佔位資料，待 Backend API 提供。
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
