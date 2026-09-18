import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AxiosError } from 'axios';
import type { AxiosAdapter, InternalAxiosRequestConfig } from 'axios';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { inventoryApiClient as apiClient } from '../auth/transport';
import { GoodsReceiptDetailPage, GoodsReceiptEditorPage, PurchaseOrderDetailPage, PurchaseOrderEditorPage, PurchaseOrdersPage } from './PurchasingPages';
import type { GoodsReceipt, GoodsReceiptCreate, PurchaseOrder, PurchaseOrderCreate, PurchasingMapping } from '../types/purchasing';
import { addDecimal, subtractDecimal, todayISO } from '../utils/format';
import { canReceive, decimalError, lineAmount, orderActions, orderLineError, receiptLineErrors } from '../utils/purchasing';
import { InventoryTestSession } from '../../../test/inventorySession';

const supplier = { supplier_id: 1, supplier_code: 'NCC-01', supplier_name: 'Nhà cung cấp An Phú', status: 'ACTIVE' as const, contact_name: 'An', phone: '0900000000', email: null };
const mapping: PurchasingMapping = { supplier_ingredient_id: 1, supplier_id: 1, ingredient_id: 1, purchase_unit_id: 2, base_qty_per_purchase_unit: '1000.000', minimum_order_qty: '1.000', latest_unit_price: '35000.25', is_active: true, is_preferred: true, supplier, ingredient: { ingredient_id: 1, ingredient_code: 'BOT', ingredient_name: 'Bột mì', base_unit_id: 1, status: 'ACTIVE' }, purchase_unit: { unit_id: 2, unit_code: 'KG', unit_name: 'Kilogram' } };
const units = [{ unit_id: 1, unit_code: 'G', unit_name: 'Gram', is_active: true }, { unit_id: 2, unit_code: 'KG', unit_name: 'Kilogram', is_active: true }];
function makeOrder(): PurchaseOrder {
  return { purchase_order_id: 1, purchase_order_number: 'PO-TEST-01', supplier_id: 1, status: 'ORDERED', order_date: todayISO(), expected_delivery_date: null, created_by: 7, approved_by: 7, subtotal_amount: '87500.63', notes: null, cancelled_at: null, cancellation_reason: null, created_at: `${todayISO()}T00:00:00Z`, items: [{ purchase_order_item_id: 1, supplier_ingredient_id: 1, purchase_unit_id: 2, ordered_quantity: '2.500', base_qty_per_purchase_unit: '1000.000', ordered_base_qty: '2500.000', expected_unit_price: '35000.25', line_amount: '87500.63', received_quantity: '0.000', remaining_quantity: '2.500' }] };
}
const originalAdapter = apiClient.defaults.adapter;
let currentOrder: PurchaseOrder;
let receipts: GoodsReceipt[];
let writes: { url: string; body: unknown }[];
let conflict: string | undefined;

