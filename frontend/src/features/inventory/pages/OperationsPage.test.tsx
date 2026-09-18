import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { AdjustmentPage } from './AdjustmentPage';
import * as api from '../api/operations';
import { operationBalance, operationConversion, operationIngredient, operationLot, operationPage } from '../tests/operationFixtures';
import { InventoryTestSession } from '../../../test/inventorySession';

vi.mock('../api/operations');
const mock = vi.mocked(api);
function mount(query = 'ingredient_id=1', permissions?: string[]) { render(<InventoryTestSession userId={3} permissions={permissions}><RouterProvider router={createMemoryRouter([{ path: '/inventory/adjustments/new', element: <AdjustmentPage /> }], { initialEntries: [`/inventory/adjustments/new?${query}`] })} /></InventoryTestSession>); }
function fillCommon() {
  fireEvent.change(screen.getByRole('textbox', { name: 'Lý do (bắt buộc)' }), { target: { value: 'Xuất cho ca chiều' } });
}
beforeEach(() => {
  vi.resetAllMocks(); mock.getOperationIngredient.mockResolvedValue(operationIngredient); mock.listOperationIngredients.mockResolvedValue(operationPage([operationIngredient]));
  mock.getOperationLot.mockResolvedValue(operationLot); mock.listOperationLots.mockResolvedValue(operationPage([operationLot]));
  mock.getOperationBalance.mockResolvedValue(operationBalance); mock.getIssueConversions.mockResolvedValue({ complete: true, items: [operationConversion] });
  mock.getIssueLots.mockResolvedValue({ complete: true, items: [operationLot] }); mock.issueStock.mockResolvedValue({ movements: [] }); mock.adjustStock.mockResolvedValue({ movements: [] });
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); }; HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
});
afterEach(cleanup);

describe('stock issue and adjustment', () => {
  it('previews direct unit conversion and sends decimal strings only after confirmation', async () => {
    mount(); await screen.findByRole('option', { name: 'Kilogram (KG)' });
    expect(screen.queryByRole('spinbutton', { name: /nhân viên|người thực hiện/i })).not.toBeInTheDocument();
    expect(screen.getByText('Nhân viên kiểm thử')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Đơn vị xuất' }), { target: { value: '2' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Số lượng xuất' }), { target: { value: '0,02' } }); fillCommon();
    expect(await screen.findAllByText('30 G')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Xem lại và xuất kho' })); expect(mock.issueStock).not.toHaveBeenCalled();
    const dialog = screen.getByRole('dialog', { name: 'Xác nhận xuất kho?' }); fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận' }));
    await waitFor(() => expect(mock.issueStock).toHaveBeenCalledExactlyOnceWith({ ingredient_id: 1, quantity: '0.02', unit_id: 2, performed_by: 3, reason: 'Xuất cho ca chiều' }));
    expect(await screen.findByText('Đã cập nhật kho')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Số lượng xuất' })).toHaveValue('');
  });

  it('rejects over-available and inexact converted quantities', async () => {
    mock.getIssueConversions.mockResolvedValue({ complete: true, items: [{ ...operationConversion, factor: '0.333333' }] });
    mount(); await screen.findByRole('option', { name: 'Kilogram (KG)' }); fillCommon();
    fireEvent.change(screen.getByRole('textbox', { name: 'Số lượng xuất' }), { target: { value: '51' } });
    expect(screen.getByText(/Số lượng xuất vượt tồn khả dụng/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Xem lại và xuất kho' })); expect(screen.queryByRole('dialog', { name: 'Xác nhận xuất kho?' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('combobox', { name: 'Đơn vị xuất' }), { target: { value: '2' } });
    fireEvent.change(screen.getByRole('textbox', { name: 'Số lượng xuất' }), { target: { value: '0.001' } });
    expect(screen.getByText(/Lượng quy đổi phải biểu diễn chính xác/)).toBeInTheDocument(); expect(mock.issueStock).not.toHaveBeenCalled();
  });

  it('caps adjustment at original receipt and permits an explicit zero', async () => {
    mount('ingredient_id=1&lot_id=201'); await screen.findByText(/Lượng nhập gốc:/); fillCommon();
    const amount = screen.getByRole('textbox', { name: 'Số tồn thực tế (G)' }); fireEvent.change(amount, { target: { value: '101' } });
    expect(screen.getByText(/Số thực tế không được vượt lượng nhập gốc/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Xem lại và điều chỉnh' })); expect(mock.adjustStock).not.toHaveBeenCalled();
    fireEvent.change(amount, { target: { value: '0' } }); fireEvent.click(screen.getByRole('button', { name: 'Xem lại và điều chỉnh' }));
    const dialog = screen.getByRole('dialog', { name: 'Xác nhận điều chỉnh lô?' }); fireEvent.click(within(dialog).getByRole('button', { name: 'Xác nhận' }));
    await waitFor(() => expect(mock.adjustStock).toHaveBeenCalledExactlyOnceWith(201, { actual_quantity: '0', performed_by: 3, reason: 'Xuất cho ca chiều' }));
  });

  it('does not load stock or offer adjustments to purchasing-only users', () => {
    mount('ingredient_id=1&lot_id=201', ['PURCHASE_MANAGE']);
    expect(screen.getByText('Không đủ quyền truy cập')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Điều chỉnh một lô' })).not.toBeInTheDocument();
    expect(mock.getOperationLot).not.toHaveBeenCalled();
    expect(mock.getOperationIngredient).not.toHaveBeenCalled();
    expect(mock.adjustStock).not.toHaveBeenCalled();
  });
});
