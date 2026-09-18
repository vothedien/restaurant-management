import { useState, type FormEvent } from 'react';
import axios from 'axios';
import { Link, Navigate, useSearchParams } from 'react-router-dom';
import { Field, LoadingState } from '../components/ui';
import { inventoryReturnTo } from './returnTo';
import { useInventoryAuth } from './useInventoryAuth';

export function InventoryLoginPage() {
  const auth = useInventoryAuth();
  const [params] = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const returnTo = inventoryReturnTo(params.get('returnTo'));
  if (auth.status === 'authenticated') return <Navigate replace to={returnTo} />;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || auth.unavailable || auth.status === 'loading') return;
    if (!username.trim() || !password) { setError('Nhập tên đăng nhập và mật khẩu.'); return; }
    setPending(true); setError('');
    try { await auth.signIn({ username: username.trim(), password }); setPassword(''); }
    catch (caught) {
      const status = axios.isAxiosError(caught) ? caught.response?.status : undefined;
      setPassword('');
      setError(status === 401 ? 'Tên đăng nhập hoặc mật khẩu không đúng.' : status === 403 ? 'Tài khoản chưa được phép đăng nhập. Liên hệ quản trị hệ thống.' : 'Chưa thể đăng nhập. Vui lòng kiểm tra kết nối và thử lại.');
    } finally { setPending(false); }
  }
  return <div className="inventory inv-auth-shell" lang="vi"><main className="inv-login-card"><Link className="inv-auth-brand" to="/inventory">Kho nhà hàng</Link><h1>Đăng nhập Kho hàng</h1><p className="inv-muted">Đăng nhập bằng tài khoản nhà hàng được cấp quyền Kho.</p>{auth.status === 'loading' ? <LoadingState /> : <>{auth.message && <div className={auth.unavailable ? 'inv-note' : 'inv-error'} role={auth.unavailable ? 'status' : 'alert'}><p>{auth.message}</p><button className="inv-button secondary" type="button" onClick={auth.retry}>Kiểm tra lại kết nối</button></div>}<form onSubmit={submit} aria-busy={pending}><Field label="Tên đăng nhập"><input autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} required disabled={pending || auth.unavailable} maxLength={50} /></Field><Field label="Mật khẩu"><input type="password" autoComplete="current-password" value={password} onChange={event => setPassword(event.target.value)} required disabled={pending || auth.unavailable} /></Field>{error && <div className="inv-error" role="alert">{error}</div>}<button className="inv-button" type="submit" disabled={pending || auth.unavailable}>{pending ? 'Đang đăng nhập…' : 'Đăng nhập'}</button></form></>}</main></div>;
}
