import { beforeEach, describe, expect, it, vi } from 'vitest';
import { countStocktake, getIssueLots, issueStock, listStocktakes, startStocktake } from './operations';
import * as http from './http';
import { operationLot, operationPage, stocktakeDocument } from '../tests/operationFixtures';
import { countState, draftFor, matchesCountFilter, planFefo, quantityError } from '../utils/operations';

vi.mock('./http');
beforeEach(() => vi.resetAllMocks());
describe('operations API contracts', () => {
  it('uses true endpoint paths, decimal strings and offset pagination', async () => {
    await listStocktakes(3, 'IN_PROGRESS'); expect(http.get).toHaveBeenCalledWith('/inventory/stocktakes', { limit: 20, offset: 40, status: 'IN_PROGRESS' }, undefined);
    await startStocktake(7, [201]); expect(http.post).toHaveBeenCalledWith('/inventory/stocktakes/7/start', { stock_lot_ids: [201] });
    await countStocktake(7, 71, { actual: '0,125', reason: ' Count ', verified: true }); expect(http.patch).toHaveBeenCalledWith('/inventory/stocktakes/7/items/71', { actual_quantity: '0.125', adjustment_reason: 'Count' });
    const payload = { ingredient_id: 1, quantity: '0.125', unit_id: 2, performed_by: 3, reason: 'Ca chiều' }; await issueStock(payload); expect(http.post).toHaveBeenCalledWith('/inventory/stock/issues', payload);
  });
  it('never presents the first page of large FEFO data as a complete allocation', async () => {
    vi.mocked(http.get).mockResolvedValue(operationPage([operationLot], 1001));
    const result = await getIssueLots(1); expect(result.complete).toBe(false); expect(http.get).toHaveBeenCalledTimes(1);
  });
});
describe('count and FEFO invariants', () => {
  it('distinguishes blank, verified zero, match and difference', () => {
    const item = stocktakeDocument.items[0]; const blank = draftFor(item); expect(blank.actual).toBe(''); expect(countState(item, blank)).toBe('uncounted');
    const zero = { actual: '0', reason: 'Counted zero', verified: true }; expect(countState(item, zero)).toBe('difference'); expect(matchesCountFilter(item, zero, 'counted')).toBe(true);
    expect(countState(item, { actual: '50.000', reason: 'Counted', verified: true })).toBe('matched');
    expect(quantityError('0')).toBeUndefined(); expect(quantityError('0', true)).toBeTruthy(); expect(quantityError('0,001')).toBeUndefined(); expect(quantityError('0.0001')).toBeTruthy(); expect(quantityError('100000000000')).toBeTruthy();
  });
  it('orders expiry, creation and ID using exact decimal allocation', () => {
    const lots = [{ ...operationLot, stock_lot_id: 1, expiry_date: null, current_quantity: '0.300' }, { ...operationLot, stock_lot_id: 2, expiry_date: '2027-01-02', current_quantity: '0.100' }, { ...operationLot, stock_lot_id: 3, expiry_date: '2027-01-01', current_quantity: '0.100' }];
    const result = planFefo(lots, '0.300'); expect(result.allocations.map(row => row.lot.stock_lot_id)).toEqual([3, 2, 1]); expect(result.allocations.map(row => row.quantity)).toEqual(['0.100', '0.100', '0.1']); expect(result.remaining).toBe('0'); expect(result.available).toBe('0.5');
  });
});
