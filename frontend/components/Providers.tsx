"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import { API_URL } from "@/lib/api";
import { useAuth } from "@/lib/store";

function WakeGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const started = Date.now();
    let delay = 500;
    async function poll() {
      try {
        const response = await fetch(`${API_URL}/health/ready`);
        if (response.ok) {
          if (!cancelled) setReady(true);
          return;
        }
      } catch {
        setSeconds((value) => value);
      }
      if (cancelled) return;
      setSeconds(Math.round((Date.now() - started) / 1000));
      if (Date.now() - started > 90000) {
        setReady(true);
        return;
      }
      delay = Math.min(delay * 1.5, 5000);
      setTimeout(poll, delay);
    }
    poll();
    return () => {
      cancelled = true;
    };
  }, []);
  if (ready) return <>{children}</>;
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-line border-t-primary" aria-hidden />
      <p className="text-lg font-semibold">Waking up the planner…</p>
      <p className="max-w-sm text-sm text-muted">The free-tier backend sleeps when idle and needs up to a minute to start. {seconds > 0 && `Waiting ${seconds}s.`}</p>
    </div>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 15000, retry: 1, refetchOnWindowFocus: false } } }));
  const hydrate = useAuth((state) => state.hydrate);
  useEffect(() => {
    hydrate();
  }, [hydrate]);
  return (
    <QueryClientProvider client={client}>
      <WakeGate>{children}</WakeGate>
    </QueryClientProvider>
  );
}
