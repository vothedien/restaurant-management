export type PurchaseOrderStatus = 'DRAFT' | 'PENDING_APPROVAL' | 'APPROVED' | 'ORDERED' | 'PARTIALLY_RECEIVED' | 'RECEIVED' | 'CANCELLED';
export type OrderTransition = 'PENDING_APPROVAL' | 'APPROVED' | 'ORDERED' | 'CANCELLED';
export type ReceiptStatus = 'DRAFT' | 'CONFIRMED' | 'CANCELLED';

export interface PurchasingUnit {
  unit_id: number; unit_code: string; unit_name: string; is_active?: boolean;
}
export interface PurchasingSupplier {
  supplier_id: number; supplier_code: string; supplier_name: string;
  status: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED'; contact_name?: string | null;
  phone?: string | null; email?: string | null;
}
export interface PurchasingMapping {
  supplier_ingredient_id: number; supplier_id: number; ingredient_id: number;
  purchase_unit_id: number; base_qty_per_purchase_unit: string; minimum_order_qty: string;
  latest_unit_price: string | null; is_active: boolean; is_preferred: boolean;
  supplier: PurchasingSupplier;
  ingredient: { ingredient_id: number; ingredient_code: string; ingredient_name: string; base_unit_id: number; status: string };
  purchase_unit: PurchasingUnit;
}
export interface PurchaseOrderItemInput {
  supplier_ingredient_id: number; ordered_quantity: string; expected_unit_price: string;
}
export interface PurchaseOrderItem extends PurchaseOrderItemInput {
  purchase_order_item_id: number; purchase_unit_id: number;
  base_qty_per_purchase_unit: string; ordered_base_qty: string; line_amount: string;
  received_quantity: string; remaining_quantity: string;
}
export interface PurchaseOrder {
  purchase_order_id: number; purchase_order_number: string; supplier_id: number;
  status: PurchaseOrderStatus; order_date: string; expected_delivery_date: string | null;
  created_by: number; approved_by: number | null; subtotal_amount: string; notes: string | null;
  cancelled_at: string | null; cancellation_reason: string | null; created_at: string;
  items: PurchaseOrderItem[];
}
export interface PurchaseOrderCreate {
  purchase_order_number?: string | null; supplier_id: number; created_by: number;
  order_date: string; expected_delivery_date: string | null; notes: string | null;
  items: PurchaseOrderItemInput[];
}
export type PurchaseOrderUpdate = Pick<PurchaseOrderCreate, 'order_date' | 'expected_delivery_date' | 'notes' | 'items'>;
export interface ReceiptItemInput {
  purchase_order_item_id: number; received_quantity: string; actual_unit_price: string;
  lot_code?: string | null; manufacture_date?: string | null; expiry_date?: string | null;
}
export interface ReceiptItem extends ReceiptItemInput {
  goods_receipt_item_id: number; purchase_unit_id: number; base_quantity: string; line_amount: string;
}
export interface GoodsReceipt {
  goods_receipt_id: number; receipt_number: string; purchase_order_id: number; receipt_date: string;
  supplier_document_no: string | null; status: ReceiptStatus; received_by: number;
  notes: string | null; created_at: string; items: ReceiptItem[];
}
export interface GoodsReceiptCreate {
  receipt_number?: string | null; purchase_order_id: number; receipt_date: string;
  supplier_document_no: string | null; received_by: number; notes: string | null; items: ReceiptItemInput[];
}
export interface PurchasingContext {
  supplier: PurchasingSupplier; mappings: PurchasingMapping[]; units: PurchasingUnit[]; complete: boolean;
}
