import { beforeEach, describe, expect, it, vi } from 'vitest';
import { inventoryApiClient as apiClient } from '../auth/transport';
import { catalogApi, catalogOptions } from '../api/catalog';
import { decimalError } from './CatalogHelpers';

beforeEach(() => vi.restoreAllMocks());
describe('Catalog API contracts', () => {
  it('maps page/search/status to backend pagination without leaking UI query fields', async () => {
    const get = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: { data: { items: [], total: 0, limit: 20, offset: 40 } } });
    await catalogApi.ingredients({ page: 3, search: 'gạo', status: 'ACTIVE' });
    expect(get).toHaveBeenCalledWith('/api/v1/inventory/ingredients', { params: { limit: 20, offset: 40, search: 'gạo', status: 'ACTIVE' }, signal: undefined });
  });

  it('uses PUT and decimal strings for replacing all recipe items', async () => {
    const put = vi.spyOn(apiClient, 'put').mockResolvedValue({ data: { data: {} } });
    const items = [{ ingredient_id: 2, unit_id: 1, quantity: '0.125' }];
    await catalogApi.replaceRecipeItems(7, items);
    expect(put).toHaveBeenCalledWith('/api/v1/recipes/7/items', { items });
  });

  it('deactivates suppliers and mappings through their DELETE endpoints', async () => {
    const del = vi.spyOn(apiClient, 'delete').mockResolvedValue({ data: { data: {} } });
    await catalogApi.deactivateSupplier(4); await catalogApi.deactivateMapping(6);
    expect(del).toHaveBeenNthCalledWith(1, '/api/v1/purchasing/suppliers/4');
    expect(del).toHaveBeenNthCalledWith(2, '/api/v1/purchasing/supplier-ingredients/6');
  });

  it('loads all bounded reference pages and refuses oversized catalogs', async () => {
    const loader = vi.fn().mockResolvedValueOnce({ items: [1], total: 2, limit: 1, offset: 0 }).mockResolvedValueOnce({ items: [2], total: 2, limit: 1, offset: 1 });
    expect(await catalogOptions(loader)).toEqual([1, 2]);
    expect(loader).toHaveBeenNthCalledWith(2, 2);
    await expect(catalogOptions(vi.fn().mockResolvedValue({ items: [], total: 1001, limit: 100, offset: 0 }))).rejects.toThrow('1.000');
  });

  it('validates database precision without converting decimal quantities to float', () => {
    expect(decimalError('99999999999,999')).toBeUndefined();
    expect(decimalError('100000000000')).toBeDefined();
    expect(decimalError('0', 3, true)).toBeDefined();
    expect(decimalError('0.000001', 6, true, 18)).toBeUndefined();
    expect(decimalError('1.0001')).toBeDefined();
  });
});
