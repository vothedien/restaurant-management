import { Route, Routes } from "react-router-dom";

import { MainLayout } from "../layouts/MainLayout";
import { HomePage } from "../pages/HomePage";
import { InventoryDashboard } from "../pages/InventoryDashboard";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { SalesDashboard } from "../pages/SalesDashboard";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route index element={<HomePage />} />
        <Route path="sales" element={<SalesDashboard />} />
        <Route path="inventory" element={<InventoryDashboard />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
