"use client";

import { useState } from "react";
import type { ServerCodeExecutionResultMessage } from "@evaluador/contracts";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle, Terminal, Check, AlertTriangle, Clock } from "lucide-react";

interface TestConsoleProps {
  result: ServerCodeExecutionResultMessage | null;
  isRunning: boolean;
}

export function TestConsole({ result, isRunning }: TestConsoleProps) {
  const [activeTab, setActiveTab] = useState<"tests" | "output">("tests");

  return (
    <div className="h-full flex flex-col bg-[#181818] border-t border-[#333333] text-neutral-200 text-xs">
      {/* Console Top Header */}
      <div className="h-9 px-4 bg-[#202020] border-b border-[#303030] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setActiveTab("tests")}
            className={`px-2 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
              activeTab === "tests"
                ? "bg-[#2d2d2d] text-white font-medium"
                : "text-neutral-400 hover:text-white"
            }`}
          >
            <span>Resultados de Tests</span>
            {result && (
              <Badge
                variant={result.status === "success" ? "secondary" : "destructive"}
                className="text-[10px] h-4 px-1"
              >
                {result.tests_passed}/{result.total_tests}
              </Badge>
            )}
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("output")}
            className={`px-2 py-1 rounded text-xs transition-colors flex items-center gap-1.5 ${
              activeTab === "output"
                ? "bg-[#2d2d2d] text-white font-medium"
                : "text-neutral-400 hover:text-white"
            }`}
          >
            <Terminal className="h-3 w-3" />
            <span>Terminal Salida</span>
          </button>
        </div>

        {/* Execution Time */}
        {result && (
          <div className="flex items-center gap-1 text-[11px] text-neutral-400 font-mono">
            <Clock className="h-3 w-3" />
            <span>{result.execution_time_ms} ms</span>
          </div>
        )}
      </div>

      {/* Console Body */}
      <div className="flex-1 overflow-y-auto p-4">
        {isRunning ? (
          <div className="h-full flex items-center justify-center text-neutral-400 space-x-2 animate-pulse">
            <div className="h-2 w-2 rounded-full bg-emerald-500 animate-ping" />
            <span>Ejecutando suite de pruebas en el sandbox aislado...</span>
          </div>
        ) : !result ? (
          <div className="h-full flex flex-col items-center justify-center text-neutral-500 space-y-1.5">
            <Terminal className="h-6 w-6 opacity-40" />
            <p className="text-xs">
              Presiona <strong className="text-neutral-400">Ejecutar Pruebas</strong> o{" "}
              <kbd className="px-1.5 py-0.5 rounded bg-neutral-800 text-neutral-300 font-mono text-[10px]">
                Ctrl + Enter
              </kbd>{" "}
              para validar tu código.
            </p>
          </div>
        ) : activeTab === "tests" ? (
          <div className="space-y-3">
            {/* Status Summary Banner */}
            <div
              className={`p-2.5 rounded-lg border flex items-center gap-2 text-xs font-medium ${
                result.status === "success"
                  ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                  : "bg-red-950/40 border-red-800/60 text-red-300"
              }`}
            >
              {result.status === "success" ? (
                <>
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  <span>
                    ¡Excelente trabajo! Has superado todos los casos de prueba ({result.tests_passed}/{result.total_tests}).
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle className="h-4 w-4 text-red-400 shrink-0" />
                  <span>
                    Algunos casos de prueba fallaron ({result.tests_passed}/{result.total_tests}). Revisa tu lógica de depuración.
                  </span>
                </>
              )}
            </div>

            {/* Test Details List */}
            <div className="space-y-2">
              {result.test_details?.map((test, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded bg-[#1f1f1f] border border-[#2d2d2d] flex items-start justify-between gap-2"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {test.passed ? (
                        <Check className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
                      ) : (
                        <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />
                      )}
                      <span className="font-mono text-xs text-neutral-200">
                        {test.test_name}
                      </span>
                    </div>
                    {test.message && (
                      <p className="text-[11px] text-red-400 font-mono pl-5">
                        {test.message}
                      </p>
                    )}
                  </div>

                  <Badge
                    variant={test.passed ? "secondary" : "destructive"}
                    className="text-[10px] font-mono capitalize"
                  >
                    {test.passed ? "Aprobado" : "Falló"}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        ) : (
          /* Terminal Stdout / Stderr */
          <div className="font-mono text-xs space-y-2">
            {result.stdout && (
              <pre className="whitespace-pre-wrap text-neutral-300 bg-black/40 p-3 rounded border border-neutral-800">
                {result.stdout}
              </pre>
            )}
            {result.stderr && (
              <pre className="whitespace-pre-wrap text-red-400 bg-red-950/20 p-3 rounded border border-red-900/50">
                {result.stderr}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
