import { test, prepareInventoryTest } from './session';
import { expect, type APIRequestContext, type Page } from '@playwright/test';
import Decimal from 'decimal.js';

const apiOrigin = 'http://127.0.0.1:8011';

test.beforeEach(async ({ request, page }) => { await prepareInventoryTest({ request, page }); });

async function post<T>(request: APIRequestContext, path: string, data?: unknown): Promise<T> {
  const response = await request.post(`${apiOrigin}/api/v1${path}`, { data });
  expect(response.ok(), await response.text()).toBeTruthy();
  return (await response.json()).data as T;
}

async function seedReceivedLot(request: APIRequestContext) {
  const lotCode = `UI-OPERATIONS-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const order = await post<{ purchase_order_id: number; items: { purchase_order_item_id: number }[] }>(request, '/purchasing/purchase-orders', {
    supplier_id: 1, created_by: 1,
    items: [{ supplier_ingredient_id: 1, ordered_quantity: '1.000', expected_unit_price: '20.00' }],
  });
  for (const status of ['PENDING_APPROVAL', 'APPROVED', 'ORDERED']) await post(request, `/purchasing/purchase-orders/${order.purchase_order_id}/status`, { status, actor_id: 1 });
  const receipt = await post<{ goods_receipt_id: number }>(request, '/purchasing/goods-receipts', {
    purchase_order_id: order.purchase_order_id, received_by: 1,
    items: [{ purchase_order_item_id: order.items[0].purchase_order_item_id, received_quantity: '1.000', actual_unit_price: '20.00', lot_code: lotCode }],
  });
  await post(request, `/purchasing/goods-receipts/${receipt.goods_receipt_id}/confirm`);
  for (let offset = 0; offset < 1000; offset += 100) {
    const response = await request.get(`${apiOrigin}/api/v1/inventory/stock-lots?ingredient_id=1&limit=100&offset=${offset}`);
    expect(response.ok()).toBeTruthy();
    const result = (await response.json()).data as { items: { stock_lot_id: number; lot_code: string }[]; total: number };
    const lot = result.items.find(row => row.lot_code === lotCode);
    if (lot) return lot;
    if (offset + 100 >= result.total) break;
  }
  throw new Error('The isolated receipt did not create the expected test lot.');
}

async function balance(request: APIRequestContext) {
  const response = await request.get(`${apiOrigin}/api/v1/inventory/stock?ingredient_id=1`);
  expect(response.ok()).toBeTruthy();
  return new Decimal((await response.json()).data.items[0].current_quantity as string);
}

async function createAndStart(page: Page, lotCode: string) {
  await page.goto('/inventory/stocktakes/new');
  await page.getByRole('textbox', { name: 'Ghi chú', exact: true }).fill('Kiểm đếm giao diện trong SQLite riêng');
  await expect(page.getByRole('combobox', { name: 'Lọc lô theo nguyên liệu', exact: true })).toBeEnabled();
  await page.getByRole('combobox', { name: 'Lọc lô theo nguyên liệu', exact: true }).selectOption('1');
  for (let pageIndex = 0; pageIndex < 50; pageIndex++) {
    await expect(page.locator('.inv-skeleton')).toHaveCount(0);
    const checkbox = page.getByRole('checkbox', { name: `Chọn lô ${lotCode}`, exact: true });
    if (await checkbox.count()) { await checkbox.check(); break; }
    const next = page.getByRole('button', { name: 'Sau', exact: true }).last();
    if (await next.isDisabled()) throw new Error('Cannot find isolated lot in the stocktake picker.');
    await next.click();
  }
  await expect(page.getByText('Đã chọn 1 / 1.000 lô', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Tạo phiếu nháp', exact: true }).click();
  await expect(page).toHaveURL(/\/inventory\/stocktakes\/\d+$/);
  await expect(page.getByRole('button', { name: 'Bắt đầu kiểm kê', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Bắt đầu kiểm kê', exact: true }).click();
  await page.getByRole('dialog', { name: 'Bắt đầu kiểm kê?' }).getByRole('button', { name: 'Xác nhận', exact: true }).click();
  await expect(page.getByRole('progressbar', { name: 'Tiến độ kiểm kê' })).toHaveAttribute('value', '0');
  return Number(page.url().split('/').at(-1));
}

test('issue, adjust and complete a stocktake using the mobile counting workflow', async ({ page, request }) => {
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message));
  const lot = await seedReceivedLot(request);
  const before = await balance(request);
  await page.goto('/inventory/adjustments/new?ingredient_id=1');
  await expect(page.getByRole('combobox', { name: 'Đơn vị xuất', exact: true })).toBeEnabled();
  await page.getByRole('textbox', { name: 'Số lượng xuất', exact: true }).fill('10');
  await page.getByRole('textbox', { name: 'Lý do (bắt buộc)', exact: true }).fill('Xuất cho ca kiểm thử giao diện');
  await page.getByRole('button', { name: 'Xem lại và xuất kho', exact: true }).click();
  await page.getByRole('dialog', { name: 'Xác nhận xuất kho?' }).getByRole('button', { name: 'Xác nhận', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Đã cập nhật kho', exact: true })).toBeVisible();
  expect((await balance(request)).toFixed()).toBe(before.minus('10').toFixed());

  await page.goto(`/inventory/adjustments/new?ingredient_id=1&lot_id=${lot.stock_lot_id}`);
  await page.getByRole('textbox', { name: 'Số tồn thực tế (G)', exact: true }).fill('980');
  await page.getByRole('textbox', { name: 'Lý do (bắt buộc)', exact: true }).fill('Cân thực tế sau ca');
  await page.getByRole('button', { name: 'Xem lại và điều chỉnh', exact: true }).click();
  await page.getByRole('dialog', { name: 'Xác nhận điều chỉnh lô?' }).getByRole('button', { name: 'Xác nhận', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Đã cập nhật kho', exact: true })).toBeVisible();

  const stocktakeId = await createAndStart(page, lot.lot_code);
  await page.setViewportSize({ width: 390, height: 844 });
  const card = page.locator('.inv-count-mobile');
  const input = card.getByRole('textbox', { name: `Số thực tế lô ${lot.lot_code}`, exact: true });
  await expect(input).toHaveValue('');
  await input.fill('975');
  await card.getByRole('textbox', { name: `Lý do lô ${lot.lot_code}`, exact: true }).fill('Đếm thiếu 5 gram sau ca');
  await card.getByRole('button', { name: 'Xác nhận số đếm', exact: true }).click();
  await expect(page.getByRole('progressbar')).toHaveAttribute('value', '1');
  await page.getByRole('button', { name: 'Lưu số đếm', exact: true }).click();
  await expect(page.getByText('Đã lưu 1 số đếm. Tồn kho chỉ thay đổi khi chốt phiếu.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Rà soát và chốt', exact: true }).click();
  await page.getByRole('dialog', { name: 'Chốt phiếu kiểm kê?' }).getByRole('button', { name: 'Xác nhận', exact: true }).click();
  await expect(page.getByText(/Đã chốt phiếu STK-/)).toBeVisible();
  const documentResponse = await request.get(`${apiOrigin}/api/v1/inventory/stocktakes/${stocktakeId}`);
  expect((await documentResponse.json()).data.status).toBe('COMPLETED');
  const refreshedLot = await request.get(`${apiOrigin}/api/v1/inventory/stock-lots/${lot.stock_lot_id}`);
  expect(new Decimal((await refreshedLot.json()).data.current_quantity).toFixed()).toBe('975');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflow).toBe(false);
  await page.screenshot({ path: '../tmp/inventory-stocktake-mobile.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('a competing real stock adjustment returns 409 without losing entered counts', async ({ page, request }) => {
  const lot = await seedReceivedLot(request);
  await createAndStart(page, lot.lot_code);
  const table = page.locator('.inv-count-desktop');
  const input = table.getByRole('textbox', { name: `Số thực tế lô ${lot.lot_code}`, exact: true });
  await input.fill('950');
  await table.getByRole('textbox', { name: `Lý do lô ${lot.lot_code}`, exact: true }).fill('Số đếm trước giao dịch khác');
  await table.getByRole('button', { name: 'Xác nhận số đếm', exact: true }).click();
  // A second writer touches the same disposable lot after this sheet's snapshot.
  await post(request, `/inventory/stock-lots/${lot.stock_lot_id}/adjust`, { actual_quantity: '990', performed_by: 1, reason: 'Competing isolated test writer' });
  await page.getByRole('button', { name: 'Lưu số đếm', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Dữ liệu tồn kho đã thay đổi', exact: true });
  await expect(dialog).toBeVisible();
  await expect(input).toHaveValue('950');
  await dialog.getByRole('button', { name: 'Tải lại tồn và trạng thái', exact: true }).click();
  await expect(dialog.getByRole('cell', { name: '990 G', exact: true })).toBeVisible();
  await expect(input).toHaveValue('950');
  await expect(dialog.getByRole('link', { name: 'Lập phiếu mới', exact: true })).toHaveAttribute('href', '/inventory/stocktakes/new');
  await dialog.getByRole('button', { name: 'Đóng hộp thoại', exact: true }).click();
  await page.getByRole('button', { name: 'Hủy phiếu', exact: true }).click();
  await page.getByRole('dialog', { name: 'Hủy phiếu kiểm kê?' }).getByRole('button', { name: 'Xác nhận', exact: true }).click();
  await expect(page.getByText('Đã hủy phiếu kiểm kê.', { exact: true })).toBeVisible();
});
