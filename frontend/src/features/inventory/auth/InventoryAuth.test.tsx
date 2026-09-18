import { useEffect } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router-dom';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { InventoryLayout } from '../layouts/InventoryLayout';
import InventoryRoutes from '../routes/InventoryRoutes';
import { InventoryAuthProvider } from './InventoryAuthProvider';
import { InventoryAuthGuard, RequireInventoryCapability } from './InventoryGuards';
import { InventoryLoginPage } from './InventoryLoginPage';
import { backendAuthAdapter, inventoryAuthClient } from './backendAdapter';
import { hasCapability } from './permissions';
import { inventoryReturnTo } from './returnTo';
import { inventoryApiClient, setInventoryCredential } from './transport';
import type { InventoryAuthAdapter, InventorySession } from './types';

// Test-only adapter data. Production has no fabricated user, token, or role login.
const session: InventorySession = {
  accessToken: 'test-only-inventory-session',
  user: {
    userId: 31, username: 'test-manager', displayName: 'Lê An',
    roles: [{ code: 'RESTAURANT_MANAGER', name: 'Quản lý nhà hàng' }],
    permissions: ['INVENTORY_MANAGE', 'PURCHASE_APPROVE', 'REPORT_VIEW'],
  },
};
function makeAdapter(restored: InventorySession | null = null): InventoryAuthAdapter {
  return { restoreSession: vi.fn().mockResolvedValue(restored), signIn: vi.fn().mockResolvedValue(session), signOut: vi.fn().mockResolvedValue(undefined) };
}
function ProtectedData({ title, onMount }: { title: string; onMount: () => void }) {
  useEffect(onMount, [onMount]);
  return <h1>{title}</h1>;
}
function mount(adapter: InventoryAuthAdapter, entry = '/inventory/stock?ingredient_id=4', onMount = vi.fn()) {
  const router = createMemoryRouter([{
    element: <InventoryAuthProvider adapter={adapter}><Outlet /></InventoryAuthProvider>,
    children: [
      { path: '/inventory/login', element: <InventoryLoginPage /> },
      { element: <InventoryAuthGuard />, children: [{ path: '/inventory', element: <InventoryLayout />, children: [
        { index: true, element: <RequireInventoryCapability capability="enterInventory"><ProtectedData title="Tổng quan kiểm thử" onMount={onMount} /></RequireInventoryCapability> },
        { path: 'stock', element: <RequireInventoryCapability capability="viewStock"><ProtectedData title="Tồn kho kiểm thử" onMount={onMount} /></RequireInventoryCapability> },
        { path: 'recipes', element: <RequireInventoryCapability capability="viewRecipes"><ProtectedData title="Công thức kiểm thử" onMount={onMount} /></RequireInventoryCapability> },
        { path: '*', element: <InventoryRoutes /> },
      ] }] },
    ],
  }], { initialEntries: [entry] });
  const rendered = render(<RouterProvider router={router} />);
  return { router, onMount, ...rendered };
}
function submitLogin() {
  fireEvent.change(screen.getByLabelText('Tên đăng nhập'), { target: { value: ' test-manager ' } });
  fireEvent.change(screen.getByLabelText('Mật khẩu'), { target: { value: 'test-only-password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Đăng nhập' }));
}
function response(config: InternalAxiosRequestConfig, status = 200) {
  return { config, data: {}, headers: {}, status, statusText: status === 200 ? 'OK' : 'Denied' };
}
async function authorizationHeader() {
  let header: unknown;
  await inventoryApiClient.get('/api/v1/inventory/token-probe', { adapter: async config => { header = config.headers.get('Authorization'); return response(config); } });
  return header;
}
async function failRequest(status: 401 | 403) {
  await inventoryApiClient.get('/test-only/protected', { adapter: async config => { throw new AxiosError('Denied', 'ERR_BAD_REQUEST', config, undefined, response(config, status)); } }).catch(() => undefined);
}
afterEach(() => { setInventoryCredential(null); });

