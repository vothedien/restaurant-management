import { render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { InventoryTestSession } from '../../../test/inventorySession';
import { stockSnapshot } from '../api/stock';
import { get } from '../api/http';
import { InventoryOverviewPage } from './InsightPages';

vi.mock('../api/stock', () => ({ stockSnapshot: vi.fn(), collect: vi.fn() }));
vi.mock('../api/http', () => ({ get: vi.fn() }));
function mount(permissions: string[]) {
  const router = createMemoryRouter([{ path: '/inventory', element: <InventoryOverviewPage /> }], { initialEntries: ['/inventory'] });
  render(<InventoryTestSession permissions={permissions}><RouterProvider router={router} /></InventoryTestSession>);
}
beforeEach(() => {
  vi.mocked(stockSnapshot).mockResolvedValue({ ingredients: [], balances: [], lots: [], loadedAt: '2026-09-16T00:00:00Z' });
  vi.mocked(get).mockResolvedValue({ items: [], total: 0, limit: 6, offset: 0 });
});
describe('Overview permission boundaries', () => {
  it('does not load stock or documents for a recipe-only account', () => {
    mount(['RECIPE_MANAGE']);
    expect(screen.getByRole('link', { name: 'Mở công thức món' })).toBeInTheDocument();
    expect(stockSnapshot).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });
  it('does not fetch or present purchase and stocktake counts to an account with recipe and report rights', async () => {
    mount(['RECIPE_MANAGE', 'REPORT_VIEW']);
    await screen.findByText('Giá trị tồn theo lô');
    await waitFor(() => expect(stockSnapshot).toHaveBeenCalledOnce());
    expect(get).toHaveBeenCalledExactlyOnceWith('/inventory/stock-movements', { limit: 6, offset: 0 }, expect.any(AbortSignal));
    expect(screen.queryByText('Đơn mua chờ duyệt')).not.toBeInTheDocument();
    expect(screen.queryByText('Kiểm kê đang thực hiện')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '+ Nhập hàng' })).not.toBeInTheDocument();
  });
});
