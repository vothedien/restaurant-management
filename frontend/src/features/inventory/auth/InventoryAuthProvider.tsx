import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import axios from 'axios';
import { backendAuthAdapter } from './backendAdapter';
import { InventoryAuthContext, type InventoryAuthContextValue } from './context';
import { hasCapability } from './permissions';
import { onInventoryAuthorizationFailure, setInventoryCredential, setInventoryRequestLocation } from './transport';
import { AuthUnavailableError, validateSession, type InventoryAuthAdapter, type InventoryCredentials, type InventoryUser } from './types';

interface State { status: 'loading' | 'anonymous' | 'authenticated'; user: InventoryUser | null; unavailable: boolean; message?: string }
export function InventoryAuthProvider({ children, adapter = backendAuthAdapter }: { children: ReactNode; adapter?: InventoryAuthAdapter }) {
  const [state, setState] = useState<State>({ status: 'loading', user: null, unavailable: false });
  const [deniedPath, setDeniedPath] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const pending = useRef(false);
  const signInController = useRef<AbortController | null>(null);
  const location = useLocation();
  const locationRef = useRef(location.pathname + location.search);
  useLayoutEffect(() => {
    locationRef.current = location.pathname + location.search;
    setInventoryRequestLocation(locationRef.current);
    return () => setInventoryRequestLocation(null);
  }, [location]);
  const clearSession = useCallback((message?: string) => {
    generation.current += 1;
    signInController.current?.abort();
    signInController.current = null;
    pending.current = false;
    setInventoryCredential(null);
    setDeniedPath(null);
    setState({ status: 'anonymous', user: null, unavailable: false, message });
    void adapter.signOut().catch(() => { /* Local session is already cleared. */ });
  }, [adapter]);
  useEffect(() => onInventoryAuthorizationFailure((status, requestPath) => {
    if (status === 401) clearSession('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.');
    else if (requestPath === locationRef.current) setDeniedPath(requestPath);
  }), [clearSession]);
  useEffect(() => {
    const controller = new AbortController();
    const attempt = ++generation.current;
    void adapter.restoreSession(controller.signal).then(session => {
      if (controller.signal.aborted || attempt !== generation.current) return;
      if (!session) { setInventoryCredential(null); setState({ status: 'anonymous', user: null, unavailable: false }); return; }
      const verified = validateSession(session);
      setInventoryCredential(verified.accessToken);
      setState({ status: 'authenticated', user: verified.user, unavailable: false });
    }).catch((error: unknown) => {
      if (controller.signal.aborted || attempt !== generation.current) return;
      setInventoryCredential(null);
      const unavailable = error instanceof AuthUnavailableError;
      const expired = axios.isAxiosError(error) && error.response?.status === 401;
      if (expired) void adapter.signOut().catch(() => {});
      setState({ status: 'anonymous', user: null, unavailable, message: unavailable ? error.message : expired ? 'Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.' : 'Không thể kiểm tra phiên đăng nhập. Vui lòng thử lại.' });
    });
    return () => { generation.current += 1; controller.abort(); signInController.current?.abort(); signInController.current = null; pending.current = false; setInventoryCredential(null); };
  }, [adapter, revision]);
  const signIn = useCallback(async (credentials: InventoryCredentials) => {
    if (pending.current) return;
    pending.current = true;
    const attempt = ++generation.current;
    const controller = new AbortController();
    signInController.current = controller;
    try {
      const session = validateSession(await adapter.signIn(credentials, controller.signal));
      if (attempt !== generation.current) return;
      setInventoryCredential(session.accessToken);
      setDeniedPath(null);
      setState({ status: 'authenticated', user: session.user, unavailable: false });
    } finally { if (signInController.current === controller) { pending.current = false; signInController.current = null; } }
  }, [adapter]);
  const signOut = useCallback(async () => { clearSession(); }, [clearSession]);
  const retry = useCallback(() => { setState({ status: 'loading', user: null, unavailable: false }); setRevision(value => value + 1); }, []);
  const clearDenied = useCallback(() => setDeniedPath(null), []);
  const value = useMemo<InventoryAuthContextValue>(() => ({ ...state, deniedPath, can: capability => hasCapability(state.user, capability), signIn, signOut, retry, clearDenied }), [state, deniedPath, signIn, signOut, retry, clearDenied]);
  return <InventoryAuthContext.Provider value={value}>{children}</InventoryAuthContext.Provider>;
}
