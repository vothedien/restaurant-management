import type { InventoryCapability } from '../auth/permissions';
export const navigationCapabilities: Record<string, InventoryCapability> = {
  '': 'enterInventory', alerts: 'viewStock', ingredients: 'viewIngredients', units: 'viewUnits', recipes: 'viewRecipes', suppliers: 'viewSuppliers',
  'purchase-orders': 'viewPurchaseOrders', 'goods-receipts': 'viewReceipts', stock: 'viewStock', lots: 'viewStock', movements: 'viewStock',
  'adjustments/new': 'issueStock', stocktakes: 'viewStocktakes', reports: 'viewReports',
};
export const inventoryNavGroups = [
  {label:'Tổng quan',items:[['','Tổng quan kho'],['alerts','Trung tâm cảnh báo']]},
  {label:'Danh mục',items:[['ingredients','Nguyên liệu'],['units','Đơn vị & quy đổi'],['recipes','Công thức món'],['suppliers','Nhà cung cấp']]},
  {label:'Mua & nhập hàng',items:[['purchase-orders','Đơn mua hàng'],['goods-receipts','Phiếu nhập hàng']]},
  {label:'Quản lý tồn',items:[['stock','Tồn kho hiện tại'],['lots','Lô hàng'],['movements','Biến động kho'],['adjustments/new','Xuất / điều chỉnh'],['stocktakes','Kiểm kê']]},
  {label:'Phân tích',items:[['reports','Báo cáo kho']]},
];
