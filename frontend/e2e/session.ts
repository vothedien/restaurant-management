import { expect, test as base, type APIRequestContext, type Page } from '@playwright/test';

export const testApi = 'http://127.0.0.1:8011';
export const testOrigin = 'http://localhost:5174';
export const testSessionKey = 'inventory_access_token';
export const fixturePassword = 'inventory-test-only-password';
export type FixtureProfile = 'manager' | 'warehouse' | 'purchaser' | 'sales' | 'locked';

export async function verifyDisposableEnvironment(request: APIRequestContext) {
  const marker = { environment: 'inventory-ui-sqlite-memory', persistent: false, auth: 'inventory-real-backend' };
  for (const origin of [testApi, testOrigin]) {
    const response = await request.get(origin + '/__test__/environment');
    expect(response.ok(), 'Disposable API marker missing at ' + origin).toBe(true);
    expect(await response.json()).toEqual(marker);
  }
  const adapter = await request.get(testOrigin + '/__test__/auth-adapter');
  expect(await adapter.json()).toEqual({ adapter: 'inventory-real-backend', apiTarget: testApi });
}

// Business setup calls authenticate through the real endpoint too. No dependency
// override or test JWT enters the browser/application.
export const test = base.extend({
  request: async ({ playwright }, provideContext) => {
    const anonymous = await playwright.request.newContext();
    let authenticated: APIRequestContext | undefined;
    try {
      await verifyDisposableEnvironment(anonymous);
      const response = await anonymous.post(testApi + '/api/v1/inventory-auth/login', { data: { username: 'manager', password: fixturePassword } });
      expect(response.ok()).toBe(true);
      const data = (await response.json()).data;
      authenticated = await playwright.request.newContext({ extraHTTPHeaders: { Authorization: 'Bearer ' + data.access_token } });
      await provideContext(authenticated);
    } finally {
      await authenticated?.dispose();
      await anonymous.dispose();
    }
  },
});

export async function loginFixture(page: Page, profile: FixtureProfile = 'manager') {
  await page.getByLabel('Tên đăng nhập', { exact: true }).fill(profile);
  await page.getByLabel('Mật khẩu', { exact: true }).fill(fixturePassword);
  await page.getByRole('button', { name: 'Đăng nhập', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Đăng xuất', exact: true })).toBeVisible();
}

export async function prepareInventoryTest({ page, request }: { page: Page; request: APIRequestContext }, options: { anonymous?: boolean; profile?: FixtureProfile } = {}) {
  await verifyDisposableEnvironment(request);
  await page.route('**/api/v1/**', route => new URL(route.request().url()).origin === testOrigin ? route.continue() : route.abort());
  if (!options.anonymous) {
    await page.goto('/inventory/login');
    await loginFixture(page, options.profile);
  }
}