describe('Inventory authentication with an injected test adapter', () => {
  it('does not expose Inventory menu capabilities to a Sales user with REPORT_VIEW alone', () => {
    const salesUser = { ...session.user, permissions: ['REPORT_VIEW', 'ORDER_CREATE'] };
    expect(hasCapability(salesUser, 'enterInventory')).toBe(false);
    expect(hasCapability(salesUser, 'viewIngredients')).toBe(false);
    expect(hasCapability(salesUser, 'viewStock')).toBe(false);
    expect(hasCapability(salesUser, 'viewReports')).toBe(false);
  });
  it('redirects anonymous direct access to login without mounting protected data', async () => {
    const adapter = makeAdapter();
    const { router, onMount } = mount(adapter);
    await screen.findByRole('heading', { name: 'Đăng nhập Kho hàng' });
    expect(router.state.location.pathname).toBe('/inventory/login');
    expect(new URLSearchParams(router.state.location.search).get('returnTo')).toBe('/inventory/stock?ingredient_id=4');
    expect(onMount).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: /Sales/i })).not.toBeInTheDocument();
  });

  it('logs in through the adapter and returns to the original internal route', async () => {
    const adapter = makeAdapter();
    const { router } = mount(adapter);
    await screen.findByLabelText('Tên đăng nhập');
    submitLogin();
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    expect(router.state.location.pathname + router.state.location.search).toBe('/inventory/stock?ingredient_id=4');
    expect(adapter.signIn).toHaveBeenCalledExactlyOnceWith({ username: 'test-manager', password: 'test-only-password' }, expect.any(AbortSignal));
    expect(await authorizationHeader()).toBe(`Bearer ${session.accessToken}`);
    expect(screen.getByText('Lê An')).toBeInTheDocument();
    expect(screen.queryByText(session.accessToken)).not.toBeInTheDocument();
    expect(screen.getAllByRole('link').every(link => !link.getAttribute('href')?.startsWith('/sales'))).toBe(true);
  });

  it('shows invalid credentials and clears the password without opening protected data', async () => {
    const adapter = makeAdapter();
    vi.mocked(adapter.signIn).mockRejectedValue(new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', undefined, undefined, { status: 401 } as never));
    const { onMount } = mount(adapter);
    await screen.findByLabelText('Tên đăng nhập');
    submitLogin();
    expect(await screen.findByRole('alert')).toHaveTextContent('Tên đăng nhập hoặc mật khẩu không đúng.');
    expect(screen.getByLabelText('Mật khẩu')).toHaveValue('');
    expect(onMount).not.toHaveBeenCalled();
    expect(await authorizationHeader()).toBeUndefined();
  });

  it('restores a session at a nested URL and clears credentials on logout', async () => {
    const adapter = makeAdapter(session);
    const { router } = mount(adapter);
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    expect(adapter.restoreSession).toHaveBeenCalledExactlyOnceWith(expect.any(AbortSignal));
    expect(await authorizationHeader()).toBe(`Bearer ${session.accessToken}`);
    fireEvent.click(screen.getByRole('button', { name: 'Đăng xuất' }));
    await screen.findByRole('heading', { name: 'Đăng nhập Kho hàng' });
    expect(router.state.location.pathname).toBe('/inventory/login');
    expect(await authorizationHeader()).toBeUndefined();
    expect(adapter.signOut).toHaveBeenCalledOnce();
  });

  it('expires the session on a current request 401 and preserves the return path', async () => {
    const adapter = makeAdapter(session);
    const { router } = mount(adapter);
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    await act(() => failRequest(401));
    await screen.findByRole('heading', { name: 'Đăng nhập Kho hàng' });
    expect(screen.getByRole('alert')).toHaveTextContent('Phiên đăng nhập đã hết hạn');
    expect(new URLSearchParams(router.state.location.search).get('returnTo')).toBe('/inventory/stock?ingredient_id=4');
    expect(await authorizationHeader()).toBeUndefined();
    expect(adapter.signOut).toHaveBeenCalledOnce();
  });

  it('replaces a denied request with 403 and keeps the authenticated session', async () => {
    const adapter = makeAdapter(session);
    const { router } = mount(adapter);
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    await act(() => failRequest(403));
    await screen.findByRole('heading', { name: 'Không đủ quyền truy cập' });
    expect(screen.queryByRole('heading', { name: 'Tồn kho kiểm thử' })).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/inventory/stock');
    expect(await authorizationHeader()).toBe(`Bearer ${session.accessToken}`);
    expect(adapter.signOut).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('link', { name: 'Về tổng quan Kho' }));
    await screen.findByRole('heading', { name: 'Tổng quan kiểm thử' });
  });

  it.each(['/inventory', '/inventory/stock?ingredient_id=99'])('ignores a late 403 from another route after navigation to %s', async destination => {
    const { router } = mount(makeAdapter(session));
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    let rejectRequest!: () => void;
    let started!: () => void;
    const dispatched = new Promise<void>(resolve => { started = resolve; });
    const request = inventoryApiClient.post('/test-only/pending-write', {}, { adapter: config => new Promise((_resolve, reject) => {
      rejectRequest = () => reject(new AxiosError('Denied', 'ERR_BAD_REQUEST', config, undefined, response(config, 403)));
      started();
    }) }).catch(() => undefined);
    await dispatched;
    await act(async () => { await router.navigate(destination); });
    await act(async () => { rejectRequest(); await request; });
    expect(router.state.location.pathname + router.state.location.search).toBe(destination);
    expect(screen.queryByRole('heading', { name: 'Không đủ quyền truy cập' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: destination === '/inventory' ? 'Tổng quan kiểm thử' : 'Tồn kho kiểm thử' })).toBeInTheDocument();
    expect(await authorizationHeader()).toBe(`Bearer ${session.accessToken}`);
  });

  it('still expires the session for a same-session 401 arriving after navigation', async () => {
    const { router } = mount(makeAdapter(session));
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    let rejectRequest!: () => void;
    let started!: () => void;
    const dispatched = new Promise<void>(resolve => { started = resolve; });
    const request = inventoryApiClient.post('/test-only/pending-write', {}, { adapter: config => new Promise((_resolve, reject) => {
      rejectRequest = () => reject(new AxiosError('Expired', 'ERR_BAD_REQUEST', config, undefined, response(config, 401)));
      started();
    }) }).catch(() => undefined);
    await dispatched;
    await act(async () => { await router.navigate('/inventory'); });
    await act(async () => { rejectRequest(); await request; });
    await screen.findByRole('heading', { name: 'Đăng nhập Kho hàng' });
    expect(new URLSearchParams(router.state.location.search).get('returnTo')).toBe('/inventory');
    expect(await authorizationHeader()).toBeUndefined();
  });

  it('rejects a direct route missing permission before its data child mounts', async () => {
    const { onMount } = mount(makeAdapter(session), '/inventory/recipes');
    await screen.findByRole('heading', { name: 'Không đủ quyền truy cập' });
    expect(onMount).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: 'Công thức món' })).not.toBeInTheDocument();
  });

  it('does not grant Inventory rights from an ADMIN role without permissions', async () => {
    const roleOnly = { ...session, user: { ...session.user, roles: [{ code: 'ADMIN', name: 'Quản trị viên' }], permissions: [] } };
    const { onMount } = mount(makeAdapter(roleOnly), '/inventory');
    await screen.findByRole('heading', { name: 'Không đủ quyền truy cập' });
    expect(onMount).not.toHaveBeenCalled();
    expect(hasCapability(roleOnly.user, 'enterInventory')).toBe(false);
    expect(hasCapability(roleOnly.user, 'adjustStock')).toBe(false);
  });

  it('guards unknown Inventory paths before displaying a not-found page', async () => {
    const noPermissions = { ...session, user: { ...session.user, permissions: [] } };
    mount(makeAdapter(noPermissions), '/inventory/unknown-page');
    await screen.findByRole('heading', { name: 'Không đủ quyền truy cập' });
    expect(screen.queryByText('Không tìm thấy trang kho')).not.toBeInTheDocument();
  });

  it('keeps the not-found page available for users with Inventory access', async () => {
    mount(makeAdapter(session), '/inventory/unknown-page');
    expect(await screen.findByRole('heading', { name: 'Không tìm thấy trang kho' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Không đủ quyền truy cập' })).not.toBeInTheDocument();
  });

  it('closes the mobile menu on Escape and restores focus to its toggle', async () => {
    mount(makeAdapter(session));
    await screen.findByRole('heading', { name: 'Tồn kho kiểm thử' });
    const toggle = screen.getByRole('button', { name: 'Mở menu Kho' });
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveFocus();
  });

  it('keeps the production login unavailable when the real status contract says Auth is not implemented', async () => {
    const get = vi.spyOn(inventoryAuthClient, 'get').mockResolvedValue({ data: { success: true, message: 'Auth status', data: { implemented: true, configured: false } } });
    const { onMount } = mount(backendAuthAdapter);
    await screen.findByRole('heading', { name: 'Đăng nhập Kho hàng' });
    expect(screen.getByRole('status')).toHaveTextContent('Đăng nhập Kho chưa được cấu hình');
    expect(screen.getByLabelText('Tên đăng nhập')).toBeDisabled();
    expect(screen.getByLabelText('Mật khẩu')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Đăng nhập' })).toBeDisabled();
    expect(get).toHaveBeenCalledExactlyOnceWith('/api/v1/inventory-auth/status', { signal: expect.any(AbortSignal) });
    expect(onMount).not.toHaveBeenCalled();
    expect(await authorizationHeader()).toBeUndefined();
  });

  it('ignores a sign-in result arriving after its provider unmounts', async () => {
    let finish!: (value: InventorySession) => void;
    const adapter = makeAdapter();
    vi.mocked(adapter.signIn).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
    const { unmount } = mount(adapter);
    await screen.findByLabelText('Tên đăng nhập');
    submitLogin();
    await waitFor(() => expect(adapter.signIn).toHaveBeenCalledOnce());
    unmount();
    await act(async () => { finish(session); });
    expect(await authorizationHeader()).toBeUndefined();
  });
});

describe('Inventory-only return paths', () => {
  it.each([
    '/inventory', '/inventory/stock?ingredient_id=1', '/inventory/lots/2#movements',
  ])('preserves a valid local destination %s', value => {
    expect(inventoryReturnTo(value)).toBe(value);
  });
  it.each([
    undefined, null, '', 'https://outside.invalid/inventory', '//outside.invalid/inventory',
    '/sales', '/inventory-other', '/inventory/../sales', '/inventory/login', '/inventory/login/reset',
    '/inventory/%2f%2foutside.invalid', '/inventory/%5coutside.invalid', '/inventory/%252foutside.invalid',
    '/inventory/%ZZ', '/inventory/%', '/inventory/\n', '/inventory/\\outside.invalid', '/inventory/%00', '/inventory/%0A',
  ])('rejects unsafe or malformed destination %s', value => {
    expect(inventoryReturnTo(value)).toBe('/inventory');
  });
});
