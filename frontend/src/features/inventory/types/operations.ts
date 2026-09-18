export interface OperationPage<T> { items: T[]; total: number; limit: number; offset: number }
export interface OperationUnit { unit_id: number; unit_code: string; unit_name: string; dimension: string; is_active: boolean }
export interface OperationIngredient {
  ingredient_id: number; ingredient_code: string; ingredient_name: string; base_unit_id: number;
  base_unit: OperationUnit; status: 'ACTIVE' | 'INACTIVE';
}
export interface OperationConversion {
  conversion_id: number; from_unit_id: number; to_unit_id: number; factor: string;
  from_unit: OperationUnit; to_unit: OperationUnit;
}
export interface OperationLot {
  stock_lot_id: number; ingredient_id: number; goods_receipt_item_id: number | null; lot_code: string;
  manufacture_date: string | null; expiry_date: string | null; received_quantity: string;
  current_quantity: string; unit_cost: string; status: 'ACTIVE' | 'DEPLETED' | 'EXPIRED' | 'BLOCKED'; created_at: string;
}
export interface OperationBalance {
  ingredient_id: number; ingredient_code: string; ingredient_name: string; base_unit_id: number;
  current_quantity: string; available_quantity: string; unavailable_quantity: string;
}
export interface OperationMovement {
  stock_movement_id: number; movement_number: string; ingredient_id: number; stock_lot_id: number | null;
  movement_type: 'RECEIPT' | 'CONSUMPTION' | 'ADJUSTMENT' | 'RETURN'; direction: 'IN' | 'OUT';
  quantity: string; occurred_at: string; performed_by: number | null; order_item_id: number | null;
  goods_receipt_item_id: number | null; stocktake_item_id: number | null; reason: string | null; created_at: string;
}
export interface StockChange { movements: OperationMovement[] }
export type StocktakeStatus = 'DRAFT' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
export interface Stocktake {
  stocktake_id: number; stocktake_number: string; status: StocktakeStatus; started_at: string | null;
  completed_at: string | null; created_by: number; completed_by: number | null; notes: string | null; created_at: string;
}
export interface StocktakeItem {
  stocktake_item_id: number; stocktake_id: number; stock_lot_id: number; system_quantity: string;
  actual_quantity: string; variance_quantity: string; adjustment_reason: string | null; counted: boolean;
}
export interface StocktakeDetail extends Stocktake { items: StocktakeItem[] }
export interface CountDraft { actual: string; reason: string; verified: boolean }
export type CountFilter = 'all' | 'uncounted' | 'counted' | 'matched' | 'difference';
export interface LotContext { lot: OperationLot; ingredient: OperationIngredient }
