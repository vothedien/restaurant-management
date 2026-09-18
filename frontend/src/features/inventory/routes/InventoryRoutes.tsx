import { lazy, Suspense } from 'react';
import { Link, Route, Routes } from 'react-router-dom';
import { LoadingState, EmptyState } from '../components/ui';
import '../inventory.css';

const Overview = lazy(() => import('../pages/InsightPages').then(m => ({default:m.InventoryOverviewPage})));
const Alerts = lazy(() => import('../pages/InsightPages').then(m => ({default:m.AlertsPage})));
const Reports = lazy(() => import('../pages/InsightPages').then(m => ({default:m.ReportsPage})));
const Ingredients = lazy(() => import('../pages/CatalogIngredients').then(m => ({default:m.IngredientsPage})));
const IngredientDetail = lazy(() => import('../pages/CatalogIngredients').then(m => ({default:m.IngredientDetailPage})));
const Units = lazy(() => import('../pages/CatalogUnits').then(m => ({default:m.UnitsPage})));
const Suppliers = lazy(() => import('../pages/CatalogSuppliers').then(m => ({default:m.SuppliersPage})));
const SupplierDetail = lazy(() => import('../pages/CatalogSuppliers').then(m => ({default:m.SupplierDetailPage})));
const Recipes = lazy(() => import('../pages/CatalogRecipes').then(m => ({default:m.RecipesPage})));
const RecipeDetail = lazy(() => import('../pages/CatalogRecipes').then(m => ({default:m.RecipeDetailPage})));
const PurchaseOrders = lazy(() => import('../pages/PurchasingPages').then(m => ({default:m.PurchaseOrdersPage})));
const PurchaseOrderEditor = lazy(() => import('../pages/PurchasingPages').then(m => ({default:m.PurchaseOrderEditorPage})));
const PurchaseOrderDetail = lazy(() => import('../pages/PurchasingPages').then(m => ({default:m.PurchaseOrderDetailPage})));
const Receipts = lazy(() => import('../pages/PurchasingPages').then(m => ({default:m.GoodsReceiptsPage})));
const ReceiptEditor = lazy(() => import('../pages/PurchasingPages').then(m => ({default:m.GoodsReceiptEditorPage})));
const ReceiptDetail = lazy(() => import('../pages/PurchasingPages').then(m => ({default:m.GoodsReceiptDetailPage})));
const Stock = lazy(() => import('../pages/StockPages').then(m => ({default:m.StockPage})));
const Lots = lazy(() => import('../pages/StockPages').then(m => ({default:m.LotsPage})));
const LotDetail = lazy(() => import('../pages/StockPages').then(m => ({default:m.LotDetailPage})));
const Movements = lazy(() => import('../pages/StockPages').then(m => ({default:m.MovementsPage})));
const Adjustment = lazy(() => import('../pages/AdjustmentPage').then(m => ({default:m.AdjustmentPage})));
const Stocktakes = lazy(() => import('../pages/StocktakePages').then(m => ({default:m.StocktakesPage})));
const StocktakeCreate = lazy(() => import('../pages/StocktakePages').then(m => ({default:m.StocktakeCreatePage})));
const StocktakeDetail = lazy(() => import('../pages/StocktakePages').then(m => ({default:m.StocktakeDetailPage})));

import { RequireInventoryCapability } from '../auth/InventoryGuards';
export default function InventoryRoutes() {
  return <Suspense fallback={<LoadingState />}><Routes>
    <Route index element={<RequireInventoryCapability><Overview /></RequireInventoryCapability>} />
    <Route path="alerts" element={<RequireInventoryCapability capability="viewStock"><Alerts /></RequireInventoryCapability>} />
    <Route path="ingredients" element={<RequireInventoryCapability capability="viewIngredients"><Ingredients /></RequireInventoryCapability>} />
    <Route path="ingredients/:id" element={<RequireInventoryCapability capability="viewIngredients"><IngredientDetail /></RequireInventoryCapability>} />
    <Route path="units" element={<RequireInventoryCapability capability="viewUnits"><Units /></RequireInventoryCapability>} />
    <Route path="recipes" element={<RequireInventoryCapability capability="viewRecipes"><Recipes /></RequireInventoryCapability>} />
    <Route path="recipes/:dishId" element={<RequireInventoryCapability capability="viewRecipes"><RecipeDetail /></RequireInventoryCapability>} />
    <Route path="suppliers" element={<RequireInventoryCapability capability="viewSuppliers"><Suppliers /></RequireInventoryCapability>} />
    <Route path="suppliers/:id" element={<RequireInventoryCapability capability="viewSuppliers"><SupplierDetail /></RequireInventoryCapability>} />
    <Route path="purchase-orders" element={<RequireInventoryCapability capability="viewPurchaseOrders"><PurchaseOrders /></RequireInventoryCapability>} />
    <Route path="purchase-orders/new" element={<RequireInventoryCapability capability="createPurchaseOrders"><PurchaseOrderEditor /></RequireInventoryCapability>} />
    <Route path="purchase-orders/:id/edit" element={<RequireInventoryCapability capability="updatePurchaseOrders"><PurchaseOrderEditor /></RequireInventoryCapability>} />
    <Route path="purchase-orders/:id" element={<RequireInventoryCapability capability="viewPurchaseOrders"><PurchaseOrderDetail /></RequireInventoryCapability>} />
    <Route path="goods-receipts" element={<RequireInventoryCapability capability="viewReceipts"><Receipts /></RequireInventoryCapability>} />
    <Route path="goods-receipts/new" element={<RequireInventoryCapability capability="createReceipts"><ReceiptEditor /></RequireInventoryCapability>} />
    <Route path="goods-receipts/:id" element={<RequireInventoryCapability capability="viewReceipts"><ReceiptDetail /></RequireInventoryCapability>} />
    <Route path="stock" element={<RequireInventoryCapability capability="viewStock"><Stock /></RequireInventoryCapability>} />
    <Route path="lots" element={<RequireInventoryCapability capability="viewStock"><Lots /></RequireInventoryCapability>} />
    <Route path="lots/:id" element={<RequireInventoryCapability capability="viewStock"><LotDetail /></RequireInventoryCapability>} />
    <Route path="movements" element={<RequireInventoryCapability capability="viewStock"><Movements /></RequireInventoryCapability>} />
    <Route path="adjustments/new" element={<RequireInventoryCapability anyOf={['issueStock', 'adjustStock']}><Adjustment /></RequireInventoryCapability>} />
    <Route path="stocktakes" element={<RequireInventoryCapability capability="viewStocktakes"><Stocktakes /></RequireInventoryCapability>} />
    <Route path="stocktakes/new" element={<RequireInventoryCapability capability="createStocktakes"><StocktakeCreate /></RequireInventoryCapability>} />
    <Route path="stocktakes/:id" element={<RequireInventoryCapability capability="viewStocktakes"><StocktakeDetail /></RequireInventoryCapability>} />
    <Route path="reports" element={<RequireInventoryCapability capability="viewReports"><Reports /></RequireInventoryCapability>} />
    <Route path="*" element={<RequireInventoryCapability><EmptyState title="Không tìm thấy trang kho" action={<Link to="/inventory">Về tổng quan kho</Link>} /></RequireInventoryCapability>} />
  </Routes></Suspense>;
}
