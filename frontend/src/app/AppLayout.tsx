import { Outlet } from "react-router-dom";
import NavBar from "@/components/shared/NavBar";

export default function AppLayout() {
  return (
    <div className="min-h-screen bg-background">
      <NavBar />
      <Outlet />
    </div>
  );
}
