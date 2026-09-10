import { TrendingUp, TrendingDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface HighlightRow {
  district: string;
  index: number;
  delta: string;
  trend: "up" | "down";
}

// 佔位資料，待 Backend API 提供整理後結果。
const ROWS: HighlightRow[] = [
  { district: "板橋區", index: 86, delta: "+2.1%", trend: "up" },
  { district: "新莊區", index: 81, delta: "+1.4%", trend: "up" },
  { district: "三重區", index: 78, delta: "-0.6%", trend: "down" },
  { district: "中和區", index: 74, delta: "+0.8%", trend: "up" },
  { district: "土城區", index: 69, delta: "-1.3%", trend: "down" },
];

export default function DistrictHighlightsTable() {
  return (
    <Card className="h-full">
      <CardHeader>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          Highlights
        </p>
        <CardTitle className="text-lg font-bold text-slate-900">
          重點行政區分析
        </CardTitle>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs font-semibold uppercase tracking-wide text-accent-slate">
              <th className="pb-2">行政區</th>
              <th className="pb-2 text-right">機會指數</th>
              <th className="pb-2 text-right">增減</th>
              <th className="pb-2 text-right">趨勢</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {ROWS.map((row) => {
              const Icon = row.trend === "up" ? TrendingUp : TrendingDown;
              return (
                <tr key={row.district}>
                  <td className="py-2.5 font-semibold text-slate-800">
                    {row.district}
                  </td>
                  <td className="py-2.5 text-right font-bold text-slate-900">
                    {row.index}
                  </td>
                  <td
                    className={cn(
                      "py-2.5 text-right font-semibold",
                      row.trend === "up" ? "text-accent-teal" : "text-risk-high",
                    )}
                  >
                    {row.delta}
                  </td>
                  <td className="py-2.5">
                    <Icon
                      className={cn(
                        "ml-auto h-4 w-4",
                        row.trend === "up"
                          ? "text-accent-teal"
                          : "text-risk-high",
                      )}
                      aria-hidden="true"
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}
