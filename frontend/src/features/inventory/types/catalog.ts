import type { Page } from './common';

export type CatalogPage<T> = Page<T>;
export type UnitDimension = 'MASS' | 'VOLUME' | 'COUNT' | 'LENGTH' | 'OTHER';
export interface Unit {
  unit_id: number; unit_code: string; unit_name: string; dimension: UnitDimension; is_active: boolean;
}
export type UnitWrite = Omit<Unit, 'unit_id'>;
export interface UnitConversion {
  conversion_id: number; from_unit_id: number; to_unit_id: number; factor: string;
  from_unit: Unit; to_unit: Unit;
}
export type ConversionWrite = Pick<UnitConversion, 'from_unit_id' | 'to_unit_id' | 'factor'>;
export interface Ingredient {
  ingredient_id: number; ingredient_code: string; ingredient_name: string; base_unit_id: number;
  manages_lot: boolean; default_shelf_life_days: number | null; minimum_stock_qty: string;
  safety_stock_qty: string; status: 'ACTIVE' | 'INACTIVE'; created_at: string; updated_at: string;
  base_unit: Unit;
}
export type IngredientWrite = Omit<Ingredient, 'ingredient_id' | 'created_at' | 'updated_at' | 'base_unit'>;
export type SupplierStatus = 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';
export interface Supplier {
  supplier_id: number; supplier_code: string; supplier_name: string; status: SupplierStatus;
  contact_name: string | null; phone: string | null; email: string | null; address: string | null;
  tax_code: string | null; created_at: string; updated_at: string;
}
export type SupplierWrite = Omit<Supplier, 'supplier_id' | 'created_at' | 'updated_at'>;
export interface SupplierIngredient {
  supplier_ingredient_id: number; supplier_id: number; ingredient_id: number;
  supplier_sku: string | null; purchase_unit_id: number; base_qty_per_purchase_unit: string;
  lead_time_days: number; minimum_order_qty: string; latest_unit_price: string | null;
  is_preferred: boolean; is_active: boolean;
  supplier: Pick<Supplier, 'supplier_id' | 'supplier_code' | 'supplier_name' | 'status'>;
  ingredient: Pick<Ingredient, 'ingredient_id' | 'ingredient_code' | 'ingredient_name' | 'base_unit_id' | 'status'>;
  purchase_unit: Unit;
}
export type MappingWrite = Omit<SupplierIngredient, 'supplier_ingredient_id' | 'supplier' | 'ingredient' | 'purchase_unit'>;
export type MappingUpdate = Omit<MappingWrite, 'supplier_id' | 'ingredient_id'>;
export type RecipeStatus = 'DRAFT' | 'ACTIVE' | 'INACTIVE' | 'EXPIRED';
export interface Recipe {
  recipe_version_id: number; dish_id: number; version_no: number; status: RecipeStatus;
  effective_from: string | null; effective_to: string | null; notes: string | null;
  created_by: number | null; created_at: string;
  dish: { dish_id: number; dish_code: string; dish_name: string; status: 'ACTIVE' | 'INACTIVE' | 'SOLD_OUT' };
}
export interface RecipeItemWrite { ingredient_id: number; unit_id: number; quantity: string }
export interface RecipeItem extends RecipeItemWrite {
  recipe_item_id: number; recipe_version_id: number; base_quantity: string;
  ingredient: Pick<Ingredient, 'ingredient_id' | 'ingredient_code' | 'ingredient_name' | 'base_unit_id' | 'status' | 'base_unit'>;
  unit: Unit;
}
export interface RecipeDetail extends Recipe { items: RecipeItem[] }
export type RecipeMetadata = Pick<Recipe, 'effective_from' | 'effective_to' | 'notes'>;
export interface CatalogBalance {
  ingredient_id: number; ingredient_code: string; ingredient_name: string; base_unit_id: number;
  current_quantity: string; available_quantity: string; unavailable_quantity: string;
}
