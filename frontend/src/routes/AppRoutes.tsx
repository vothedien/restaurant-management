import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";

import { MainLayout } from "../layouts/MainLayout";
import { HomePage } from "../pages/HomePage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { SalesDashboard } from "../pages/SalesDashboard";

const InventoryApplication = lazy(() => import("../features/inventory/routes/InventoryApplication"));

export function AppRoutes() {
  return (
    <Routes>
      <Route path="inventory/*" element={<Suspense fallback={<p role="status">Đang tải kho hàng…</p>}><InventoryApplication /></Suspense>} />
      <Route element={<MainLayout />}>
        <Route index element={<HomePage />} />
        <Route path="sales" element={<SalesDashboard />} />
        <Route path="login" element={<LoginPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
