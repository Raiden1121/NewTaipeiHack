import type { ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import PolicyOutcomeTracker from "./components/PolicyOutcomeTracker";
import PolicyDecisionAssistant from "./components/PolicyDecisionAssistant";
import SectionErrorFallback from "@/components/shared/SectionErrorFallback";

interface SectionProps {
  eyebrow: string;
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
}

function Section({ eyebrow, title, description, action, children }: SectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
            {eyebrow}
          </p>
          <h2 className="text-xl font-bold text-slate-900">{title}</h2>
          {description ? (
            <p className="mt-1 text-sm text-slate-500">{description}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
      {children}
    </section>
  );
}

export default function PolicySupportPage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 px-4 py-6 md:px-6 md:py-8">
      <Section
        eyebrow="Policy Outcomes"
        title="政策成效追蹤"
        description="即時監控核心專案執行指標"
        action={
          <button
            type="button"
            className="flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
          >
            檢視所有專案
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        }
      >
        <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
          <PolicyOutcomeTracker />
        </ErrorBoundary>
      </Section>

      <Section
        eyebrow="Decision Support"
        title="AI 政策決策輔助"
        description="基於即時數據與大語言模型的政策分析助理"
      >
        <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
          <PolicyDecisionAssistant />
        </ErrorBoundary>
      </Section>
    </div>
  );
}
