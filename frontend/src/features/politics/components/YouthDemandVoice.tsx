import { motion } from "motion/react";
import { Quote } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface DemandTopic {
  label: string;
  share: number;
}

// 佔位資料，待 Backend API 提供整理後結果。
const TOPICS: DemandTopic[] = [
  { label: "住宅與居住正義", share: 35 },
  { label: "就業與創業支持", share: 28 },
  { label: "交通與通勤改善", share: 14 },
  { label: "教育與技能培力", share: 13 },
  { label: "社會參與管道", share: 10 },
];

export default function YouthDemandVoice() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            Proposal Topics
          </p>
          <CardTitle className="text-lg font-bold text-slate-900">
            提案議題分布
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {TOPICS.map((topic, index) => (
            <div key={topic.label} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-slate-700">
                  {topic.label}
                </span>
                <span className="font-bold text-slate-900">{topic.share}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <motion.div
                  className="h-full rounded-full bg-primary"
                  initial={{ width: 0 }}
                  animate={{ width: `${topic.share}%` }}
                  transition={{ delay: index * 0.06, duration: 0.5 }}
                />
              </div>
            </div>
          ))}
          <p className="text-[11px] text-slate-400">
            議題比例為佔位資料，待 Backend API 提供整理後結果。
          </p>
        </CardContent>
      </Card>

      <Card className="flex flex-col bg-slate-50">
        <CardHeader>
          <p className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            <Quote className="h-3.5 w-3.5" aria-hidden="true" />
            外部研究引用
          </p>
        </CardHeader>
        <CardContent className="flex flex-1 flex-col justify-between gap-4">
          <blockquote className="text-sm leading-relaxed text-slate-700">
            「根據 2023 青年世代政策關注度調查，超過六成的新北青年將『居住負擔』
            列為首要政治訴求，直接影響其地區參與意願。」
          </blockquote>
          <p className="text-xs text-slate-400">
            資料來源：天下智庫青年趨勢報告（2023）· 佔位引用
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
