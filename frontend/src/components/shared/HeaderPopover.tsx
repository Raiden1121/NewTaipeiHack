import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { X, type LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";

interface HeaderPopoverProps {
  icon: LucideIcon;
  buttonLabel: string;
  title: string;
  message: string;
}

export default function HeaderPopover({
  icon: Icon,
  buttonLabel,
  title,
  message,
}: HeaderPopoverProps) {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    function handlePointerDown(event: MouseEvent) {
      if (!panelRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={panelRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label={buttonLabel}
        aria-expanded={open}
        className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-white transition-colors hover:bg-primary/90"
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -8 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
            className="absolute right-0 top-full z-50 mt-2 w-64 origin-top-right"
          >
            <Card className="dark:bg-surface">
              <div className="flex items-center justify-between border-b border-slate-200 p-4 pb-3 dark:border-slate-700">
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                  {title}
                </h2>
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label={`關閉${title}`}
                  className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
              <div className="p-4 text-sm text-slate-500 dark:text-slate-400">
                {message}
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
