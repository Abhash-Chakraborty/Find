"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { Toaster } from "sonner";
import { vaultStore } from "@/store/vaultStore";

interface ProvidersProps {
  children: ReactNode;
}

export function Providers({ children }: ProvidersProps) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            refetchOnWindowFocus: false,
            retry: 1,
          },
          mutations: {
            retry: 1,
          },
        },
      }),
  );

  useEffect(() => {
    const lockFn = () => {
      vaultStore.getState().lock();
    };

    const handleVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        lockFn();
      }
    };

    window.addEventListener("beforeunload", lockFn);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.removeEventListener("beforeunload", lockFn);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <Toaster position="top-right" richColors theme="system" />
    </QueryClientProvider>
  );
}
