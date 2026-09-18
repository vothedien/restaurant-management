import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { InventoryTestSession } from '../../../test/inventorySession';
import { catalogApi } from '../api/catalog';
import type { Ingredient, RecipeDetail, Unit } from '../types/catalog';
import { IngredientDetailPage, IngredientForm, IngredientsPage } from './CatalogIngredients';
import { RecipeDetailPage } from './CatalogRecipes';
import { UnitsPage } from './CatalogUnits';
import { SupplierDetailPage, SuppliersPage } from './CatalogSuppliers';

const unit: Unit = { unit_id: 1, unit_code: 'KG', unit_name: 'Kilogram', dimension: 'MASS', is_active: true };
const ingredient: Ingredient = { ingredient_id: 7, ingredient_code: 'GA', ingredient_name: 'Thịt gà', base_unit_id: 1, base_unit: unit, manages_lot: true, default_shelf_life_days: null, minimum_stock_qty: '0', safety_stock_qty: '0', status: 'ACTIVE', created_at: '2026-09-15T00:00:00Z', updated_at: '2026-09-15T00:00:00Z' };
const recipe: RecipeDetail = { recipe_version_id: 3, dish_id: 2, version_no: 1, status: 'ACTIVE', effective_from: null, effective_to: null, notes: null, created_by: null, created_at: '2026-09-15T00:00:00Z', dish: { dish_id: 2, dish_code: 'COMGA', dish_name: 'Cơm gà', status: 'ACTIVE' }, items: [] };
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 20, offset: 0 });
function mount(node: ReactNode, path = '/inventory/ingredients', pattern = '*', permissions?: string[]) {
  const router = createMemoryRouter([{ path: pattern, element: node }], { initialEntries: [path] });
  render(<InventoryTestSession permissions={permissions}><RouterProvider router={router} /></InventoryTestSession>);
  return router;
}
beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(catalogApi, 'units').mockResolvedValue(pageOf([unit]));
  vi.spyOn(catalogApi, 'conversions').mockResolvedValue(pageOf([]));
});

