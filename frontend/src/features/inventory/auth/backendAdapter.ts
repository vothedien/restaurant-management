import axios from 'axios';
import { apiClient, type ApiResponse } from '../../../api/client';
import { AuthUnavailableError, validateSession, type InventoryAuthAdapter, type InventoryUser } from './types';

export const INVENTORY_TOKEN_KEY = 'inventory_access_token';
export const inventoryAuthClient = axios.create({ baseURL: apiClient.defaults.baseURL, timeout: apiClient.defaults.timeout, headers: { Accept: 'application/json' } });
interface UserResponse { user_id: number; username: string; full_name: string; roles: { role_code: string; role_name: string }[]; permissions: string[] }
function normalizeUser(user: UserResponse): InventoryUser {
  return { userId: user.user_id, username: user.username, displayName: user.full_name, roles: user.roles.map(role => ({ code: role.role_code, name: role.role_name })), permissions: user.permissions };
}
async function currentSession(token: string, signal: AbortSignal) {
  const response = await inventoryAuthClient.get<ApiResponse<{ user: UserResponse }>>('/api/v1/inventory-auth/me', { signal, headers: { Authorization: `Bearer ${token}` } });
  signal.throwIfAborted();
  return validateSession({ accessToken: token, user: normalizeUser(response.data.data.user) });
}
export const backendAuthAdapter: InventoryAuthAdapter = {
  async restoreSession(signal) {
    const token = sessionStorage.getItem(INVENTORY_TOKEN_KEY);
    if (token) return currentSession(token, signal);
    const response = await inventoryAuthClient.get<ApiResponse<{ implemented: boolean; configured: boolean }>>('/api/v1/inventory-auth/status', { signal });
    if (!response.data.data.implemented || !response.data.data.configured) throw new AuthUnavailableError('Đăng nhập Kho chưa được cấu hình. Vui lòng liên hệ quản trị hệ thống.');
    return null;
  },
  async signIn(credentials, signal) {
    const response = await inventoryAuthClient.post<ApiResponse<{ access_token: string }>>('/api/v1/inventory-auth/login', credentials, { signal });
    const token = response.data.data.access_token;
    if (typeof token !== 'string' || !token || /[\r\n]/.test(token)) throw new Error('Invalid Inventory session');
    const session = await currentSession(token, signal);
    signal.throwIfAborted();
    sessionStorage.setItem(INVENTORY_TOKEN_KEY, token);
    return session;
  },
  async signOut() {
    const token = sessionStorage.getItem(INVENTORY_TOKEN_KEY);
    // Clear synchronously, before network completion or a subsequent login.
    sessionStorage.removeItem(INVENTORY_TOKEN_KEY);
    if (token) await inventoryAuthClient.post('/api/v1/inventory-auth/logout', null, { headers: { Authorization: `Bearer ${token}` } });
  },
};
