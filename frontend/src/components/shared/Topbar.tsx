import { useLocation } from "react-router-dom";
import { Menu, Bell, ShieldCheck } from "lucide-react";
import { navTitleForPath, navIconForPath } from "./navItems";
import HeaderPopover from "./HeaderPopover";

interface TopbarProps {
  onOpenMenu: () => void;
}

export default function Topbar({ onOpenMenu }: TopbarProps) {
  const { pathname } = useLocation();
  const title = navTitleForPath(pathname);
  const TitleIcon = navIconForPath(pathname);

  return (
    <header className="sticky top-0 z-30 flex items-center gap-4 border-b border-slate-200 bg-white/90 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90 md:px-6">
      <button
        type="button"
        onClick={onOpenMenu}
        className="rounded-lg p-2 text-slate-600 transition-colors hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 lg:hidden"
        aria-label="開啟主導覽"
      >
        <Menu className="h-5 w-5" aria-hidden="true" />
      </button>

      <div className="flex flex-1 items-center gap-2 truncate">
        {/* navIconForPath 只是依路徑挑選既有的圖示元件，非動態產生新元件；
            react-hooks/static-components 對此樣式屬已知誤報。 */}
        {/* eslint-disable-next-line react-hooks/static-components */}
        <TitleIcon className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
        <h1 className="truncate text-base font-bold text-slate-900 dark:text-white md:text-lg">
          {title}
        </h1>
      </div>

      <HeaderPopover
        icon={Bell}
        buttonLabel="通知"
        title="通知"
        message="通知頁面待開發"
      />

      <HeaderPopover
        icon={ShieldCheck}
        buttonLabel="權限管理"
        title="權限管理"
        message="權限管理頁面待開發"
      />
    </header>
  );
}
