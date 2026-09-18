import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useInventoryAuth } from '../auth/useInventoryAuth';
import { inventoryNavGroups, navigationCapabilities } from './navigation';
const icons: Record<string,string> = { '':'M3 11 12 3l9 8M5 10v11h5v-6h4v6h5V10',alerts:'M12 3 2 21h20L12 3Zm0 7v4m0 3v1',ingredients:'M4 7h16v14H4V7Zm-1-4h18v4H3V3Zm6 8h6',units:'M3 7h18v10H3V7Zm4 0v5m5-5v3m5-3v5',recipes:'M5 3h14v18H5V3Zm4 5h6m-6 4h6m-6 4h4',suppliers:'M3 21V8l9-5 9 5v13H3Zm5 0v-6h8v6M7 9h1m4 0h1m4 0h1','purchase-orders':'M6 3h12v18H6V3Zm3 5h6m-6 4h6m-6 4h3','goods-receipts':'M3 8h18v13H3V8Zm4-5h10l4 5M12 11v7m-3-3 3 3 3-3',stock:'M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7',lots:'M12 3 3 8v10l9 4 9-4V8l-9-5Zm-9 5 9 5 9-5m-9 5v9',movements:'M3 7h16m-4-4 4 4-4 4M21 17H5m4-4-4 4 4 4','adjustments/new':'M12 4v16M4 12h16',stocktakes:'M8 3h8v4H8V3Zm-3 2H3v17h18V5h-2M7 12l2 2 4-4m2 3h3m-11 5h11',reports:'M4 21V3m0 18h17M8 17v-5m5 5V7m5 10v-8' };
function NavIcon({name}:{name:string}) { return <svg className="inv-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={icons[name]??icons.stock}/></svg>; }
export function InventoryLayout() {
  const { user, can, signOut } = useInventoryAuth();
  const location = useLocation();
  const currentPath = location.pathname + location.search;
  const [openPath, setOpenPath] = useState<string | null>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const menuOpen = openPath === currentPath;
  const groups = inventoryNavGroups.map(group => ({ ...group, items: group.items.filter(([path]) => path === 'adjustments/new' ? can('issueStock') || can('adjustStock') : can(navigationCapabilities[path])) })).filter(group => group.items.length);
  const section = location.pathname.replace(/^\/inventory\/?/, '').split('/')[0];
  const current = groups.flatMap(group => group.items).find(([path]) => path.split('/')[0] === section);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') { setOpenPath(null); toggle.current?.focus(); } };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [menuOpen]);
  return <div className="inventory inv-workspace" lang="vi">
    <a className="inv-skip-link" href="#inventory-main">Đến nội dung chính</a>
    <header className="inv-topbar">
      <Link className="inv-brand" to="/inventory"><span className="inv-logo"><NavIcon name="lots" /></span><span>Kho nhà hàng</span></Link>
      <div className="inv-user-menu"><div><strong>{user?.displayName}</strong><span>{user?.roles.map(role => role.name || role.code).join(' · ') || 'Tài khoản hệ thống'}</span></div><button type="button" className="inv-button secondary" onClick={() => { void signOut(); }}>Đăng xuất</button></div>
      <button ref={toggle} type="button" className="inv-button secondary inv-menu-toggle" aria-expanded={menuOpen} aria-controls="inventory-navigation" onClick={() => setOpenPath(menuOpen ? null : currentPath)}>{menuOpen ? 'Đóng menu Kho' : 'Mở menu Kho'}</button>
    </header>
    <aside className="inv-sidebar" data-open={menuOpen} id="inventory-navigation"><div className="inv-sidebar-inner"><nav aria-label="Điều hướng Kho hàng">{groups.map(group => <div key={group.label}><h2>{group.label}</h2>{group.items.map(([path, label]) => <NavLink key={path} end={!path} to={`/inventory${path ? `/${path}` : ''}`} onClick={() => setOpenPath(null)}><NavIcon name={path} />{label}</NavLink>)}</div>)}</nav></div></aside>
    <main className="inv-main" id="inventory-main" tabIndex={-1}><nav className="inv-breadcrumb" aria-label="Đường dẫn"><Link to="/inventory">Kho hàng</Link>{section && <><span aria-hidden="true">/</span><span>{current?.[1] ?? 'Chi tiết'}</span></>}</nav><Outlet /></main>
  </div>;
}
