import { useCallback, useEffect, useRef, useState } from "react";

export const INVENTORY_REFRESH = "inventory:refresh";
export function useQuery<T>(key: string, loader: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<{ key: string; revision: number; data?: T; error?: Error }>({ key, revision: -1 });
  const [revision, setRevision] = useState(0);
  const loaderRef = useRef(loader);
  useEffect(() => { loaderRef.current = loader; });
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  useEffect(() => {
    window.addEventListener(INVENTORY_REFRESH, refresh);
    return () => window.removeEventListener(INVENTORY_REFRESH, refresh);
  }, [refresh]);
  useEffect(() => {
    const controller = new AbortController();
    void loaderRef.current(controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ key, revision, data });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState(previous => ({ key, revision, data: previous.key === key ? previous.data : undefined, error: error instanceof Error ? error : new Error('Không thể tải dữ liệu.') }));
    });
    return () => controller.abort();
  }, [key, revision]);
  return { data: state.key === key ? state.data : undefined, error: state.key === key && state.revision === revision ? state.error : undefined, loading: state.key !== key || state.revision !== revision, refresh };
}
