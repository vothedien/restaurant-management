import { get, type Params } from './http';
import type { Page } from '../types/common';
import type { Ingredient } from '../types/catalog';

export interface Balance { ingredient_id: number; ingredient_code: string; ingredient_name: string; base_unit_id: number; current_quantity: string; available_quantity: string; unavailable_quantity: string }
export interface Lot { stock_lot_id: number; ingredient_id: number; goods_receipt_item_id: number | null; lot_code: string; manufacture_date: string | null; expiry_date: string | null; received_quantity: string; current_quantity: string; unit_cost: string; status: string; created_at: string }
export interface Movement { stock_movement_id: number; movement_number: string; ingredient_id: number; stock_lot_id: number | null; movement_type: string; direction: 'IN' | 'OUT'; quantity: string; occurred_at: string; performed_by: number | null; order_item_id: number | null; goods_receipt_item_id: number | null; stocktake_item_id: number | null; reason: string | null }
export const COLLECTION_LIMIT = 1000;
/** Bounded full collection: never present one server page as a global report. */
export async function collect<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T[]> {
  const first = await get<Page<T>>(path, { ...params, limit: 100, offset: 0 }, signal);
  if (first.total > COLLECTION_LIMIT) throw new Error(`Chưa đủ dữ liệu để tổng hợp: có ${first.total} bản ghi, vượt giới hạn ${COLLECTION_LIMIT}. Thu hẹp bộ lọc; báo cáo toàn kho cần API tổng hợp.`);
  const result = [...first.items];
  for (let offset = 100; offset < first.total; offset += 100) {
    const next = await get<Page<T>>(path, { ...params, limit: 100, offset }, signal);
    if (next.total !== first.total) throw new Error('Danh sách đã thay đổi khi tải. Tải lại để có tập dữ liệu đầy đủ.');
    result.push(...next.items);
  }
  if (result.length !== first.total) throw new Error('Chưa tải đủ dữ liệu. Vui lòng thử tải lại.');
  return result;
}
export async function stockSnapshot(signal?: AbortSignal) {
  const [ingredients, balances, lots] = await Promise.all([
    collect<Ingredient>('/inventory/ingredients', {}, signal), collect<Balance>('/inventory/stock', {}, signal), collect<Lot>('/inventory/stock-lots', {}, signal),
  ]);
  return { ingredients, balances, lots, loadedAt: new Date().toISOString() };
}
export async function stockLabels(ids: number[], signal?: AbortSignal): Promise<Record<number, Ingredient>> {
  // Detail metadata is absent from lot/movement schemas. Resolve only this page.
  const unique = [...new Set(ids)]; const result: Record<number, Ingredient> = {};
  for (let offset = 0; offset < unique.length; offset += 4) {
    const batch = await Promise.all(unique.slice(offset, offset + 4).map(id => get<Ingredient>(`/inventory/ingredients/${id}`, undefined, signal)));
    batch.forEach(item => { result[item.ingredient_id] = item; });
  }
  return result;
}
