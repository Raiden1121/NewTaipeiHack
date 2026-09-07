import { ErrorBoundary } from "react-error-boundary";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import DistrictChoroplethMap from "./components/DistrictChoroplethMap";
import KpiSummaryRow from "./components/KpiSummaryRow";
import SectionEntryCards from "./components/SectionEntryCards";
import SectionErrorFallback from "@/components/shared/SectionErrorFallback";

export default function HomePage() {
  const { reset } = useQueryErrorResetBoundary();

  return (
    <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-8 px-6 py-10">
      <header>
        <p className="mb-1 text-xs font-bold uppercase tracking-[0.16em] text-accent-slate">
          NEW TAIPEI · YOUTH OPPORTUNITY MAP
        </p>
        <h1 className="text-3xl font-bold text-slate-900 md:text-4xl">
          新北青年機會地圖
        </h1>
      </header>

      <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
        <KpiSummaryRow />
      </ErrorBoundary>

      <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
        <DistrictChoroplethMap />
      </ErrorBoundary>

      <ErrorBoundary onReset={reset} FallbackComponent={SectionErrorFallback}>
        <SectionEntryCards />
      </ErrorBoundary>
    </main>
  );
}
