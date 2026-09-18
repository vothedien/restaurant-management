import { afterEach, describe, expect, it, vi } from 'vitest';
import { backendAuthAdapter, inventoryAuthClient, INVENTORY_TOKEN_KEY } from './backendAdapter';

const user = { user_id: 2, username: 'warehouse', full_name: 'Người dùng kiểm thử', roles: [{ role_code: 'WAREHOUSE', role_name: 'Kho' }], permissions: ['INVENTORY_MANAGE'] };
const envelope = (data: unknown) => ({ data: { success: true, message: 'Test', data } });
afterEach(() => { sessionStorage.clear(); vi.restoreAllMocks(); });
describe('Real Inventory Auth adapter HTTP contract', () => {
  it('posts credentials then loads current rights through me and uses its own session key', async () => {
    const signal = new AbortController().signal;
    sessionStorage.setItem('sales_access_token', 'sales-test-value');
    const post = vi.spyOn(inventoryAuthClient, 'post').mockResolvedValue(envelope({ access_token: 'inventory-test-value' }));
    const get = vi.spyOn(inventoryAuthClient, 'get').mockResolvedValue(envelope({ user }));
    const session = await backendAuthAdapter.signIn({ username: 'warehouse', password: 'fixture-password' }, signal);
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/v1/inventory-auth/login', { username: 'warehouse', password: 'fixture-password' }, { signal });
    expect(get).toHaveBeenCalledExactlyOnceWith('/api/v1/inventory-auth/me', { signal, headers: { Authorization: 'Bearer inventory-test-value' } });
    expect(session.user).toEqual({ userId: 2, username: user.username, displayName: user.full_name, roles: [{ code: 'WAREHOUSE', name: 'Kho' }], permissions: user.permissions });
    expect(sessionStorage.getItem(INVENTORY_TOKEN_KEY)).toBe('inventory-test-value');
    expect(sessionStorage.getItem('sales_access_token')).toBe('sales-test-value');
  });
  it('restores only from me, including newly revoked permissions', async () => {
    sessionStorage.setItem(INVENTORY_TOKEN_KEY, 'inventory-test-value');
    vi.spyOn(inventoryAuthClient, 'get').mockResolvedValue(envelope({ user: { ...user, permissions: [] } }));
    expect((await backendAuthAdapter.restoreSession(new AbortController().signal))?.user.permissions).toEqual([]);
  });
  it('does not persist a login when me fails', async () => {
    vi.spyOn(inventoryAuthClient, 'post').mockResolvedValue(envelope({ access_token: 'inventory-test-value' }));
    vi.spyOn(inventoryAuthClient, 'get').mockRejectedValue(new Error('Unavailable'));
    await expect(backendAuthAdapter.signIn({ username: 'warehouse', password: 'fixture-password' }, new AbortController().signal)).rejects.toThrow();
    expect(sessionStorage.getItem(INVENTORY_TOKEN_KEY)).toBeNull();
  });
  it('does not restore storage from an aborted login', async () => {
    const controller = new AbortController();
    vi.spyOn(inventoryAuthClient, 'post').mockResolvedValue(envelope({ access_token: 'inventory-test-value' }));
    vi.spyOn(inventoryAuthClient, 'get').mockImplementation(async () => { controller.abort(); return envelope({ user }); });
    await expect(backendAuthAdapter.signIn({ username: 'warehouse', password: 'fixture-password' }, controller.signal)).rejects.toThrow();
    expect(sessionStorage.getItem(INVENTORY_TOKEN_KEY)).toBeNull();
  });
  it('always clears local storage immediately even if server logout fails', async () => {
    sessionStorage.setItem(INVENTORY_TOKEN_KEY, 'inventory-test-value');
    const post = vi.spyOn(inventoryAuthClient, 'post').mockRejectedValue(new Error('Offline'));
    const signOut = backendAuthAdapter.signOut();
    expect(sessionStorage.getItem(INVENTORY_TOKEN_KEY)).toBeNull();
    await expect(signOut).rejects.toThrow('Offline');
    expect(post).toHaveBeenCalledExactlyOnceWith('/api/v1/inventory-auth/logout', null, { headers: { Authorization: 'Bearer inventory-test-value' } });
  });
  it('does not erase a newer login when an older logout finishes', async () => {
    sessionStorage.setItem(INVENTORY_TOKEN_KEY, 'old-inventory-value');
    let finish!: () => void;
    vi.spyOn(inventoryAuthClient, 'post').mockImplementation(() => new Promise(resolve => { finish = () => resolve(envelope({ stateless: true })); }));
    const signOut = backendAuthAdapter.signOut();
    sessionStorage.setItem(INVENTORY_TOKEN_KEY, 'new-inventory-value');
    finish(); await signOut;
    expect(sessionStorage.getItem(INVENTORY_TOKEN_KEY)).toBe('new-inventory-value');
  });
  it('allows the actual login form when the server is configured', async () => {
    vi.spyOn(inventoryAuthClient, 'get').mockResolvedValue(envelope({ implemented: true, configured: true }));
    expect(await backendAuthAdapter.restoreSession(new AbortController().signal)).toBeNull();
  });
});