describe('Inventory catalog forms', () => {
  it('preserves decimal precision and blocks double submit while saving an ingredient', async () => {
    const user = userEvent.setup(); const saved = vi.fn();
    let finish!: (value: Ingredient) => void;
    const save = vi.spyOn(catalogApi, 'saveIngredient').mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    mount(<IngredientForm onClose={vi.fn()} onSaved={saved} />);
    await screen.findByRole('option', { name: 'KG — Kilogram' });
    await user.type(screen.getByLabelText('Mã nguyên liệu'), 'GA');
    await user.type(screen.getByLabelText('Tên nguyên liệu'), 'Thịt gà');
    await user.selectOptions(screen.getByLabelText('Đơn vị cơ sở'), '1');
    await user.clear(screen.getByLabelText('Mức tồn tối thiểu'));
    await user.type(screen.getByLabelText('Mức tồn tối thiểu'), '12345678901,125');
    const button = screen.getByRole('button', { name: 'Tạo nguyên liệu' });
    await user.click(button);
    fireEvent.submit(button.closest('form')!);
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].minimum_stock_qty).toBe('12345678901.125');
    expect(screen.getByRole('button', { name: 'Đang lưu…' })).toBeDisabled();
    await act(async () => finish(ingredient));
    expect(saved).toHaveBeenCalledWith(ingredient);
  });

  it('shows inline decimal validation and retains the value on 409', async () => {
    const user = userEvent.setup();
    const conflict = Object.assign(new Error('Ingredient code already exists'), { isAxiosError: true, response: { status: 409, data: { message: 'Ingredient code already exists' } } });
    const save = vi.spyOn(catalogApi, 'saveIngredient').mockRejectedValue(conflict);
    mount(<IngredientForm ingredient={ingredient} onClose={vi.fn()} onSaved={vi.fn()} />);
    await screen.findByRole('option', { name: 'KG — Kilogram' });
    await user.clear(screen.getByLabelText('Mức tồn tối thiểu'));
    await user.type(screen.getByLabelText('Mức tồn tối thiểu'), '-1');
    await user.click(screen.getByRole('button', { name: 'Lưu nguyên liệu' }));
    expect(await screen.findByText('Nhập số không âm, tối đa 3 chữ số thập phân.')).toBeVisible();
    expect(save).not.toHaveBeenCalled();
    await user.clear(screen.getByLabelText('Mức tồn tối thiểu'));
    await user.type(screen.getByLabelText('Mức tồn tối thiểu'), '12,5');
    await user.click(screen.getByRole('button', { name: 'Lưu nguyên liệu' }));
    expect(await screen.findByText('Cần đối chiếu dữ liệu')).toBeVisible();
    expect(screen.getByLabelText('Mức tồn tối thiểu')).toHaveValue('12,5');
  });

  it('asks before dismissing unsaved ingredient changes', async () => {
    const user = userEvent.setup(); const close = vi.fn(); const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    mount(<IngredientForm ingredient={ingredient} onClose={close} onSaved={vi.fn()} />);
    await user.type(screen.getByLabelText('Tên nguyên liệu'), ' mới');
    await user.click(screen.getByRole('button', { name: 'Đóng hộp thoại' }));
    expect(confirm).toHaveBeenCalled(); expect(close).not.toHaveBeenCalled();
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Đóng hộp thoại' }));
    expect(close).toHaveBeenCalledOnce();
  });

  it('renders loading, empty, and retryable error states for the ingredient list', async () => {
    let resolve!: (value: ReturnType<typeof pageOf<Ingredient>>) => void;
    const query = vi.spyOn(catalogApi, 'ingredients').mockImplementationOnce(() => new Promise(done => { resolve = done; }));
    mount(<IngredientsPage />);
    expect(screen.getByRole('status')).toBeVisible();
    await act(async () => resolve(pageOf([])));
    expect(screen.getByText('Chưa có nguyên liệu')).toBeVisible();
    query.mockRejectedValue(new Error('Máy chủ chưa sẵn sàng'));
    act(() => window.dispatchEvent(new Event('inventory:refresh')));
    expect(await screen.findByText('Máy chủ chưa sẵn sàng')).toBeVisible();
    query.mockResolvedValue(pageOf([ingredient]));
    await userEvent.click(screen.getByRole('button', { name: 'Tải lại dữ liệu' }));
    expect(await screen.findByRole('link', { name: 'Thịt gà' })).toBeVisible();
  });

  it('keeps historical recipe versions read-only', async () => {
    vi.spyOn(catalogApi, 'recipes').mockResolvedValue(pageOf([recipe]));
    vi.spyOn(catalogApi, 'recipe').mockResolvedValue(recipe);
    mount(<RecipeDetailPage />, '/inventory/recipes/2?version=3', '/inventory/recipes/:dishId');
    expect(await screen.findByText('Phiên bản đã chốt chỉ được xem. Tạo bản nháp mới để thay đổi công thức.')).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Sửa định lượng' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Kích hoạt phiên bản' })).not.toBeInTheDocument();
  });

  it('requires explicit confirmation before recipe activation', async () => {
    const user = userEvent.setup();
    const draft: RecipeDetail = { ...recipe, status: 'DRAFT', items: [{ recipe_item_id: 9, recipe_version_id: 3, ingredient_id: 7, unit_id: 1, quantity: '1', base_quantity: '1', ingredient, unit }] };
    vi.spyOn(catalogApi, 'recipes').mockResolvedValue(pageOf([draft]));
    vi.spyOn(catalogApi, 'recipe').mockResolvedValue(draft);
    const activate = vi.spyOn(catalogApi, 'activateRecipe').mockResolvedValue({ ...draft, status: 'ACTIVE' });
    mount(<RecipeDetailPage />, '/inventory/recipes/2?version=3', '/inventory/recipes/:dishId');
    await user.click(await screen.findByRole('button', { name: 'Kích hoạt phiên bản' }));
    expect(activate).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: 'Kích hoạt phiên bản 1?' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Xác nhận' }));
    await waitFor(() => expect(activate).toHaveBeenCalledExactlyOnceWith(3));
  });

  it('keeps one recipe editor open and guards switching versions with unsaved quantities', async () => {
    const user = userEvent.setup();
    const draft: RecipeDetail = { ...recipe, status: 'DRAFT', items: [{ recipe_item_id: 9, recipe_version_id: 3, ingredient_id: 7, unit_id: 1, quantity: '1', base_quantity: '1', ingredient, unit }] };
    const second: RecipeDetail = { ...recipe, recipe_version_id: 4, version_no: 2 };
    vi.spyOn(catalogApi, 'recipes').mockResolvedValue(pageOf([draft, second]));
    vi.spyOn(catalogApi, 'recipe').mockImplementation(async id => id === 3 ? draft : second);
    vi.spyOn(catalogApi, 'ingredients').mockResolvedValue(pageOf([ingredient]));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const router = mount(<RecipeDetailPage />, '/inventory/recipes/2?version=3', '/inventory/recipes/:dishId');
    await user.click(await screen.findByRole('button', { name: 'Sửa định lượng' }));
    expect(screen.getByRole('button', { name: 'Tạo phiên bản mới' })).toBeDisabled();
    await user.clear(screen.getByLabelText('Định lượng Thịt gà'));
    await user.type(screen.getByLabelText('Định lượng Thịt gà'), '2,5');
    await user.click(screen.getByRole('button', { name: 'Phiên bản 2 · Đang áp dụng' }));
    await waitFor(() => expect(confirm).toHaveBeenCalledOnce());
    expect(router.state.location.search).toBe('?version=3');
    expect(screen.getByLabelText('Định lượng Thịt gà')).toHaveValue('2,5');
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Phiên bản 2 · Đang áp dụng' }));
    await waitFor(() => expect(router.state.location.search).toBe('?version=4'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Tạo phiên bản mới' })).toBeEnabled());
    expect(screen.queryByLabelText('Định lượng Thịt gà')).not.toBeInTheDocument();
  });

  it('shows all six supported decimal places in a conversion factor', async () => {
    vi.mocked(catalogApi.conversions).mockResolvedValue(pageOf([{ conversion_id: 1, from_unit_id: 1, to_unit_id: 2, factor: '0.000001', from_unit: unit, to_unit: { ...unit, unit_id: 2, unit_code: 'T' } }]));
    mount(<UnitsPage />, '/inventory/units?tab=conversions');
    expect(await screen.findByText('= 0,000001')).toBeVisible();
  });

  it('prevents same-unit conversions before sending a request', async () => {
    const user = userEvent.setup(); const save = vi.spyOn(catalogApi, 'saveConversion');
    mount(<UnitsPage />, '/inventory/units?tab=conversions');
    await user.click(screen.getByRole('button', { name: 'Thêm quy đổi' }));
    await screen.findAllByRole('option', { name: 'KG — Kilogram' });
    await user.selectOptions(screen.getByLabelText('Đơn vị nguồn'), '1');
    await user.selectOptions(screen.getByLabelText('Đơn vị đích'), '1');
    await user.type(screen.getByLabelText('Hệ số quy đổi'), '1000');
    await user.click(screen.getByRole('button', { name: 'Lưu thay đổi' }));
    expect(screen.getByText('Đơn vị nguồn và đích phải khác nhau.')).toBeVisible();
    expect(save).not.toHaveBeenCalled();
  });

  it('does not load stock or supplier data for a recipe-only ingredient reader', async () => {
    vi.spyOn(catalogApi, 'ingredient').mockResolvedValue(ingredient);
    const stock = vi.spyOn(catalogApi, 'balances').mockResolvedValue(pageOf([]));
    const mappings = vi.spyOn(catalogApi, 'mappings').mockResolvedValue(pageOf([]));
    mount(<IngredientDetailPage />, '/inventory/ingredients/7', '/inventory/ingredients/:id', ['RECIPE_MANAGE']);
    expect(await screen.findByRole('heading', { name: 'Thịt gà' })).toBeVisible();
    expect(screen.getByRole('heading', { name: 'Thiết lập nguyên liệu' })).toBeVisible();
    expect(stock).not.toHaveBeenCalled();
    expect(mappings).not.toHaveBeenCalled();
    expect(screen.queryByRole('button', { name: 'Nhà cung cấp' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sửa nguyên liệu' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Xuất / điều chỉnh' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Tồn theo lô' })).not.toBeInTheDocument();
  });

  it('rejects a directly mounted ingredient editor before loading its options', () => {
    const save = vi.spyOn(catalogApi, 'saveIngredient');
    mount(<IngredientForm ingredient={ingredient} onClose={vi.fn()} onSaved={vi.fn()} />, undefined, undefined, ['PURCHASE_MANAGE']);
    expect(screen.getByText('Không có quyền sửa nguyên liệu')).toBeVisible();
    expect(screen.queryByRole('textbox', { name: 'Tên nguyên liệu' })).not.toBeInTheDocument();
    expect(catalogApi.units).not.toHaveBeenCalled();
    expect(save).not.toHaveBeenCalled();
  });

  it('keeps ingredients and units read-only for purchasing permission', async () => {
    vi.spyOn(catalogApi, 'ingredients').mockResolvedValue(pageOf([ingredient]));
    mount(<><IngredientsPage /><UnitsPage /></>, undefined, undefined, ['PURCHASE_MANAGE']);
    await screen.findByRole('link', { name: 'Thịt gà' });
    await screen.findByText('Kilogram');
    expect(screen.queryByRole('button', { name: 'Thêm nguyên liệu' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Thêm đơn vị' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sửa' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ngừng dùng' })).not.toBeInTheDocument();
  });

  it('keeps suppliers and mappings read-only for inventory permission', async () => {
    const supplier = { supplier_id: 2, supplier_code: 'NCC', supplier_name: 'Nhà cung cấp kiểm thử', status: 'ACTIVE' as const, contact_name: null, phone: null, email: null, address: null, tax_code: null, created_at: '2026-09-15T00:00:00Z', updated_at: '2026-09-15T00:00:00Z' };
    vi.spyOn(catalogApi, 'suppliers').mockResolvedValue(pageOf([supplier]));
    vi.spyOn(catalogApi, 'supplier').mockResolvedValue(supplier);
    vi.spyOn(catalogApi, 'mappings').mockResolvedValue(pageOf([]));
    mount(<><SuppliersPage /><SupplierDetailPage /></>, '/inventory/suppliers/2', '/inventory/suppliers/:id', ['INVENTORY_MANAGE']);
    await screen.findByRole('heading', { name: 'Nhà cung cấp kiểm thử' });
    await screen.findByText('Chưa có liên kết phù hợp');
    expect(screen.getByRole('link', { name: 'Xem đơn mua' })).toBeVisible();
    expect(screen.queryByRole('button', { name: 'Thêm nhà cung cấp' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sửa thông tin' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Sửa' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Ngừng hợp tác' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Thêm nguyên liệu cung cấp' })).not.toBeInTheDocument();
  });
});
