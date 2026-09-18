import type { ReactNode } from 'react';
import { InventoryAuthContext } from '../features/inventory/auth/context';
import { hasCapability } from '../features/inventory/auth/permissions';
import type { InventoryUser } from '../features/inventory/auth/types';

const ALL_INVENTORY_PERMISSIONS = ['INVENTORY_MANAGE', 'PURCHASE_MANAGE', 'PURCHASE_APPROVE', 'RECIPE_MANAGE', 'REPORT_VIEW'];
export function InventoryTestSession({ children, userId = 1, permissions = ALL_INVENTORY_PERMISSIONS }: { children: ReactNode; userId?: number; permissions?: string[] }) {
  const user: InventoryUser = { userId, username: 'test-user', displayName: 'Nhân viên kiểm thử', roles: [{ code: 'TEST', name: 'Vai trò kiểm thử' }], permissions };
  return <InventoryAuthContext.Provider value={{ status: 'authenticated', user, unavailable: false, deniedPath: null, can: capability => hasCapability(user, capability), signIn: async () => {}, signOut: async () => {}, retry: () => {}, clearDenied: () => {} }}>{children}</InventoryAuthContext.Provider>;
}
