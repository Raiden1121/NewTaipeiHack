import { Check } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface Stage {
  label: string;
  status: "done" | "current" | "upcoming";
}

// 佔位資料，待 Backend API 提供整理後結果。
const STAGES: Stage[] = [
  { label: "立法三讀", status: "done" },
  { label: "頒行公告", status: "current" },
  { label: "青年參政會報", status: "upcoming" },
  { label: "青年政策白皮書", status: "upcoming" },
];

export default function YouthActProgress() {
  const currentIndex = STAGES.findIndex((stage) => stage.status === "current");
  const progressRatio =
    currentIndex <= 0 ? 0 : currentIndex / (STAGES.length - 1);

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
              Legislation Progress
            </p>
            <CardTitle className="text-lg font-bold text-slate-900">
              青年基本法進度
            </CardTitle>
          </div>
          <Badge variant="secondary">資料待補</Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-4">
        <div className="relative px-1">
          <div className="absolute left-0 right-0 top-3 h-1 rounded-full bg-slate-100" />
          <div
            className="absolute left-0 top-3 h-1 rounded-full bg-primary transition-all"
            style={{ width: `${progressRatio * 100}%` }}
          />
          <ol className="relative flex justify-between">
            {STAGES.map((stage) => (
              <li
                key={stage.label}
                className="flex flex-1 flex-col items-center gap-2 text-center first:items-start last:items-end"
              >
                <span
                  className={cn(
                    "flex h-7 w-7 items-center justify-center rounded-full border-2 bg-surface text-xs font-bold",
                    stage.status === "done" &&
                      "border-primary bg-primary text-primary-foreground",
                    stage.status === "current" &&
                      "border-primary text-primary",
                    stage.status === "upcoming" &&
                      "border-slate-200 text-slate-400",
                  )}
                >
                  {stage.status === "done" ? (
                    <Check className="h-3.5 w-3.5" aria-hidden="true" />
                  ) : (
                    <span
                      className={cn(
                        "h-2 w-2 rounded-full",
                        stage.status === "current"
                          ? "bg-primary"
                          : "bg-slate-300",
                      )}
                    />
                  )}
                </span>
                <span
                  className={cn(
                    "text-xs font-semibold",
                    stage.status === "upcoming"
                      ? "text-slate-400"
                      : "text-slate-700",
                  )}
                >
                  {stage.label}
                </span>
              </li>
            ))}
          </ol>
        </div>
      </CardContent>
    </Card>
  );
}
