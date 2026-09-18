import { get, patch, post } from './http';
import type { Page } from '../types/common';
import type { GoodsReceipt, GoodsReceiptCreate, OrderTransition, PurchaseOrder, PurchaseOrderCreate, PurchaseOrderUpdate, PurchasingContext, PurchasingMapping, PurchasingSupplier, PurchasingUnit } from '../types/purchasing';

type Filters = Record<string, string | number | boolean | undefined>;
const ordersPath = '/purchasing/purchase-orders';
const receiptsPath = '/purchasing/goods-receipts';
export const listPurchaseOrders = (params: Filters = {}, signal?: AbortSignal) => get<Page<PurchaseOrder>>(ordersPath, params, signal);
export const getPurchaseOrder = (id: number, signal?: AbortSignal) => get<PurchaseOrder>(`${ordersPath}/${id}`, undefined, signal);
export const createPurchaseOrder = (body: PurchaseOrderCreate) => post<PurchaseOrder>(ordersPath, body);
export const updatePurchaseOrder = (id: number, body: PurchaseOrderUpdate) => patch<PurchaseOrder>(`${ordersPath}/${id}`, body);
export const transitionPurchaseOrder = (id: number, status: OrderTransition, actor_id: number, cancellation_reason?: string) => post<PurchaseOrder>(`${ordersPath}/${id}/status`, { status, actor_id, ...(status === 'CANCELLED' ? { cancellation_reason } : {}) });
export const listGoodsReceipts = (params: Filters = {}, signal?: AbortSignal) => get<Page<GoodsReceipt>>(receiptsPath, params, signal);
export const getGoodsReceipt = (id: number, signal?: AbortSignal) => get<GoodsReceipt>(`${receiptsPath}/${id}`, undefined, signal);
export const createGoodsReceipt = (body: GoodsReceiptCreate) => post<GoodsReceipt>(receiptsPath, body);
export const confirmGoodsReceipt = (id: number) => post<GoodsReceipt>(`${receiptsPath}/${id}/confirm`);
export const cancelGoodsReceipt = (id: number) => post<GoodsReceipt>(`${receiptsPath}/${id}/cancel`);
export const listPurchasingSuppliers = (params: Filters = {}, signal?: AbortSignal) => get<Page<PurchasingSupplier>>('/purchasing/suppliers', params, signal);
export const listPurchasingMappings = (params: Filters = {}, signal?: AbortSignal) => get<Page<PurchasingMapping>>('/purchasing/supplier-ingredients', params, signal);

// Lookup catalogues have a hard cap. Operational lists always use server pagination.
// Incomplete metadata never becomes a stock/purchasing aggregate.
async function lookupPages<T>(path: string, params: Filters, signal?: AbortSignal) {
  const first = await get<Page<T>>(path, { ...params, limit: 100, offset: 0 }, signal);
  const pages = Math.min(10, Math.ceil(first.total / 100));
  const rest = await Promise.all(Array.from({ length: Math.max(0, pages - 1) }, (_, index) => get<Page<T>>(path, { ...params, limit: 100, offset: (index + 1) * 100 }, signal)));
  return { items: [...first.items, ...rest.flatMap(page => page.items)], complete: first.total <= 1000 };
}
export async function getPurchasingContext(supplierId: number, signal?: AbortSignal, includeUnits = true): Promise<PurchasingContext> {
  const [supplier, mappings, units] = await Promise.all([
    get<PurchasingSupplier>(`/purchasing/suppliers/${supplierId}`, undefined, signal),
    lookupPages<PurchasingMapping>('/purchasing/supplier-ingredients', { supplier_id: supplierId }, signal),
    includeUnits ? lookupPages<PurchasingUnit>('/inventory/units', {}, signal) : Promise.resolve({ items: [], complete: true }),
  ]);
  return { supplier, mappings: mappings.items, units: units.items, complete: mappings.complete && units.complete };
}
