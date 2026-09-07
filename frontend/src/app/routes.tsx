import { createBrowserRouter } from "react-router-dom";
import AppLayout from "./AppLayout";
import HomePage from "@/features/home/HomePage";
import PlaceholderPage from "@/components/shared/PlaceholderPage";

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: "/", element: <HomePage /> },
      { path: "/employment", element: <PlaceholderPage title="青年就業" /> },
      { path: "/politics", element: <PlaceholderPage title="青年參政" /> },
      { path: "/fertility", element: <PlaceholderPage title="青年生育" /> },
      {
        path: "/policy-support",
        element: <PlaceholderPage title="施政協助" />,
      },
    ],
  },
]);
