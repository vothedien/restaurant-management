import { test, prepareInventoryTest } from './session';
import { expect } from '@playwright/test';
import Decimal from 'decimal.js';

const testApi = 'http://127.0.0.1:8011';
test.beforeEach(async ({ request, page }) => { await prepareInventoryTest({ request, page }); });

test('recipe creation, direct unit conversion and activation persist through detail refresh', async ({ page, request }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  const units = (await (await request.get(`${testApi}/api/v1/inventory/units?limit=100`)).json()).data.items;
  const kilograms = units.find((unit: { unit_code: string }) => unit.unit_code === 'KG');
  expect(kilograms).toBeTruthy();
  const ingredients = (await (await request.get(`${testApi}/api/v1/inventory/ingredients?search=FLOUR`)).json()).data.items;
  const flour = ingredients.find((ingredient: { ingredient_code: string }) => ingredient.ingredient_code === 'FLOUR');
  expect(flour).toBeTruthy();

  await page.goto('/inventory/recipes');
  await page.getByRole('button', { name: 'Tạo phiên bản công thức', exact: true }).first().click();
  const createDialog = page.getByRole('dialog', { name: 'Tạo phiên bản công thức nháp' });
  await createDialog.getByLabel('ID món đã có trong hệ thống', { exact: true }).fill('1');
  await createDialog.getByLabel('Ghi chú', { exact: true }).fill(`Recipe browser QA ${Date.now()}`);
  const creationResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/recipes') && response.request().method() === 'POST');
  await createDialog.getByRole('button', { name: 'Tạo bản nháp', exact: true }).click();
  const response = await creationResponse;
  expect(response.status()).toBe(201);
  const recipe = (await response.json()).data;
  expect(recipe.status).toBe('DRAFT');
  await expect(page).toHaveURL(new RegExp(`/inventory/recipes/1\\?version=${recipe.recipe_version_id}$`));
  await expect(createDialog).not.toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: `Phiên bản ${recipe.version_no}`, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Kích hoạt phiên bản', exact: true })).toBeDisabled();

  await page.getByRole('button', { name: 'Sửa định lượng', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Tạo phiên bản mới', exact: true })).toBeDisabled();
  await expect(page.getByRole('option', { name: /FLOUR/ })).toBeAttached();
  await page.getByLabel('Chọn nguyên liệu', { exact: true }).selectOption(String(flour.ingredient_id));
  await page.getByLabel(`Định lượng ${flour.ingredient_name}`, { exact: true }).fill('0,250');
  await page.getByLabel(`Đơn vị ${flour.ingredient_name}`, { exact: true }).selectOption(String(kilograms.unit_id));
  const itemsResponse = page.waitForResponse(result => result.url().endsWith(`/recipes/${recipe.recipe_version_id}/items`) && result.request().method() === 'PUT');
  await page.getByRole('button', { name: 'Lưu toàn bộ định lượng', exact: true }).click();
  const itemsResult = await itemsResponse;
  expect(itemsResult.ok()).toBe(true);
  const saved = (await itemsResult.json()).data;
  expect(new Decimal(saved.items[0].quantity).eq('0.250')).toBe(true);
  expect(new Decimal(saved.items[0].base_quantity).eq('250')).toBe(true);
  await expect(page.getByRole('button', { name: 'Kích hoạt phiên bản', exact: true })).toBeEnabled();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await page.getByRole('button', { name: 'Kích hoạt phiên bản', exact: true }).click();
  const activateDialog = page.getByRole('dialog', { name: `Kích hoạt phiên bản ${recipe.version_no}?` });
  await expect(activateDialog).toContainText('sẽ ngừng hoạt động ngay');
  const activateResponse = page.waitForResponse(result => result.url().endsWith(`/recipes/${recipe.recipe_version_id}/activate`) && result.request().method() === 'POST');
  await activateDialog.getByRole('button', { name: 'Xác nhận', exact: true }).click();
  expect((await activateResponse).ok()).toBe(true);
  await expect(activateDialog).not.toBeVisible();
  await expect(page.getByText('Phiên bản đã chốt chỉ được xem. Tạo bản nháp mới để thay đổi công thức.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Sửa định lượng', exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.getByText('Phiên bản đã chốt chỉ được xem. Tạo bản nháp mới để thay đổi công thức.', { exact: true })).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  const active = (await (await request.get(`${testApi}/api/v1/recipes/dishes/1/active`)).json()).data;
  expect(active.recipe_version_id).toBe(recipe.recipe_version_id);
  expect(errors).toEqual([]);
});