function response(config: InternalAxiosRequestConfig, data: unknown) { return { data: { success: true, data }, status: 200, statusText: 'OK', headers: {}, config }; }
function apiFailure(config: InternalAxiosRequestConfig, status: number, message: string) {
  return new AxiosError(message, 'ERR_BAD_RESPONSE', config, undefined, { config, status, statusText: 'Error', headers: {}, data: { success: false, message } });
}
const adapter: AxiosAdapter = async config => {
  const path = config.url!.replace('/api/v1', '');
  const body = typeof config.data === 'string' ? JSON.parse(config.data) : config.data;
  const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });
  if (config.method === 'get') {
    if (path === '/purchasing/suppliers') return response(config, page([supplier]));
    if (path === '/purchasing/suppliers/1') return response(config, supplier);
    if (path === '/purchasing/supplier-ingredients') return response(config, page([mapping]));
    if (path === '/inventory/units') return response(config, page(units));
    if (path === '/purchasing/purchase-orders') return response(config, page([structuredClone(currentOrder)]));
    if (path === '/purchasing/purchase-orders/1') return response(config, structuredClone(currentOrder));
    if (path === '/purchasing/goods-receipts') return response(config, page(structuredClone(receipts)));
    if (/^\/purchasing\/goods-receipts\/\d+$/.test(path)) return response(config, structuredClone(receipts.find(receipt => receipt.goods_receipt_id === Number(path.split('/').at(-1)))));
  }
  if (config.method === 'post') {
    writes.push({ url: path, body });
    if (conflict) throw apiFailure(config, 409, conflict);
    if (path === '/purchasing/purchase-orders') {
      const payload = body as PurchaseOrderCreate;
      currentOrder = { ...makeOrder(), status: 'DRAFT', created_by: payload.created_by, approved_by: null, items: [{ ...makeOrder().items[0], ...payload.items[0] }] };
      return response(config, structuredClone(currentOrder));
    }
    if (path === '/purchasing/purchase-orders/1/status') { currentOrder.status = body.status; return response(config, structuredClone(currentOrder)); }
    if (path === '/purchasing/goods-receipts') {
      const payload = body as GoodsReceiptCreate;
      const id = receipts.length + 1;
      const receipt: GoodsReceipt = { ...payload, goods_receipt_id: id, receipt_number: `GR-TEST-0${id}`, created_at: `${todayISO()}T00:00:00Z`, status: 'DRAFT', items: payload.items.map((item, index) => ({ ...item, goods_receipt_item_id: id * 100 + index, purchase_unit_id: 2, base_quantity: '1250.000', line_amount: lineAmount(item.received_quantity, item.actual_unit_price), lot_code: item.lot_code || `LOT-${id}-${index}` })) };
      receipts.push(receipt); return response(config, structuredClone(receipt));
    }
    if (/^\/purchasing\/goods-receipts\/\d+\/confirm$/.test(path)) {
      const receipt = receipts.find(item => item.goods_receipt_id === Number(path.split('/').at(-2)))!;
      if (receipt.status !== 'CONFIRMED') {
        receipt.status = 'CONFIRMED';
        const qty = receipt.items.reduce((sum, item) => addDecimal(sum, item.received_quantity), '0');
        currentOrder.items[0].received_quantity = addDecimal(currentOrder.items[0].received_quantity, qty);
        currentOrder.items[0].remaining_quantity = subtractDecimal(currentOrder.items[0].ordered_quantity, currentOrder.items[0].received_quantity);
        currentOrder.status = currentOrder.items[0].remaining_quantity === '0' ? 'RECEIVED' : 'PARTIALLY_RECEIVED';
      }
      return response(config, structuredClone(receipt));
    }
  }
  throw new Error(`Unmocked contract: ${config.method} ${path}`);
};

function mount(path: string, permissions?: string[], userId = 7) {
  const router = createMemoryRouter([
    { path: '/inventory/purchase-orders', element: <PurchaseOrdersPage /> },
    { path: '/inventory/purchase-orders/new', element: <PurchaseOrderEditorPage /> },
    { path: '/inventory/purchase-orders/:id', element: <PurchaseOrderDetailPage /> },
    { path: '/inventory/goods-receipts/new', element: <GoodsReceiptEditorPage /> },
    { path: '/inventory/goods-receipts/:id', element: <GoodsReceiptDetailPage /> },
  ], { initialEntries: [path] });
  render(<InventoryTestSession permissions={permissions} userId={userId}><RouterProvider router={router} /></InventoryTestSession>);
  return router;
}
beforeEach(() => { currentOrder = makeOrder(); receipts = []; writes = []; conflict = undefined; apiClient.defaults.adapter = adapter; });
afterEach(() => { apiClient.defaults.adapter = originalAdapter; vi.restoreAllMocks(); });

