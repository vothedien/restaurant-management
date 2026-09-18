import { test, prepareInventoryTest } from './session';
import { expect } from '@playwright/test';

// This suite refuses to write unless the separate disposable API is running.
test.beforeEach(async ({ request, page }) => { await prepareInventoryTest({ request, page }); });
test('inventory routes and keyboard-accessible ingredient modal',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const routes=['','alerts','ingredients','ingredients/1','units','recipes','suppliers','suppliers/1','purchase-orders','purchase-orders/new','goods-receipts','goods-receipts/new','stock','lots','movements','adjustments/new','stocktakes','stocktakes/new','reports'];
  for(const route of routes){await page.goto(`/inventory${route?`/${route}`:''}`);await expect(page.locator('.inv-page-header h1')).toBeVisible();await expect(page.locator('.inv-skeleton')).toHaveCount(0);await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.locator('a[href^="/sales"]')).toHaveCount(0);await expect(page.getByRole('spinbutton',{name:/ID người|Mã nhân viên/})).toHaveCount(0);}
  await page.setViewportSize({width:390,height:844});
  await page.goto('/inventory/ingredients');await page.getByRole('button',{name:'Thêm nguyên liệu',exact:true}).first().click();await expect(page.getByRole('dialog')).toBeVisible();await expect(page.getByLabel('Mã nguyên liệu',{exact:true})).toBeFocused();await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).not.toBeVisible();expect(errors).toEqual([]);
});

test('overview and stock stay within all six requested viewport sizes',async({page})=>{
  const errors:string[]=[];page.on('pageerror',error=>errors.push(error.message));page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const viewports=[{width:1440,height:900},{width:1366,height:768},{width:1024,height:768},{width:768,height:1024},{width:390,height:844},{width:375,height:812}];
  for(const viewport of viewports){await page.setViewportSize(viewport);await page.goto('/inventory');await expect(page.getByRole('heading',{name:'Tổng quan kho',exact:true})).toBeVisible();await expect(page.locator('.inv-kpi').first()).toBeVisible();const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);expect(overflow).toBe(false);await page.screenshot({path:`../tmp/inventory-${viewport.width}.png`,fullPage:true});}
  for(const viewport of viewports){await page.setViewportSize(viewport);await page.goto('/inventory/stock');await expect(page.locator('.inv-stock-row').first()).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth)).toBe(false);await page.screenshot({path:`../tmp/inventory-stock-${viewport.width}.png`,fullPage:true});}
  expect(errors).toEqual([]);
});
