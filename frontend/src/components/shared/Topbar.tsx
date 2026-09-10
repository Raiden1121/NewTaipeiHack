import { useLocation } from "react-router-dom";
import { Menu, Search, Bell } from "lucide-react";
import { navTitleForPath } from "./navItems";

interface TopbarProps {
  onOpenMenu: () => void;
}

export default function Topbar({ onOpenMenu }: TopbarProps) {
  const { pathname } = useLocation();
  const title = navTitleForPath(pathname);

  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur md:px-6">
      <button
        type="button"
        onClick={onOpenMenu}
        className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 lg:hidden"
        aria-label="開啟主導覽"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      <h1 className="flex-1 truncate text-base font-bold text-slate-900 md:text-lg">
        {title}
      </h1>

      <div className="relative hidden md:block">
        <Search
          className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400"
          aria-hidden="true"
        />
        <input
          type="search"
          placeholder="搜尋指標／行政區"
          className="h-9 w-56 rounded-full border border-slate-200 bg-slate-50 pl-9 pr-4 text-sm text-slate-700 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      <button
        type="button"
        className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100"
        aria-label="通知"
      >
        <Bell className="h-5 w-5" aria-hidden="true" />
      </button>

      <div
        className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-sm font-bold text-white"
        aria-hidden="true"
      >
        青
      </div>
    </header>
  );
}
