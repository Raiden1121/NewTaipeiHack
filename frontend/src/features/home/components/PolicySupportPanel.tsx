import { Bot, SendHorizontal } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface PolicyProgress {
  label: string;
  value: number;
}

// 佔位資料，待施政協助板塊與 Backend API 提供。
const PROGRESS: PolicyProgress[] = [
  { label: "租金補貼核發率", value: 89 },
  { label: "青創貸款成效達成率", value: 92 },
  { label: "培力計畫結訓率", value: 76 },
  { label: "育兒津貼申請覆蓋率", value: 84 },
];

const PROMPT_EXAMPLES = [
  "板橋區青年租金補貼成效如何？",
  "哪些行政區的青創資源投入與產出落差最大？",
];

export default function PolicySupportPanel() {
  return (
    <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Policy Outcomes
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            政策成效追蹤
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {PROGRESS.map((item) => (
            <div key={item.label}>
              <div className="mb-1 flex items-center justify-between text-sm">
                <span className="font-semibold text-slate-700">
                  {item.label}
                </span>
                <span className="font-bold text-primary">{item.value}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${item.value}%` }}
                />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Decision Support
          </p>
          <CardTitle className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <Bot className="h-5 w-5 text-primary" aria-hidden="true" />
            AI 政策輔助
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <p className="text-sm text-slate-600">
            輸入特定領域議題，AI 將基於新北市公開統計資料生成洞察與政策處方建議。
          </p>
          <div className="flex flex-wrap gap-2">
            {PROMPT_EXAMPLES.map((example) => (
              <span
                key={example}
                className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-500"
              >
                {example}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 p-2">
            <input
              type="text"
              placeholder="請輸入問題（展示佔位，尚未串接）"
              className="min-w-0 flex-1 bg-transparent px-2 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none"
            />
            <Button size="sm" type="button" aria-label="送出">
              <SendHorizontal className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
