import { test, prepareInventoryTest } from './session';
import { expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import Decimal from 'decimal.js';

const testApi = 'http://127.0.0.1:8011';
test.beforeEach(async ({ request, page }) => { await prepareInventoryTest({ request, page }); });

async function transition(page: Page, label: string, status: string) {
  await page.getByRole('button', { name: label, exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toBeVisible();
  const response = page.waitForResponse(value => value.url().endsWith('/status') && value.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Xác nhận', exact: true }).click();
  const result = await response;
  expect(result.ok()).toBe(true);
  expect((await result.json()).data.status).toBe(status);
  await expect(dialog).not.toBeVisible();
}

test('purchase order approvals and two deliveries update real isolated stock and lots', async ({ page, request }) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const baselineResponse = await request.get(`${testApi}/api/v1/inventory/stock?ingredient_id=1`);
  const baseline = new Decimal((await baselineResponse.json()).data.items[0].current_quantity);
  const code = `PO-UI-${Date.now()}`;
  await page.goto('/inventory/purchase-orders/new');
  await expect(page.getByRole('option', { name: /Local supplier/ })).toBeAttached();
  await page.getByLabel('Nhà cung cấp', { exact: true }).selectOption('1');
  await expect(page.getByRole('option', { name: /FLOUR/ })).toBeAttached();
  await page.getByLabel('Nguyên liệu', { exact: true }).selectOption('1');
  await page.getByRole('button', { name: 'Thêm nguyên liệu', exact: true }).click();
  await page.getByLabel('Số lượng dòng 1', { exact: true }).fill('2,500');
  await page.getByLabel('Đơn giá dòng 1 (VND)', { exact: true }).fill('35000,25');
  await page.getByLabel('Mã đơn (bỏ trống để tạo tự động)', { exact: true }).fill(code);
  const createdResponse = page.waitForResponse(value => value.url().endsWith('/purchasing/purchase-orders') && value.request().method() === 'POST');
  await page.getByRole('button', { name: 'Lưu nháp', exact: true }).click();
  const created = await createdResponse;
  expect(created.status()).toBe(201);
  const purchaseOrder = (await created.json()).data;
  expect(purchaseOrder.status).toBe('DRAFT');
  expect(new Decimal(purchaseOrder.subtotal_amount).eq('87500.63')).toBe(true);
  await expect(page.getByRole('heading', { name: code, exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Lập phiếu nhập', exact: true })).toHaveCount(0);
  await page.goto(`/inventory/purchase-orders/${purchaseOrder.purchase_order_id}/edit`);
  await page.reload();
  await expect(page.getByRole('heading', { name: `Sửa ${code}`, exact: true })).toBeVisible();
  await expect(page.getByLabel('Số lượng dòng 1', { exact: true })).toHaveValue('2.500');
  await page.goto(`/inventory/purchase-orders/${purchaseOrder.purchase_order_id}`);
  await transition(page, 'Gửi duyệt', 'PENDING_APPROVAL');
  await transition(page, 'Duyệt đơn', 'APPROVED');
  await transition(page, 'Xác nhận đã đặt hàng', 'ORDERED');

  for (const delivery of [1, 2]) {
    if (delivery === 1) await page.getByRole('link', { name: 'Lập phiếu nhập', exact: true }).click();
    else {
      await page.goto(`/inventory/purchase-orders/${purchaseOrder.purchase_order_id}`);
      await page.getByRole('link', { name: 'Nhập hàng còn lại', exact: true }).click();
    }
    const quantityField = page.getByLabel(/Số lượng nhập lần này · dòng 1/);
    await expect(quantityField).toHaveValue('');
    await quantityField.fill('1,250');
    await page.getByLabel(/Đơn giá thực nhận · dòng 1/).fill('42000,50');
    const lotCode = `${code}-LOT-${delivery}`;
    await page.getByLabel('Mã lô · dòng 1', { exact: true }).fill(lotCode);
    if (delivery === 1) {
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
      const summaryFacts = await page.locator('.pur-summary .pur-facts').boundingBox();
      const summaryActions = await page.locator('.pur-summary .pur-submit').boundingBox();
      expect(summaryFacts).not.toBeNull();
      expect(summaryActions).not.toBeNull();
      expect(summaryActions!.y).toBeGreaterThanOrEqual(summaryFacts!.y + summaryFacts!.height);
      await page.screenshot({ path: '../tmp/inventory-receiving-390.png', fullPage: true });
    }
    const receiptResponse = page.waitForResponse(value => value.url().endsWith('/purchasing/goods-receipts') && value.request().method() === 'POST');
    await page.getByRole('button', { name: 'Lưu phiếu nháp', exact: true }).click();
    const received = await receiptResponse;
    expect(received.status()).toBe(201);
    const receipt = (await received.json()).data;
    expect(receipt.status).toBe('DRAFT');
    const beforeConfirm = await request.get(`${testApi}/api/v1/inventory/stock?ingredient_id=1`);
    expect(new Decimal((await beforeConfirm.json()).data.items[0].current_quantity).eq(baseline.plus((delivery - 1) * 1250))).toBe(true);
    await expect(page.getByRole('heading', { name: receipt.receipt_number, exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Chốt phiếu nhập', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('không thể sửa hoặc hủy');
    const confirmedResponse = page.waitForResponse(value => value.url().endsWith(`/goods-receipts/${receipt.goods_receipt_id}/confirm`) && value.request().method() === 'POST');
    await dialog.getByRole('button', { name: 'Xác nhận', exact: true }).click();
    expect((await confirmedResponse).ok()).toBe(true);
    await expect(page.getByText(`Đã chốt ${receipt.receipt_number}.`, { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Chốt phiếu nhập', exact: true })).toHaveCount(0);
    const afterConfirm = await request.get(`${testApi}/api/v1/inventory/stock?ingredient_id=1`);
    expect(new Decimal((await afterConfirm.json()).data.items[0].current_quantity).eq(baseline.plus(delivery * 1250))).toBe(true);
    const refreshedOrder = (await (await request.get(`${testApi}/api/v1/purchasing/purchase-orders/${purchaseOrder.purchase_order_id}`)).json()).data;
    expect(refreshedOrder.status).toBe(delivery === 1 ? 'PARTIALLY_RECEIVED' : 'RECEIVED');
    expect(new Decimal(refreshedOrder.items[0].remaining_quantity).eq(delivery === 1 ? '1.250' : '0')).toBe(true);
    await page.getByRole('link', { name: 'Lô của nguyên liệu', exact: true }).click();
    await page.getByRole('link', { name: lotCode, exact: true }).click();
    await expect(page.locator('.inv-page-header h1')).toContainText(lotCode);
    await expect(page.getByRole('alert')).toHaveCount(0);
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  await page.goto(`/inventory/purchase-orders/${purchaseOrder.purchase_order_id}`);
  await expect(page.getByText('Đã nhập đủ', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: 'Nhập hàng còn lại', exact: true })).toHaveCount(0);
  await page.goto('/inventory/stock?ingredient_id=1');
  await expect(page.locator('.inv-stock-row')).toHaveCount(1);
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(errors).toEqual([]);
});
