// UI types normalized by backendAdapter from the Inventory Auth HTTP contract.
export interface InventoryUser {
  userId: number;
  username: string;
  displayName: string;
  roles: { code: string; name: string }[];
  permissions: string[];
}
export interface InventoryCredentials { username: string; password: string }
export interface InventorySession { user: InventoryUser; accessToken: string }
export interface InventoryAuthAdapter {
  restoreSession(signal: AbortSignal): Promise<InventorySession | null>;
  signIn(credentials: InventoryCredentials, signal: AbortSignal): Promise<InventorySession>;
  signOut(): Promise<void>;
}
export class AuthUnavailableError extends Error {
  constructor(message = 'Dịch vụ đăng nhập chưa sẵn sàng. Vui lòng liên hệ quản trị hệ thống.') {
    super(message);
    this.name = 'AuthUnavailableError';
  }
}
export function validateSession(session: InventorySession): InventorySession {
  const user = session?.user;
  if (!user || !Number.isSafeInteger(user.userId) || user.userId <= 0 || !user.username?.trim() || !user.displayName?.trim()
    || !Array.isArray(user.roles) || user.roles.some(role => typeof role.code !== 'string' || typeof role.name !== 'string')
    || !Array.isArray(user.permissions) || user.permissions.some(permission => typeof permission !== 'string')
    || typeof session.accessToken !== 'string' || !session.accessToken.trim() || /[\r\n]/.test(session.accessToken)) {
    throw new Error('Không xác minh được phiên đăng nhập. Vui lòng đăng nhập lại.');
  }
  return session;
}
