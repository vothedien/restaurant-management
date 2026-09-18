import { useCallback, useRef, useState } from "react";
import { INVENTORY_REFRESH } from "./useQuery";

export function useMutation() {
  const busy = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error>();
  const clearError = useCallback(() => setError(undefined), []);
  const run = useCallback(async <T,>(fn: () => Promise<T>, onSuccess?: (data: T) => void): Promise<T | undefined> => {
    if (busy.current) return undefined;
    busy.current = true;
    setPending(true);
    setError(undefined);
    try {
      const data = await fn();
      window.dispatchEvent(new Event(INVENTORY_REFRESH));
      onSuccess?.(data);
      return data;
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('Không thể thực hiện thao tác.'));
      return undefined;
    } finally { busy.current = false; setPending(false); }
  }, []);
  return { run, pending, error, clearError };
}
