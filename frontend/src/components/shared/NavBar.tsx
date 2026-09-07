import { NavLink } from "react-router-dom";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "主頁戰情室" },
  { to: "/employment", label: "青年就業" },
  { to: "/politics", label: "青年參政" },
  { to: "/fertility", label: "青年生育" },
  { to: "/policy-support", label: "施政協助" },
];

export default function NavBar() {
  return (
    <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
      <nav className="mx-auto flex w-full max-w-[1440px] items-center gap-6 px-6 py-4">
        <span className="text-lg font-extrabold text-primary">
          新北青年機會地圖
        </span>
        <ul className="flex flex-1 items-center gap-1">
          {NAV_ITEMS.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  cn(
                    "rounded-full px-4 py-2 text-sm font-semibold text-slate-600 transition-colors hover:bg-primary/10 hover:text-primary",
                    isActive && "bg-primary text-white hover:bg-primary hover:text-white",
                  )
                }
              >
                {item.label}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
