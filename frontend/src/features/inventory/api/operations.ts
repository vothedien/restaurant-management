import { get, patch, post } from './http';
import type { CountDraft, LotContext, OperationBalance, OperationConversion, OperationIngredient, OperationLot, OperationPage, StockChange, Stocktake, StocktakeDetail, StocktakeStatus } from '../types/operations';

const base = '/inventory';
export const listStocktakes = (page: number, status?: StocktakeStatus, signal?: AbortSignal) =>
  get<OperationPage<Stocktake>>(`${base}/stocktakes`, { limit: 20, offset: (page - 1) * 20, status }, signal);
export const getStocktake = (id: number, signal?: AbortSignal) => get<StocktakeDetail>(`${base}/stocktakes/${id}`, undefined, signal);
export const createStocktake = (data: { stocktake_number?: string; created_by: number; notes?: string }) => post<StocktakeDetail>(`${base}/stocktakes`, data);
export const startStocktake = (id: number, lotIds: number[]) => post<StocktakeDetail>(`${base}/stocktakes/${id}/start`, { stock_lot_ids: lotIds });
export const countStocktake = (id: number, itemId: number, draft: CountDraft) => patch<StocktakeDetail>(`${base}/stocktakes/${id}/items/${itemId}`, { actual_quantity: draft.actual.trim().replace(',', '.'), adjustment_reason: draft.reason.trim() });
export const completeStocktake = (id: number, actor: number) => post<StocktakeDetail>(`${base}/stocktakes/${id}/complete`, { completed_by: actor });
export const cancelStocktake = (id: number) => post<StocktakeDetail>(`${base}/stocktakes/${id}/cancel`);
export const listOperationLots = (page: number, ingredientId?: number, signal?: AbortSignal, availableOnly = false) => get<OperationPage<OperationLot>>(`${base}/stock-lots`, { limit: 20, offset: (page - 1) * 20, ingredient_id: ingredientId, available_only: availableOnly }, signal);
export const getOperationLot = (id: number, signal?: AbortSignal) => get<OperationLot>(`${base}/stock-lots/${id}`, undefined, signal);
export const listOperationIngredients = (search: string, page: number, activeOnly = false, signal?: AbortSignal) => get<OperationPage<OperationIngredient>>(`${base}/ingredients`, { search: search || undefined, status: activeOnly ? 'ACTIVE' : undefined, limit: 20, offset: (page - 1) * 20 }, signal);
export const getOperationIngredient = (id: number, signal?: AbortSignal) => get<OperationIngredient>(`${base}/ingredients/${id}`, undefined, signal);
export const getOperationBalance = async (id: number, signal?: AbortSignal) => (await get<OperationPage<OperationBalance>>(`${base}/stock`, { ingredient_id: id, limit: 1, offset: 0 }, signal)).items[0];
export const issueStock = (data: { ingredient_id: number; quantity: string; unit_id: number; performed_by: number; reason: string }) => post<StockChange>(`${base}/stock/issues`, data);
export const adjustStock = (id: number, data: { actual_quantity: string; performed_by: number; reason: string }) => post<StockChange>(`${base}/stock-lots/${id}/adjust`, data);

// Never infer FEFO from a partial, ID-sorted page. Large collections retain the
// server balance but explicitly omit the allocation preview beyond this limit.
async function boundedPages<T>(path: string, params: Record<string, string | number | boolean>, signal?: AbortSignal): Promise<{ items: T[]; complete: boolean }> {
  const first = await get<OperationPage<T>>(path, { ...params, limit: 100, offset: 0 }, signal);
  if (first.total > 1000) return { items: first.items, complete: false };
  const items = [...first.items];
  for (let offset = 100; offset < first.total; offset += 100) {
    const next = await get<OperationPage<T>>(path, { ...params, limit: 100, offset }, signal);
    if (next.total !== first.total || next.items.length === 0) return { items, complete: false };
    items.push(...next.items);
  }
  return { items, complete: items.length === first.total };
}
export const getIssueLots = (id: number, signal?: AbortSignal) => boundedPages<OperationLot>(`${base}/stock-lots`, { ingredient_id: id, available_only: true }, signal);
export const getIssueConversions = (signal?: AbortSignal) => boundedPages<OperationConversion>(`${base}/unit-conversions`, {}, signal);

export async function getLotContexts(ids: number[], signal?: AbortSignal): Promise<Record<number, LotContext>> {
  const result: Record<number, LotContext> = {};
  const ingredients = new Map<number, Promise<OperationIngredient>>();
  let cursor = 0;
  // Detail metadata is loaded only for the visible count page, at most 20 lots.
  await Promise.all(Array.from({ length: Math.min(ids.length, 4) }, async () => {
    while (cursor < ids.length) {
      const id = ids[cursor++];
      const lot = await getOperationLot(id, signal);
      let ingredient = ingredients.get(lot.ingredient_id);
      if (!ingredient) { ingredient = getOperationIngredient(lot.ingredient_id, signal); ingredients.set(lot.ingredient_id, ingredient); }
      result[id] = { lot, ingredient: await ingredient };
    }
  }));
  return result;
}
