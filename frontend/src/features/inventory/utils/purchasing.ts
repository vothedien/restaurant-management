import type { OrderTransition, PurchaseOrder, PurchaseOrderStatus, PurchasingMapping, ReceiptItemInput } from '../types/purchasing';
import { addDecimal, compareDecimal, multiplyDecimal, roundDecimal } from './format';

export const orderStatusLabels: Record<PurchaseOrderStatus, string> = {
  DRAFT: 'Nháp', PENDING_APPROVAL: 'Chờ duyệt', APPROVED: 'Đã duyệt', ORDERED: 'Đã đặt hàng',
  PARTIALLY_RECEIVED: 'Đã nhập một phần', RECEIVED: 'Đã nhập đủ', CANCELLED: 'Đã hủy',
};
export function orderActions(status: PurchaseOrderStatus): OrderTransition[] {
  const next: Partial<Record<PurchaseOrderStatus, OrderTransition>> = { DRAFT: 'PENDING_APPROVAL', PENDING_APPROVAL: 'APPROVED', APPROVED: 'ORDERED' };
  return [...(next[status] ? [next[status]!] : []), ...(['DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'ORDERED'].includes(status) ? ['CANCELLED' as const] : [])];
}
export const canReceive = (status: PurchaseOrderStatus) => status === 'ORDERED' || status === 'PARTIALLY_RECEIVED';
export function inputDecimal(value: string) { return value.trim().replace(',', '.'); }
export function decimalError(value: string, scale: number, positive = false): string | undefined {
  const normalized = inputDecimal(value);
  if (!/^\d+(\.\d+)?$/.test(normalized)) return 'Nhập số thập phân hợp lệ.';
  const [whole, fraction = ''] = normalized.split('.');
  if (fraction.replace(/0+$/, '').length > scale) return `Tối đa ${scale} chữ số thập phân.`;
  if (whole.replace(/^0+/, '').length > 14 - scale) return 'Giá trị vượt giới hạn lưu trữ.';
  if (positive && compareDecimal(normalized, '0') <= 0) return 'Số lượng phải lớn hơn 0.';
  return undefined;
}
export function lineAmount(qty: string, price: string): string {
  if (decimalError(qty, 3) || decimalError(price, 2)) return '0';
  return roundDecimal(multiplyDecimal(inputDecimal(qty), inputDecimal(price)), 2);
}
export function orderLineError(mapping: PurchasingMapping | undefined, qty: string, price: string): string | undefined {
  if (!mapping || !mapping.is_active || mapping.ingredient.status !== 'ACTIVE' || mapping.supplier.status !== 'ACTIVE') return 'Liên kết nguyên liệu hoặc nhà cung cấp không còn hoạt động.';
  const error = decimalError(qty, 3, true) || decimalError(price, 2);
  if (error) return error;
  if (compareDecimal(inputDecimal(qty), mapping.minimum_order_qty) < 0) return `Số đặt tối thiểu: ${mapping.minimum_order_qty} ${mapping.purchase_unit.unit_code}.`;
  if (decimalError(multiplyDecimal(inputDecimal(qty), mapping.base_qty_per_purchase_unit), 3, true)) return 'Lượng quy đổi phải biểu diễn chính xác tới 0,001 và trong giới hạn lưu trữ.';
  if (decimalError(lineAmount(qty, price), 2)) return 'Thành tiền vượt giới hạn lưu trữ.';
  return undefined;
}
export function todayISO() { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date()); }
export function receiptLineErrors(order: PurchaseOrder, items: ReceiptItemInput[], receiptDate: string): string[] {
  const errors: string[] = [];
  const totals = new Map<number, string>();
  const lots = new Set<string>();
  if (!receiptDate || receiptDate > todayISO() || receiptDate < order.order_date) errors.push('Ngày nhập phải từ ngày đặt hàng đến hôm nay.');
  if (!items.length) errors.push('Nhập số lượng lớn hơn 0 cho ít nhất một dòng.');
  if (items.length > 200) errors.push('Một phiếu nhập có tối đa 200 dòng lô.');
  items.forEach((item, index) => {
    const po = order.items.find(line => line.purchase_order_item_id === item.purchase_order_item_id);
    const error = decimalError(item.received_quantity, 3, true) || decimalError(item.actual_unit_price, 2);
    if (error) { errors.push(`Dòng ${index + 1}: ${error}`); return; }
    if (!po) { errors.push(`Dòng ${index + 1}: không thuộc đơn mua.`); return; }
    if (decimalError(multiplyDecimal(item.received_quantity, po.base_qty_per_purchase_unit), 3, true)) errors.push(`Dòng ${index + 1}: lượng cơ sở phải chính xác tới 0,001 và trong giới hạn lưu trữ.`);
    if (decimalError(lineAmount(item.received_quantity, item.actual_unit_price), 2)) errors.push(`Dòng ${index + 1}: thành tiền vượt giới hạn lưu trữ.`);
    totals.set(item.purchase_order_item_id, addDecimal(totals.get(item.purchase_order_item_id) ?? '0', item.received_quantity));
    if (item.manufacture_date && item.manufacture_date > receiptDate) errors.push(`Dòng ${index + 1}: ngày sản xuất không được sau ngày nhập.`);
    if (item.expiry_date && (item.expiry_date < receiptDate || (item.manufacture_date && item.expiry_date < item.manufacture_date))) errors.push(`Dòng ${index + 1}: hạn dùng không được trước ngày nhập hoặc ngày sản xuất.`);
    if (item.lot_code) {
      const key = `${po.supplier_ingredient_id}:${item.lot_code.trim()}`;
      if (lots.has(key)) errors.push(`Dòng ${index + 1}: mã lô trùng trong cùng nguyên liệu.`);
      lots.add(key);
    }
  });
  totals.forEach((total, id) => {
    const line = order.items.find(item => item.purchase_order_item_id === id)!;
    if (compareDecimal(total, line.remaining_quantity) > 0) errors.push(`Tổng lượng nhập của dòng đơn #${id} vượt số còn lại ${line.remaining_quantity}.`);
  });
  return errors;
}
