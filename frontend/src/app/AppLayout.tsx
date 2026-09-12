import { useState } from "react";
import { Outlet, ScrollRestoration } from "react-router-dom";
import { MotionConfig } from "motion/react";
import { DesktopSidebar, MobileSidebar } from "@/components/shared/Sidebar";
import Topbar from "@/components/shared/Topbar";
import SettingsEffects from "@/components/shared/SettingsEffects";
import SettingsPanel from "@/components/shared/SettingsPanel";
import { useSettingsStore } from "@/stores/useSettingsStore";

export default function AppLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const reduceMotion = useSettingsStore((state) => state.reduceMotion);

  return (
    <MotionConfig reducedMotion={reduceMotion ? "always" : "user"}>
      <SettingsEffects />
      <div className="flex min-h-screen bg-background">
        <DesktopSidebar />
        <MobileSidebar open={drawerOpen} onClose={() => setDrawerOpen(false)} />

        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar onOpenMenu={() => setDrawerOpen(true)} />
          {/* 深色模式本階段僅套用外框，主內容區維持淺色以確保可讀性 */}
          <main className="flex-1 dark:bg-white">
            <Outlet />
          </main>
        </div>
      </div>
      <SettingsPanel />
      <ScrollRestoration />
    </MotionConfig>
  );
}
