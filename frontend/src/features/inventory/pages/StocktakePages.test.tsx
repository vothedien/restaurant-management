import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AxiosError } from 'axios';
import { StocktakeCreatePage, StocktakeDetailPage, StocktakesPage } from './StocktakePages';
import * as api from '../api/operations';
import { operationContext, operationIngredient, operationLot, operationPage, stocktakeDocument } from '../tests/operationFixtures';
import type { StocktakeDetail } from '../types/operations';
import { InventoryTestSession } from '../../../test/inventorySession';

vi.mock('../api/operations');
const mock = vi.mocked(api);

function mount(path = '/inventory/stocktakes/7', userId = 1, permissions?: string[]) {
  const router = createMemoryRouter([{ path: '/inventory/stocktakes', element: <StocktakesPage /> }, { path: '/inventory/stocktakes/new', element: <StocktakeCreatePage /> }, { path: '/inventory/stocktakes/:id', element: <StocktakeDetailPage /> }, { path: '/inventory/movements', element: <p>Lịch sử kho</p> }], { initialEntries: [path] });
  render(<InventoryTestSession userId={userId} permissions={permissions}><RouterProvider router={router} /></InventoryTestSession>); return router;
}
function countZero() {
  fireEvent.change(screen.getAllByRole('textbox', { name: 'Số thực tế lô FLOUR-01' })[0], { target: { value: '0' } });
  fireEvent.change(screen.getAllByRole('textbox', { name: 'Lý do lô FLOUR-01' })[0], { target: { value: 'Đã cân, hết nguyên liệu' } });
  fireEvent.click(screen.getAllByRole('button', { name: 'Xác nhận số đếm' })[0]);
}
beforeEach(() => {
  vi.resetAllMocks();
  mock.getStocktake.mockResolvedValue(structuredClone(stocktakeDocument));
  mock.getLotContexts.mockResolvedValue(operationContext);
  mock.listOperationIngredients.mockResolvedValue(operationPage([operationIngredient]));
  mock.listOperationLots.mockResolvedValue(operationPage([operationLot]));
  mock.getOperationIngredient.mockResolvedValue(operationIngredient);
  mock.listStocktakes.mockResolvedValue(operationPage([]));
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterEach(cleanup);

describe('stocktake counting workflow', () => {
  it('keeps an uncounted snapshot blank and records an explicit zero before completion', async () => {
    const counted: StocktakeDetail = { ...stocktakeDocument, items: [{ ...stocktakeDocument.items[0], actual_quantity: '0.000', variance_quantity: '-50.000', adjustment_reason: 'Đã cân, hết nguyên liệu', counted: true }] };
    mock.countStocktake.mockResolvedValue(counted);
    mock.completeStocktake.mockResolvedValue({ ...counted, status: 'COMPLETED', completed_by: 1, completed_at: '2026-09-15T08:10:00Z' });
    mount(); await screen.findAllByRole('textbox', { name: 'Số thực tế lô FLOUR-01' });
    expect(screen.getAllByRole('textbox', { name: 'Số thực tế lô FLOUR-01' })[0]).toHaveValue('');
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '0');
    expect(screen.getByRole('button', { name: 'Rà soát và chốt' })).toBeDisabled();
    countZero(); expect(screen.getByRole('progressbar')).toHaveAttribute('value', '1');
    fireEvent.click(screen.getByRole('button', { name: 'Lưu số đếm' }));
    await waitFor(() => expect(mock.countStocktake).toHaveBeenCalledWith(7, 71, { actual: '0', reason: 'Đã cân, hết nguyên liệu', verified: true }));
    expect(screen.queryByRole('spinbutton', { name: /ID người chốt/ })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Rà soát và chốt' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Rà soát và chốt' }));
    const dialog = screen.getByRole('dialog', { name: 'Chốt phiếu kiểm kê?' });
    expect(within(dialog).getByText(/tạo biến động kiểm kê/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận' }));
    await waitFor(() => expect(mock.completeStocktake).toHaveBeenCalledExactlyOnceWith(7, 1));
    expect(await screen.findByText(/Đã chốt phiếu STK-TEST/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Hủy phiếu' })).not.toBeInTheDocument();
  });

  it('retains zero and reason on 409 and offers safe stock refresh and a new sheet', async () => {
    const error = new AxiosError('Conflict', '409', undefined, undefined, { status: 409, data: { message: 'Stock changed after counting started; cancel and start a new stocktake' }, headers: {}, statusText: 'Conflict', config: {} as never });
    mock.countStocktake.mockRejectedValue(error); mount(); await screen.findAllByRole('textbox', { name: 'Số thực tế lô FLOUR-01' });
    countZero(); fireEvent.click(screen.getByRole('button', { name: 'Lưu số đếm' }));
    const dialog = await screen.findByRole('dialog', { name: 'Dữ liệu tồn kho đã thay đổi' });
    expect(within(dialog).getByRole('link', { name: 'Lập phiếu mới' })).toHaveAttribute('href', '/inventory/stocktakes/new');
    fireEvent.click(within(dialog).getByRole('button', { name: 'Tải lại tồn và trạng thái' }));
    await waitFor(() => expect(mock.getStocktake).toHaveBeenCalledTimes(3));
    expect(screen.getAllByRole('textbox', { name: 'Số thực tế lô FLOUR-01' })[0]).toHaveValue('0');
    expect(mock.countStocktake).toHaveBeenCalledTimes(1);
  });

  it('blocks duplicate saves and navigation with unsaved counts', async () => {
    let resolve!: (value: StocktakeDetail) => void;
    mock.countStocktake.mockImplementation(() => new Promise(done => { resolve = done; }));
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
    const router = mount(); await screen.findAllByRole('textbox', { name: 'Số thực tế lô FLOUR-01' });
    countZero(); fireEvent.click(screen.getByRole('link', { name: 'Xem biến động kho' }));
    await waitFor(() => expect(confirm).toHaveBeenCalled()); expect(router.state.location.pathname).toBe('/inventory/stocktakes/7');
    const save = screen.getByRole('button', { name: 'Lưu số đếm' }); fireEvent.click(save); fireEvent.click(save);
    expect(mock.countStocktake).toHaveBeenCalledTimes(1);
    resolve({ ...stocktakeDocument, items: [{ ...stocktakeDocument.items[0], actual_quantity: '0', adjustment_reason: 'Đã cân, hết nguyên liệu', counted: true }] });
    await screen.findByText(/Đã lưu 1 số đếm/); confirm.mockRestore();
  });

  it('attributes a new draft to the session user without an editable actor or automatic start', async () => {
    mock.createStocktake.mockResolvedValue({ ...stocktakeDocument, status: 'DRAFT', items: [] });
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false); mount('/inventory/stocktakes/new', 9);
    expect(screen.queryByRole('spinbutton', { name: /ID người tạo/ })).not.toBeInTheDocument();
    expect(screen.getByText('Nhân viên kiểm thử')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: 'Ghi chú' }), { target: { value: 'Kiểm cuối ca' } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo phiếu nháp' }));
    await waitFor(() => expect(mock.createStocktake).toHaveBeenCalledWith({ created_by: 9, stocktake_number: undefined, notes: 'Kiểm cuối ca' }));
    expect(mock.startStocktake).not.toHaveBeenCalled(); expect(confirm).not.toHaveBeenCalled(); confirm.mockRestore();
  });

  it('does not allow purchasing permissions to create or start stocktakes', () => {
    mount('/inventory/stocktakes/new', 9, ['PURCHASE_MANAGE']);
    expect(screen.getByText('Không đủ quyền truy cập')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Tạo phiếu nháp' })).not.toBeInTheDocument();
    expect(mock.listOperationLots).not.toHaveBeenCalled();
    expect(mock.createStocktake).not.toHaveBeenCalled();
  });

  it('uses backend status pagination and renders the empty list', async () => {
    mount('/inventory/stocktakes?status=COMPLETED&page=2');
    expect(await screen.findByText('Không có phiếu ở trạng thái này')).toBeInTheDocument();
    expect(mock.listStocktakes).toHaveBeenCalledWith(2, 'COMPLETED', expect.any(AbortSignal));
  });
});
