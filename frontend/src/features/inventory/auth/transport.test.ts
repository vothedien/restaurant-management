import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { apiClient } from '../../../api/client';
import { inventoryApiClient, onInventoryAuthorizationFailure, setInventoryCredential, setInventoryRequestLocation } from './transport';

function response(config: InternalAxiosRequestConfig, status = 200) {
  return { config, data: {}, headers: {}, status, statusText: 'Test-only adapter' };
}
afterEach(() => { setInventoryCredential(null); setInventoryRequestLocation(null); });

describe('Inventory-scoped authenticated transport', () => {
  it('attaches the credential to Inventory requests without altering the Sales client', async () => {
    setInventoryCredential('test-only-token');
    let inventoryHeader: unknown;
    let sharedHeader: unknown;
    await inventoryApiClient.get('/api/v1/inventory/stock', { adapter: async config => { inventoryHeader = config.headers.get('Authorization'); return response(config); } });
    await apiClient.get('/test-only/sales', { adapter: async config => { sharedHeader = config.headers.get('Authorization'); return response(config); } });
    expect(inventoryHeader).toBe('Bearer test-only-token');
    expect(sharedHeader).toBeUndefined();
    for (const path of ['/api/v1/sales/tables', '/api/v1/auth/me', 'https://example.invalid/api/v1/inventory/stock']) {
      await inventoryApiClient.get(path, { adapter: async config => { sharedHeader = config.headers.get('Authorization'); return response(config); } });
      expect(sharedHeader).toBeUndefined();
    }
    setInventoryCredential(null);
    await inventoryApiClient.get('/api/v1/inventory/stock', { adapter: async config => { inventoryHeader = config.headers.get('Authorization'); return response(config); } });
    expect(inventoryHeader).toBeUndefined();
  });

  it.each([401, 403] as const)('notifies the active provider for a current %i response', async status => {
    setInventoryCredential('test-only-token');
    setInventoryRequestLocation('/inventory/stock?ingredient_id=4');
    const listener = vi.fn();
    const unsubscribe = onInventoryAuthorizationFailure(listener);
    try {
      await expect(inventoryApiClient.get('/test-only/denied', { adapter: async config => { throw new AxiosError('Denied', 'ERR_BAD_REQUEST', config, undefined, response(config, status)); } })).rejects.toBeInstanceOf(AxiosError);
      expect(listener).toHaveBeenCalledExactlyOnceWith(status, '/inventory/stock?ingredient_id=4');
    } finally { unsubscribe(); }
  });

  it('ignores an old request failure after credentials change', async () => {
    setInventoryCredential('test-only-old-session');
    const listener = vi.fn();
    const unsubscribe = onInventoryAuthorizationFailure(listener);
    let fail!: () => void;
    let started!: () => void;
    const dispatched = new Promise<void>(resolve => { started = resolve; });
    const request = inventoryApiClient.get('/test-only/slow', { adapter: config => new Promise((_resolve, reject) => {
      fail = () => reject(new AxiosError('Expired old session', 'ERR_BAD_REQUEST', config, undefined, response(config, 401)));
      started();
    }) });
    try {
      await dispatched;
      setInventoryCredential('test-only-new-session');
      fail();
      await expect(request).rejects.toBeInstanceOf(AxiosError);
      expect(listener).not.toHaveBeenCalled();
    } finally { unsubscribe(); }
  });
});
