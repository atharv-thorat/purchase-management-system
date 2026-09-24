"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";
import { useToast } from "@/components/ui/Toast";

export interface Loaded<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (data: T) => void;
}

/** Load data for a page. Errors are kept for the page's error state and also toasted. */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const toast = useToast();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetcherRef.current());
      setError(null);
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "UNKNOWN", String(e));
      setError(err);
      if (err.status !== 401) toast.error(err.message);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload, setData };
}

/** Run a user action (button, form): tracks busy state, toasts the API's message on failure. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(key: string, action: () => Promise<T>, success?: string | ((result: T) => string)): Promise<T | undefined> => {
      setBusy(key);
      try {
        const result = await action();
        if (success) toast.success(typeof success === "function" ? success(result) : success);
        return result;
      } catch (e) {
        toast.error(e instanceof ApiError ? e.message : String(e));
        return undefined;
      } finally {
        setBusy(null);
      }
    },
    [toast],
  );

  return { run, busy };
}
