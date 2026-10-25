import { useEffect, useRef } from "react";
import type { CodeLanguage, SnapshotReason } from "@evaluador/contracts";

interface UseDebouncedSnapshotProps {
  code: string;
  language: CodeLanguage;
  enabled: boolean;
  onSnapshot: (code: string, language: CodeLanguage, reason: SnapshotReason) => void;
  debounceMs?: number;
}

export function useDebouncedSnapshot({
  code,
  language,
  enabled,
  onSnapshot,
  debounceMs = 3500,
}: UseDebouncedSnapshotProps) {
  const lastEmittedCodeRef = useRef<string>(code);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!enabled) return;

    // Si el código no ha cambiado, no programar snapshot
    if (code === lastEmittedCodeRef.current) return;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      lastEmittedCodeRef.current = code;
      onSnapshot(code, language, "debounce");
    }, debounceMs);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [code, language, enabled, onSnapshot, debounceMs]);

  // Función para forzar snapshot inmediato (al cambiar de fase o blur)
  const triggerImmediateSnapshot = (reason: SnapshotReason) => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    lastEmittedCodeRef.current = code;
    onSnapshot(code, language, reason);
  };

  // Función para sincronizar estado de código y cancelar timer pendiente sin emitir snapshot redundante
  const syncCurrentCode = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    lastEmittedCodeRef.current = code;
  };

  return { triggerImmediateSnapshot, syncCurrentCode };
}