describe('Purchasing business rules', () => {
  it('shows only backend transitions and receivable states', () => {
    expect(orderActions('DRAFT')).toEqual(['PENDING_APPROVAL', 'CANCELLED']);
    expect(orderActions('PENDING_APPROVAL')).toEqual(['APPROVED', 'CANCELLED']);
    expect(orderActions('APPROVED')).toEqual(['ORDERED', 'CANCELLED']);
    expect(orderActions('ORDERED')).toEqual(['CANCELLED']);
    expect(orderActions('PARTIALLY_RECEIVED')).toEqual([]);
    expect(orderActions('RECEIVED')).toEqual([]);
    expect(canReceive('APPROVED')).toBe(false);
    expect(canReceive('PARTIALLY_RECEIVED')).toBe(true);
  });
  it('rounds commercial amounts HALF_UP and rejects minimum/conversion precision violations', () => {
    expect(lineAmount('2,500', '35000,25')).toBe('87500.63');
    expect(lineAmount('0.001', '5')).toBe('0.01');
    expect(decimalError('999999999999.99', 2)).toBeUndefined();
    expect(decimalError('1000000000000', 2)).toBeDefined();
    expect(orderLineError(mapping, '0.5', '1')).toMatch(/tối thiểu/);
    expect(orderLineError({ ...mapping, base_qty_per_purchase_unit: '0.001' }, '1.001', '1')).toMatch(/0,001/);
    expect(orderLineError(mapping, '1.250', '0')).toBeUndefined();
  });
  it('validates combined split lots against exact remaining and receipt dates', () => {
    const order = makeOrder();
    order.items[0].remaining_quantity = '0.300';
    const lines = [{ purchase_order_item_id: 1, received_quantity: '0.100', actual_unit_price: '1', lot_code: 'A' }, { purchase_order_item_id: 1, received_quantity: '0.200', actual_unit_price: '1', lot_code: 'B' }];
    expect(receiptLineErrors(order, lines, todayISO())).toEqual([]);
    expect(receiptLineErrors(order, [{ ...lines[0], received_quantity: '0.101' }, lines[1]], todayISO()).join(' ')).toMatch(/vượt số còn lại/);
    expect(receiptLineErrors(order, [{ ...lines[0], manufacture_date: '2999-01-01' }], todayISO()).join(' ')).toMatch(/ngày sản xuất/);
    expect(receiptLineErrors(order, [lines[0], { ...lines[1], lot_code: 'A' }], todayISO()).join(' ')).toMatch(/mã lô trùng/);
  });
});

