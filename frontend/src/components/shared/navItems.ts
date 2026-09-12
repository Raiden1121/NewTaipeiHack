import { LayoutDashboard, Briefcase, Vote, Baby, LifeBuoy } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "主頁", icon: LayoutDashboard },
  { to: "/employment", label: "青年就業", icon: Briefcase },
  { to: "/politics", label: "青年參政", icon: Vote },
  { to: "/fertility", label: "青年生育", icon: Baby },
  { to: "/policy-support", label: "施政協助", icon: LifeBuoy },
];

function findNavItem(pathname: string): NavItem | undefined {
  return NAV_ITEMS.find((item) =>
    item.to === "/" ? pathname === "/" : pathname.startsWith(item.to),
  );
}

export function navTitleForPath(pathname: string): string {
  return findNavItem(pathname)?.label ?? "青年族群公開統計資料整合儀表板";
}

export function navIconForPath(pathname: string): LucideIcon {
  return findNavItem(pathname)?.icon ?? LayoutDashboard;
}
