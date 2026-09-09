import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./AppLayout";
import HomePage from "@/features/home/HomePage";
import EmploymentPage from "@/features/employment/EmploymentPage";
import PoliticsPage from "@/features/politics/PoliticsPage";
import PlaceholderPage from "@/components/shared/PlaceholderPage";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/employment", element: <EmploymentPage /> },
      { path: "/politics", element: <PoliticsPage /> },
      { path: "/fertility", element: <PlaceholderPage title="青年生育" /> },
      {
        path: "/policy-support",
        element: <PlaceholderPage title="施政協助" />,
      },
    ],
  },
]);
