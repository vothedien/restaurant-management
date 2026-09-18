import type { InventoryUser } from './types';

// Kept in sync with Inventory Auth's server policy. Coarse existing permissions
// do not expand roles; REPORT_VIEW alone is also assigned to Sales cashiers.
const inventory = ['INVENTORY_MANAGE'];
const purchasing = ['PURCHASE_MANAGE', 'PURCHASE_APPROVE'];
const reference = [...inventory, ...purchasing, 'RECIPE_MANAGE', 'REPORT_VIEW'];
export const CAPABILITY_PERMISSIONS = {
  enterInventory: [...inventory, ...purchasing, 'RECIPE_MANAGE'],
  viewIngredients: reference, manageIngredients: inventory,
  viewUnits: reference, manageUnits: inventory,
  viewRecipes: ['RECIPE_MANAGE'], manageRecipes: ['RECIPE_MANAGE'], activateRecipes: ['RECIPE_MANAGE'],
  viewSuppliers: [...inventory, ...purchasing], manageSuppliers: ['PURCHASE_MANAGE'],
  viewPurchaseOrders: [...inventory, ...purchasing],
  createPurchaseOrders: ['PURCHASE_MANAGE'], updatePurchaseOrders: ['PURCHASE_MANAGE'],
  submitPurchaseOrders: ['PURCHASE_MANAGE'], orderPurchaseOrders: ['PURCHASE_MANAGE'],
  approvePurchaseOrders: ['PURCHASE_APPROVE'], cancelPurchaseOrders: purchasing,
  viewReceipts: [...inventory, ...purchasing], createReceipts: inventory, finalizeReceipts: inventory, cancelReceipts: inventory,
  viewStock: [...inventory, ...purchasing, 'REPORT_VIEW'], issueStock: inventory, adjustStock: inventory,
  viewStocktakes: inventory, createStocktakes: inventory, countStocktakes: inventory, finalizeStocktakes: inventory,
  viewReports: ['REPORT_VIEW'],
} as const;
export type InventoryCapability = keyof typeof CAPABILITY_PERMISSIONS;
export function hasCapability(user: InventoryUser | null, capability: InventoryCapability) {
  return !!user && CAPABILITY_PERMISSIONS.enterInventory.some(permission => user.permissions.includes(permission))
    && CAPABILITY_PERMISSIONS[capability].some(permission => user.permissions.includes(permission));
}
