import { addDecimal, compareDecimal, subtractDecimal } from './format';
import type { CountDraft, CountFilter, OperationLot, StocktakeItem } from '../types/operations';

export function quantityError(value: string, positive = false): string | undefined {
  const normalized = value.trim().replace(',', '.');
  if (!/^\d{1,11}(?:\.\d{1,3})?$/.test(normalized)) return 'Nhập số không âm, tối đa 11 chữ số nguyên và 3 chữ số thập phân.';
  if (positive && compareDecimal(normalized, '0') <= 0) return 'Số lượng phải lớn hơn 0.';
}
export const validActor = (value: string) => /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0;
export const draftFor = (item: StocktakeItem): CountDraft => ({ actual: item.counted ? item.actual_quantity : '', reason: item.adjustment_reason ?? '', verified: item.counted });
export function countState(item: StocktakeItem, draft: CountDraft) {
  if (!draft.verified || quantityError(draft.actual) || !draft.reason.trim()) return 'uncounted';
  return compareDecimal(draft.actual.replace(',', '.'), item.system_quantity) === 0 ? 'matched' : 'difference';
}
export function matchesCountFilter(item: StocktakeItem, draft: CountDraft, filter: CountFilter) {
  const state = countState(item, draft);
  return filter === 'all' || (filter === 'counted' ? state !== 'uncounted' : filter === state);
}
export function planFefo(lots: OperationLot[], requested: string) {
  let remaining = requested;
  const sorted = [...lots].sort((a, b) => (a.expiry_date ?? '9999-12-31').localeCompare(b.expiry_date ?? '9999-12-31') || a.created_at.localeCompare(b.created_at) || a.stock_lot_id - b.stock_lot_id);
  const allocations: { lot: OperationLot; quantity: string; after: string }[] = [];
  for (const lot of sorted) {
    if (compareDecimal(remaining, '0') <= 0) break;
    const take = compareDecimal(remaining, lot.current_quantity) < 0 ? remaining : lot.current_quantity;
    if (compareDecimal(take, '0') > 0) allocations.push({ lot, quantity: take, after: subtractDecimal(lot.current_quantity, take) });
    remaining = subtractDecimal(remaining, take);
  }
  return { allocations, remaining, available: lots.reduce((total, lot) => addDecimal(total, lot.current_quantity), '0') };
}
