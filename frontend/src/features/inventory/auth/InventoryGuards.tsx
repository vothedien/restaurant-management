import type { ReactNode } from 'react';
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';
import { LoadingState } from '../components/ui';
import type { InventoryCapability } from './permissions';
import { inventoryReturnTo } from './returnTo';
import { useInventoryAuth } from './useInventoryAuth';

export function InventoryForbidden() {
  const { clearDenied } = useInventoryAuth();
  return <section className="inv-panel inv-forbidden" aria-labelledby="inv-forbidden-title"><p className="inv-muted">403 · Quyền truy cập</p><h1 id="inv-forbidden-title">Không đủ quyền truy cập</h1><p>Tài khoản của bạn chưa được cấp quyền cho trang hoặc thao tác này. Liên hệ quản lý để kiểm tra quyền.</p><Link className="inv-button secondary" to="/inventory" onClick={clearDenied}>Về tổng quan Kho</Link></section>;
}
export function InventoryAuthGuard() {
  const { status } = useInventoryAuth();
  const location = useLocation();
  if (status === 'loading') return <div className="inventory inv-auth-shell"><LoadingState /></div>;
  if (status !== 'authenticated') {
    const returnTo = inventoryReturnTo(location.pathname + location.search + location.hash);
    return <Navigate replace to={`/inventory/login?returnTo=${encodeURIComponent(returnTo)}`} />;
  }
  return <Outlet />;
}
export function RequireInventoryCapability({ capability, anyOf, children }: { capability?: InventoryCapability; anyOf?: InventoryCapability[]; children: ReactNode }) {
  const { can, deniedPath } = useInventoryAuth();
  const location = useLocation();
  if (!can('enterInventory') || (capability && !can(capability)) || (anyOf && !anyOf.some(can)) || deniedPath === location.pathname + location.search) return <InventoryForbidden />;
  return <>{children}</>;
}
