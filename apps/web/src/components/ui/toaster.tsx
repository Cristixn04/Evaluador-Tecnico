"use client";

import * as React from "react";
import { AnimatePresence } from "framer-motion";
import { useToast } from "./use-toast";
import { Toast } from "./toast";

export function Toaster() {
  const { toasts, dismiss } = useToast();

  return (
    <div
      role="region"
      aria-label="Notificaciones del sistema"
      className="fixed bottom-4 right-4 z-50 flex max-h-screen w-full max-w-sm flex-col gap-2 pointer-events-none p-4 md:bottom-6 md:right-6"
    >
      <AnimatePresence mode="popLayout">
        {toasts.map((item) => (
          <Toast key={item.id} toast={item} onDismiss={dismiss} />
        ))}
      </AnimatePresence>
    </div>
  );
}
