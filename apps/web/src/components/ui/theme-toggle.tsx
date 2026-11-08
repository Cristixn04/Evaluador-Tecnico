"use client";

import * as React from "react";
import { Sun, Moon } from "lucide-react";
import { useTheme } from "@/components/providers/theme-provider";
import { Button } from "@/components/ui/button";

export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, toggleTheme } = useTheme();

  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      onClick={toggleTheme}
      aria-label={
        resolvedTheme === "dark"
          ? "Cambiar a modo claro"
          : "Cambiar a modo oscuro"
      }
      title={
        resolvedTheme === "dark"
          ? "Cambiar a modo claro"
          : "Cambiar a modo oscuro"
      }
      className={`h-8 w-8 px-0 text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-primary ${
        className || ""
      }`}
    >
      {resolvedTheme === "dark" ? (
        <Sun className="h-4 w-4 transition-transform rotate-0 scale-100 text-amber-400" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4 transition-transform rotate-0 scale-100 text-slate-700" aria-hidden="true" />
      )}
      <span className="sr-only">Alternar tema</span>
    </Button>
  );
}
