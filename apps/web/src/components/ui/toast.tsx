"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { X, CheckCircle2, AlertTriangle, Info } from "lucide-react";
import type { ToastItem } from "./use-toast";

interface ToastProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
}

export function Toast({ toast, onDismiss }: ToastProps) {
  const isDestructive = toast.variant === "destructive";
  const isSuccess = toast.variant === "success";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 16, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.95 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      role={isDestructive ? "alert" : "status"}
      aria-live="polite"
      className={`pointer-events-auto relative flex w-full max-w-sm items-start gap-3 rounded-lg border p-4 shadow-lg backdrop-blur-md transition-all ${
        isDestructive
          ? "border-destructive/40 bg-destructive/90 text-destructive-foreground"
          : isSuccess
          ? "border-emerald-500/30 bg-emerald-950/90 text-emerald-100"
          : "border-border/80 bg-card/95 text-foreground"
      }`}
    >
      <div className="shrink-0 mt-0.5">
        {isSuccess ? (
          <CheckCircle2 className="h-4 w-4 text-emerald-400" aria-hidden="true" />
        ) : isDestructive ? (
          <AlertTriangle className="h-4 w-4 text-destructive-foreground" aria-hidden="true" />
        ) : (
          <Info className="h-4 w-4 text-primary" aria-hidden="true" />
        )}
      </div>

      <div className="flex-1 space-y-1 pr-2">
        {toast.title && (
          <p className="text-xs font-semibold tracking-tight">{toast.title}</p>
        )}
        {toast.description && (
          <p className="text-xs text-muted-foreground leading-relaxed">
            {toast.description}
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Cerrar notificación"
        className="rounded-md p-1 opacity-70 hover:opacity-100 transition-opacity focus-visible:ring-2 focus-visible:ring-primary shrink-0"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </motion.div>
  );
}