describe('Purchasing screens', () => {
  it('shows empty and retry states on the operational list', async () => {
    apiClient.defaults.adapter = async config => config.url?.endsWith('/purchase-orders') ? response(config, { items: [], total: 0, limit: 20, offset: 0 }) : adapter(config);
    const router = mount('/inventory/purchase-orders');
    expect(screen.getByRole('status', { name: 'Đang tải dữ liệu' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Chưa có đơn mua' })).toBeInTheDocument();
    apiClient.defaults.adapter = async config => { if (config.url?.endsWith('/purchase-orders')) throw apiFailure(config, 503, 'Unavailable'); return adapter(config); };
    await act(() => router.navigate('/inventory/purchase-orders?status=DRAFT'));
    expect(await screen.findByRole('alert')).toHaveTextContent('Hệ thống chưa thể xử lý');
    expect(screen.getByRole('button', { name: 'Tải lại dữ liệu' })).toBeInTheDocument();
  });
  it('keeps receiving quantities blank, requires explicit price and preserves input on 409 and refresh', async () => {
    const user = userEvent.setup();
    mount('/inventory/goods-receipts/new?purchase_order_id=1');
    const qty = await screen.findByLabelText(/Số lượng nhập lần này/);
    expect(qty).toHaveValue('');
    await user.click(screen.getByRole('button', { name: 'Lưu phiếu nháp' }));
    expect(screen.getByText('Nhập số lượng lớn hơn 0 cho ít nhất một dòng.')).toBeInTheDocument();
    await user.type(qty, '1,250');
    expect(screen.queryByLabelText(/ID người/)).not.toBeInTheDocument();
    expect(screen.getByText('Nhân viên kiểm thử')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Lưu phiếu nháp' }));
    expect(writes).toHaveLength(0);
    await user.type(screen.getByLabelText(/Đơn giá thực nhận/), '42000,50');
    conflict = "Receipt would exceed the purchase order's remaining quantity";
    await user.click(screen.getByRole('button', { name: 'Lưu phiếu nháp' }));
    expect(await screen.findByText('Cần đối chiếu dữ liệu')).toBeInTheDocument();
    expect(qty).toHaveValue('1,250');
    currentOrder.items[0].remaining_quantity = '1.000';
    await user.click(screen.getByRole('button', { name: 'Cập nhật số còn phải nhập' }));
    await waitFor(() => expect(screen.getByLabelText(/Số lượng nhập lần này/)).toHaveValue('1,250'));
    expect(await screen.findByText('Tổng các lô vượt số còn phải nhập.')).toBeInTheDocument();
    expect(writes[0].body).toMatchObject({ received_by: 7, items: [{ received_quantity: '1.250', actual_unit_price: '42000.50' }] });
  });
  it('guards navigation after unsaved receiving edits', async () => {
    const user = userEvent.setup();
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    mount('/inventory/goods-receipts/new?purchase_order_id=1');
    await user.type(await screen.findByLabelText(/Số lượng nhập lần này/), '1');
    await user.click(screen.getByRole('link', { name: 'Hủy thao tác' }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(screen.getByLabelText(/Số lượng nhập lần này/)).toHaveValue('1');
  });
  it('blocks duplicate creates while saving', async () => {
    let release: (() => void) | undefined;
    const ready = new Promise<void>(resolve => { release = resolve; });
    apiClient.defaults.adapter = async config => { if (config.method === 'post') await ready; return adapter(config); };
    const user = userEvent.setup();
    mount('/inventory/goods-receipts/new?purchase_order_id=1');
    await user.type(await screen.findByLabelText(/Số lượng nhập lần này/), '1.250');
    await user.type(screen.getByLabelText(/Đơn giá thực nhận/), '42000');
    const button = screen.getByRole('button', { name: 'Lưu phiếu nháp' });
    fireEvent.click(button); fireEvent.click(button);
    expect(button).toBeDisabled();
    await act(async () => release!());
    await screen.findByRole('heading', { name: 'GR-TEST-01' });
    expect(writes.filter(write => write.url === '/purchasing/goods-receipts')).toHaveLength(1);
    expect(writes.some(write => write.url.endsWith('/confirm'))).toBe(false);
  });
  it('creates, approves and receives an order in two explicitly confirmed deliveries', async () => {
    const user = userEvent.setup();
    const router = mount('/inventory/purchase-orders/new');
    await screen.findByRole('option', { name: /An Phú/ });
    await user.selectOptions(await screen.findByLabelText('Nhà cung cấp'), '1');
    await screen.findByRole('option', { name: /Bột mì/ });
    await user.selectOptions(screen.getByLabelText('Nguyên liệu'), '1');
    await user.click(screen.getByRole('button', { name: 'Thêm nguyên liệu' }));
    await user.type(screen.getByLabelText('Số lượng dòng 1'), '2,500');
    await user.type(screen.getByLabelText('Đơn giá dòng 1 (VND)'), '35000,25');
    expect(screen.queryByLabelText(/ID người/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Lưu nháp' }));
    await screen.findByRole('heading', { name: 'PO-TEST-01' });
    expect(writes[0].body).toMatchObject({ created_by: 7, items: [{ supplier_ingredient_id: 1, ordered_quantity: '2.500', expected_unit_price: '35000.25' }] });
    expect(screen.queryByRole('link', { name: 'Lập phiếu nhập' })).not.toBeInTheDocument();
    for (const action of ['Gửi duyệt', 'Duyệt đơn', 'Xác nhận đã đặt hàng']) {
      await user.click(await screen.findByRole('button', { name: action }));
      const dialog = await screen.findByRole('dialog');
      expect(within(dialog).queryByLabelText(/ID người/)).not.toBeInTheDocument();
      expect(within(dialog).getByText('Nhân viên kiểm thử')).toBeInTheDocument();
      await user.click(within(dialog).getByRole('button', { name: 'Xác nhận' }));
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    }
    expect(currentOrder.status).toBe('ORDERED');
    expect(writes.filter(write => write.url.endsWith('/status')).every(write => (write.body as { actor_id: number }).actor_id === 7)).toBe(true);
    await user.click(await screen.findByRole('link', { name: 'Lập phiếu nhập' }));
    for (const id of [1, 2]) {
      if (id === 2) await act(() => router.navigate('/inventory/goods-receipts/new?purchase_order_id=1'));
      await user.type(await screen.findByLabelText(/Số lượng nhập lần này/), '1.250');
      await user.type(screen.getByLabelText(/Đơn giá thực nhận/), '42000.50');
      await user.click(screen.getByRole('button', { name: 'Lưu phiếu nháp' }));
      await screen.findByRole('heading', { name: `GR-TEST-0${id}` });
      expect(receipts[id - 1].status).toBe('DRAFT');
      await user.click(await screen.findByRole('button', { name: 'Chốt phiếu nhập' }));
      const dialog = await screen.findByRole('dialog');
      expect(dialog).toHaveTextContent('không thể sửa hoặc hủy');
      await user.click(within(dialog).getByRole('button', { name: 'Xác nhận' }));
      await screen.findByText(`Đã chốt GR-TEST-0${id}.`);
      expect(currentOrder.status).toBe(id === 1 ? 'PARTIALLY_RECEIVED' : 'RECEIVED');
      expect(currentOrder.items[0].remaining_quantity).toBe(id === 1 ? '1.25' : '0');
      expect(screen.queryByRole('button', { name: 'Chốt phiếu nhập' })).not.toBeInTheDocument();
    }
    expect(writes.filter(write => write.url.endsWith('/confirm'))).toHaveLength(2);
    expect(writes.filter(write => write.url === '/purchasing/goods-receipts').every(write => (write.body as { received_by: number }).received_by === 7)).toBe(true);
  }, 20000);

  it('does not expose approval or order editing to warehouse staff', async () => {
    currentOrder.status = 'PENDING_APPROVAL';
    mount('/inventory/purchase-orders/1', ['INVENTORY_MANAGE']);
    await screen.findByRole('heading', { name: 'PO-TEST-01' });
    expect(screen.queryByRole('button', { name: 'Duyệt đơn' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hủy đơn' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Sửa đơn' })).not.toBeInTheDocument();
    expect(writes).toHaveLength(0);
  });

  it('allows approval with explicit permission and attributes the current user', async () => {
    currentOrder.status = 'PENDING_APPROVAL';
    const user = userEvent.setup();
    mount('/inventory/purchase-orders/1', ['PURCHASE_APPROVE'], 23);
    await user.click(await screen.findByRole('button', { name: 'Duyệt đơn' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).queryByRole('spinbutton')).not.toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Xác nhận' }));
    await waitFor(() => expect(writes).toHaveLength(1));
    expect(writes[0].body).toEqual({ status: 'APPROVED', actor_id: 23 });
  });

  it('keeps receipt drafts read-only for purchasing staff', async () => {
    receipts = [{ goods_receipt_id: 1, purchase_order_id: 1, receipt_number: 'GR-READ-01', receipt_date: todayISO(), received_by: 7, supplier_document_no: null, notes: null, created_at: `${todayISO()}T00:00:00Z`, status: 'DRAFT', items: [] }];
    mount('/inventory/goods-receipts/1', ['PURCHASE_MANAGE']);
    await screen.findByRole('heading', { name: 'GR-READ-01' });
    expect(screen.queryByRole('button', { name: 'Chốt phiếu nhập' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hủy phiếu nháp' })).not.toBeInTheDocument();
    expect(writes).toHaveLength(0);
  });
});
