import { expect, type APIRequestContext } from '@playwright/test';
import { test, fixturePassword, loginFixture, prepareInventoryTest, testApi, testOrigin, testSessionKey } from './session';

// Real bcrypt/JWT Inventory Auth against the disposable SQLite API.
test.beforeEach(async ({ request, page }) => { await prepareInventoryTest({ request, page }, { anonymous: true }); });

async function pendingOrder(request: APIRequestContext) {
  const created = await request.post(`${testApi}/api/v1/purchasing/purchase-orders`, { data: {
    supplier_id: 1, created_by: 1, items: [{ supplier_ingredient_id: 1, ordered_quantity: '1.000', expected_unit_price: '20.00' }],
  } });
  expect(created.ok()).toBe(true);
  const order = (await created.json()).data;
  const submitted = await request.post(`${testApi}/api/v1/purchasing/purchase-orders/${order.purchase_order_id}/status`, { data: { status: 'PENDING_APPROVAL', actor_id: 1 } });
  expect(submitted.ok()).toBe(true);
  return order.purchase_order_id as number;
}

test('[real auth] login returns to the requested Inventory route, refresh restores and logout clears session', async ({ page }) => {
  await page.goto('/inventory/ingredients/1?tab=overview');
  await expect(page).toHaveURL(/\/inventory\/login\?returnTo=/);
  expect(new URL(page.url()).searchParams.get('returnTo')).toBe('/inventory/ingredients/1?tab=overview');
  await loginFixture(page);
  await expect(page).toHaveURL(`${testOrigin}/inventory/ingredients/1?tab=overview`);
  await expect(page.locator('.inv-page-header h1')).toBeVisible();
  await expect(page.locator('a[href^="/sales"]')).toHaveCount(0);
  await expect(page.getByText('Quản lý kiểm thử', { exact: true }).first()).toBeVisible();
  await page.reload();
  await expect(page.locator('.inv-page-header h1')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Đăng xuất', exact: true }).click();
  await expect(page).toHaveURL(/\/inventory\/login/);
  expect(await page.evaluate(key => sessionStorage.getItem(key), testSessionKey)).toBeNull();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Đăng nhập Kho hàng' })).toBeVisible();
});

test('[real auth] bad credentials show an error and an external returnTo never redirects outside Inventory', async ({ page }) => {
  await page.goto('/inventory/login?returnTo=https%3A%2F%2Fexample.invalid%2Foutside');
  await page.getByLabel('Tên đăng nhập', { exact: true }).fill('manager');
  await page.getByLabel('Mật khẩu', { exact: true }).fill('wrong-fixture-password');
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Tên đăng nhập hoặc mật khẩu không đúng.');
  await expect(page.getByLabel('Mật khẩu', { exact: true })).toHaveValue('');
  expect(await page.evaluate(key => sessionStorage.getItem(key), testSessionKey)).toBeNull();
  await page.getByLabel('Mật khẩu', { exact: true }).fill(fixturePassword);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page).toHaveURL(`${testOrigin}/inventory`);
});

test('[real auth] invalid stored token expires the session and returns to login', async ({ page }) => {
  await page.goto('/inventory/login'); await loginFixture(page);
  await page.evaluate(key => sessionStorage.setItem(key, 'deliberately-invalid-test-token'), testSessionKey);
  await page.goto('/inventory/stock');
  await expect(page).toHaveURL(/\/inventory\/login\?returnTo=/);
  await expect(page.getByText('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', { exact: true })).toBeVisible();
  expect(await page.evaluate(key => sessionStorage.getItem(key), testSessionKey)).toBeNull();
});

