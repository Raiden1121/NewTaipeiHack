import type { FallbackProps } from "react-error-boundary";
import { Button } from "@/components/ui/button";

export default function SectionErrorFallback({
  error,
  resetErrorBoundary,
}: FallbackProps) {
  const message =
    error instanceof Error ? error.message : "區塊發生未預期的錯誤。";

  return (
    <section
      role="alert"
      className="flex min-h-[220px] flex-col items-center justify-center gap-3 rounded-2xl border border-red-200 bg-red-50 p-8 text-center"
    >
      <h2 className="text-lg font-bold text-red-700">區塊發生未預期的錯誤</h2>
      <p className="text-sm text-red-600">{message}</p>
      <Button variant="destructive" onClick={resetErrorBoundary}>
        重新載入
      </Button>
    </section>
  );
}
