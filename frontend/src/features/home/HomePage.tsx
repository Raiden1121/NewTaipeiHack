import type { ReactNode } from "react";
import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import DistrictChoroplethMap from "./components/DistrictChoroplethMap";
import KpiSummaryRow from "./components/KpiSummaryRow";
import DistrictHighlightsTable from "./components/DistrictHighlightsTable";
import ParticipationOverviewCard from "./components/ParticipationOverviewCard";
import FertilityOverviewCard from "./components/FertilityOverviewCard";
import PolicySupportPanel from "./components/PolicySupportPanel";
import SectionErrorFallback from "@/components/shared/SectionErrorFallback";

interface SectionProps {
  eyebrow: string;
  title: string;
  children: ReactNode;
}

function Section({ eyebrow, title, children }: SectionProps) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          {eyebrow}
        </p>
        <h2 className="text-xl font-bold text-slate-900">{title}</h2>
      </div>
      {children}
    </section>
  );
}

export default function HomePage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 px-4 py-6 md:px-6 md:py-8">
      <Section eyebrow="Employment" title="青年就業與發展機會">
        <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
          <KpiSummaryRow />
        </ErrorBoundary>
      </Section>

      <Section eyebrow="Opportunity Map" title="新北市 29 區青年機會指數">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ErrorBoundary
              onReset={reset}
              FallbackComponent={SectionErrorFallback}
            >
              <DistrictChoroplethMap />
            </ErrorBoundary>
          </div>
          <DistrictHighlightsTable />
        </div>
      </Section>

      <Section eyebrow="Youth Sections" title="青年參政與生育概況">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ParticipationOverviewCard />
          <FertilityOverviewCard />
        </div>
      </Section>

      <Section eyebrow="Governance" title="施政協助與決策支援">
        <PolicySupportPanel />
      </Section>
    </div>
  );
}
