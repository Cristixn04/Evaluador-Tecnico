"use client";

import { useEffect, useState } from "react";

export function MswProvider({ children }: { children: React.ReactNode }) {
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    async function initMsw() {
      // Solo habilitar en el cliente
      if (typeof window !== "undefined") {
        // Por defecto habilitado a menos que NEXT_PUBLIC_ENABLE_MOCKS sea 'false'
        const enabled = process.env.NEXT_PUBLIC_ENABLE_MOCKS !== "false";
        if (enabled) {
          const { worker } = await import("@/mocks/browser");
          await worker.start({
            serviceWorker: {
              url: "/mockServiceWorker.js",
            },
          });
        }
      }
      setIsReady(true);
    }

    initMsw();
  }, []);

  if (!isReady) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background text-muted-foreground font-mono text-sm">
        <div className="flex items-center gap-3">
          <div className="h-4 w-4 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          <span>Iniciando entorno local...</span>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
