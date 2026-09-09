import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./AppLayout";
import HomePage from "@/features/home/HomePage";
import EmploymentPage from "@/features/employment/EmploymentPage";
import PoliticsPage from "@/features/politics/PoliticsPage";
import FertilityPage from "@/features/fertility/FertilityPage";
import PlaceholderPage from "@/components/shared/PlaceholderPage";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/employment", element: <EmploymentPage /> },
      { path: "/politics", element: <PoliticsPage /> },
      { path: "/fertility", element: <FertilityPage /> },
      {
        path: "/policy-support",
        element: <PlaceholderPage title="施政協助" />,
      },
    ],
  },
]);