test('[real auth] a real server 403 shows denial and keeps the authenticated session', async ({ page }) => {
  await page.goto('/inventory/login'); await loginFixture(page, 'warehouse');
  // Simulate an action based on stale client permissions: forward the request
  // to a real restricted endpoint. The server itself produces the 403.
  await page.route(testOrigin + '/api/v1/inventory/ingredients?*', route => route.continue({ url: testOrigin + '/api/v1/recipes' }));
  await page.goto('/inventory/ingredients');
  await expect(page.getByRole('heading', { name: 'Không đủ quyền truy cập' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
  expect(await page.evaluate(key => sessionStorage.getItem(key), testSessionKey)).not.toBeNull();
});

test('[real auth] warehouse permission cannot approve a pending purchase order', async ({ page, request }) => {
  const orderId = await pendingOrder(request);
  await page.goto('/inventory/login'); await loginFixture(page, 'warehouse');
  await page.goto(`/inventory/purchase-orders/${orderId}`);
  await expect(page.locator('.inv-page-header h1')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Duyệt đơn', exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Tạo đơn mua', exact: true })).toHaveCount(0);
  await expect(page.getByRole('spinbutton', { name: /ID người|Mã nhân viên/ })).toHaveCount(0);
});

test('[real auth] purchasing permission cannot load the direct adjustment route', async ({ page }) => {
  await page.goto('/inventory/login'); await loginFixture(page, 'purchaser');
  await page.goto('/inventory/stock');
  await expect(page.locator('.inv-page-header h1')).toBeVisible();
  await expect(page.locator('.inv-stock-row').first()).toBeVisible();
  await expect(page.locator('.inv-skeleton')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Xuất / điều chỉnh', exact: true })).toHaveCount(0);
  const requests: string[] = [];
  page.on('request', request => { if (request.url().includes('/api/v1/') && !request.url().includes('/inventory-auth/')) requests.push(request.url()); });
  await page.goto('/inventory/adjustments/new?ingredient_id=1');
  await expect(page.getByRole('heading', { name: 'Không đủ quyền truy cập' })).toBeVisible();
  expect(requests).toEqual([]);
});

test('[real auth] manager approval uses the current session actor without an ID field', async ({ page, request }) => {
  const orderId = await pendingOrder(request);
  await page.goto('/inventory/login'); await loginFixture(page);
  await page.goto(`/inventory/purchase-orders/${orderId}`);
  await page.getByRole('button', { name: 'Duyệt đơn', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await expect(dialog.getByText('Quản lý kiểm thử', { exact: true })).toBeVisible();
  await expect(dialog.getByRole('spinbutton')).toHaveCount(0);
  const response = page.waitForResponse(value => value.url().endsWith(`/purchase-orders/${orderId}/status`) && value.request().method() === 'POST');
  await dialog.getByRole('button', { name: 'Xác nhận', exact: true }).click();
  const approved = await response;
  expect(approved.ok()).toBe(true);
  expect(approved.request().postDataJSON().actor_id).toBe(1);
  expect((await approved.json()).data.approved_by).toBe(1);
});

test('[real auth] mobile navigation opens, closes with Escape and closes after a route change', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto('/inventory/login'); await loginFixture(page, 'warehouse');
  const toggle = page.getByRole('button', { name: 'Mở menu Kho', exact: true });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(page.getByRole('button', { name: 'Đóng menu Kho', exact: true })).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('navigation', { name: 'Điều hướng Kho hàng' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false'); await expect(toggle).toBeFocused();
  await toggle.click();
  await page.getByRole('navigation', { name: 'Điều hướng Kho hàng' }).getByRole('link', { name: 'Tồn kho hiện tại', exact: true }).click();
  await expect(page).toHaveURL(`${testOrigin}/inventory/stock`);
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
});

test('[real auth] a Sales-only account cannot log into Inventory', async ({ page }) => {
  await page.goto('/inventory/login');
  await page.getByLabel('Tên đăng nhập', { exact: true }).fill('sales');
  await page.getByLabel('Mật khẩu', { exact: true }).fill(fixturePassword);
  const denied = page.waitForResponse(response => response.url().endsWith('/inventory-auth/login'));
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  expect((await denied).status()).toBe(403);
  await expect(page.getByRole('alert')).toContainText('Tài khoản chưa được phép đăng nhập');
  expect(await page.evaluate(key => sessionStorage.getItem(key), testSessionKey)).toBeNull();
  await expect(page.locator('a[href^="/sales"]')).toHaveCount(0);
});

test('[real auth] a locked account cannot log in', async ({ page }) => {
  await page.goto('/inventory/login');
  await page.getByLabel('Tên đăng nhập', { exact: true }).fill('locked');
  await page.getByLabel('Mật khẩu', { exact: true }).fill(fixturePassword);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('Tên đăng nhập hoặc mật khẩu không đúng.');
  expect(await page.evaluate(key => sessionStorage.getItem(key), testSessionKey)).toBeNull();
});
