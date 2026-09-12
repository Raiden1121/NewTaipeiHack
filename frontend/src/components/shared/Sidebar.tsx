import { NavLink } from "react-router-dom";
import { AnimatePresence, motion } from "motion/react";
import { cn } from "@/lib/utils";
import { NAV_ITEMS } from "./navItems";

interface SidebarNavProps {
  onNavigate?: () => void;
}

function SidebarNav({ onNavigate }: SidebarNavProps) {
  return (
    <div className="flex h-full flex-col gap-6 bg-primary px-4 pb-20 pt-6 text-white">
      <div className="flex items-center gap-3 px-2 text-left">
        <img src="/favicon.svg" alt="" className="h-9 w-9 shrink-0" aria-hidden="true" />
        <div>
          <p className="text-xl font-extrabold leading-snug">留得青山在</p>
          <p className="mt-1 text-base font-medium leading-snug">
            青年統計儀表板
          </p>
        </div>
      </div>

      <nav className="flex-1">
        <ul className="flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-white/80 transition-colors hover:bg-white/10 hover:text-white",
                      isActive && "bg-white text-primary hover:bg-white hover:text-primary",
                    )
                  }
                >
                  <Icon className="h-5 w-5" aria-hidden="true" />
                  {item.label}
                </NavLink>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

/** 常駐側欄，僅在 lg 以上顯示。 */
export function DesktopSidebar() {
  return (
    <aside className="hidden w-60 shrink-0 lg:block">
      <div className="sticky top-0 h-screen">
        <SidebarNav />
      </div>
    </aside>
  );
}

interface MobileSidebarProps {
  open: boolean;
  onClose: () => void;
}

/** lg 以下的抽屜式側欄。 */
export function MobileSidebar({ open, onClose }: MobileSidebarProps) {
  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <motion.div
            className="absolute inset-0 bg-slate-900/50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />
          <motion.div
            className="absolute left-0 top-0 h-full w-60 shadow-xl"
            initial={{ x: "-100%" }}
            animate={{ x: 0 }}
            exit={{ x: "-100%" }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            role="dialog"
            aria-label="主導覽"
          >
            <SidebarNav onNavigate={onClose} />
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
