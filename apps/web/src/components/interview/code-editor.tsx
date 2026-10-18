"use client";

import { useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { CodeLanguage } from "@evaluador/contracts";
import { Play, Check, RotateCcw, Loader2 } from "lucide-react";

// Import dinámico de Monaco para evitar problemas con Server-Side Rendering (SSR)
const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface CodeEditorProps {
  code: string;
  language: CodeLanguage;
  onChangeCode: (code: string) => void;
  onLanguageChange: (lang: CodeLanguage) => void;
  onRunTests: () => void;
  isRunningTests: boolean;
  saveStatus?: "saved" | "saving";
}

const DEFAULT_STARTER_CODES: Record<CodeLanguage, string> = {
  python: `def reconcile_transactions(internal_ledger: list[dict], bank_statement: list[dict]) -> dict:
    """
    Concilia transacciones internas contra extracto bancario ACH/PSE.
    
    Retorna un diccionario con:
      - 'matched': int (número de transacciones perfectamente cuadradas)
      - 'discrepancies': int (mismo ID pero montos con diferencia)
      - 'orphans': int (transacciones que no cruzaron)
    """
    matched = 0
    discrepancies = 0
    orphans = 0
    
    # Escribe aquí tu solución...
    
    return {
        "matched": matched,
        "discrepancies": discrepancies,
        "orphans": orphans
    }
`,
  javascript: `/**
 * Concilia transacciones internas contra extracto bancario ACH/PSE.
 * @param {Array<Object>} internalLedger
 * @param {Array<Object>} bankStatement
 * @returns {Object} { matched, discrepancies, orphans }
 */
function reconcileTransactions(internalLedger, bankStatement) {
  let matched = 0;
  let discrepancies = 0;
  let orphans = 0;

  // Escribe aquí tu solución...

  return { matched, discrepancies, orphans };
}
`,
  sql: `-- Consulta de conciliación de lotes PSE
SELECT 
    t.id AS transaction_id,
    t.amount AS internal_amount,
    b.amount AS bank_amount,
    CASE 
        WHEN b.id IS NULL THEN 'ORPHAN'
        WHEN t.amount != b.amount THEN 'DISCREPANCY'
        ELSE 'MATCHED'
    END AS status
FROM internal_transactions t
LEFT JOIN bank_statement b ON t.id = b.id;
`,
};

export function CodeEditor({
  code,
  language,
  onChangeCode,
  onLanguageChange,
  onRunTests,
  isRunningTests,
  saveStatus = "saved",
}: CodeEditorProps) {
  const monacoRef = useRef<any>(null);

  // Inicializar starter code si está vacío
  useEffect(() => {
    if (!code) {
      onChangeCode(DEFAULT_STARTER_CODES[language] || "");
    }
  }, [language, code, onChangeCode]);

  const handleEditorMount = (editor: any, monaco: any) => {
    monacoRef.current = editor;

    // Atajo de teclado: Ctrl+Enter o Cmd+Enter para ejecutar tests
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      onRunTests();
    });
  };

  const handleReset = () => {
    onChangeCode(DEFAULT_STARTER_CODES[language] || "");
  };

  return (
    <div className="flex flex-col h-full bg-[#1e1e1e] text-white">
      {/* Editor Control Bar */}
      <div className="h-10 px-4 bg-[#252526] border-b border-[#333333] flex items-center justify-between shrink-0 text-xs">
        {/* Left: Language Tabs */}
        <div className="flex items-center gap-1.5">
          <span className="text-neutral-400 text-[11px] mr-1 hidden sm:inline">Lenguaje:</span>
          {(["python", "javascript", "sql"] as const).map((lang) => (
            <button
              key={lang}
              type="button"
              onClick={() => {
                onLanguageChange(lang);
                onChangeCode(DEFAULT_STARTER_CODES[lang] || "");
              }}
              className={`px-2 py-0.5 rounded text-[11px] font-mono transition-colors ${
                language === lang
                  ? "bg-primary text-primary-foreground font-semibold"
                  : "text-neutral-400 hover:text-white hover:bg-neutral-800"
              }`}
            >
              {lang}
            </button>
          ))}
        </div>

        {/* Right: Autosave Status & Actions */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 text-[11px] text-neutral-400 font-mono">
            {saveStatus === "saving" ? (
              <>
                <Loader2 className="h-3 w-3 animate-spin text-yellow-400" />
                <span className="text-yellow-400 hidden sm:inline">Guardando...</span>
              </>
            ) : (
              <>
                <Check className="h-3 w-3 text-emerald-400" />
                <span className="text-neutral-400 hidden sm:inline">Autosave activo</span>
              </>
            )}
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleReset}
            className="h-7 px-2 text-[11px] text-neutral-400 hover:text-white hover:bg-neutral-800"
            title="Restablecer plantilla inicial"
          >
            <RotateCcw className="h-3 w-3" />
          </Button>

          <Button
            size="sm"
            onClick={onRunTests}
            disabled={isRunningTests}
            className="h-7 text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium shadow-sm"
          >
            {isRunningTests ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Ejecutando...</span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 fill-current" />
                <span>Ejecutar Pruebas</span>
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Editor Main Canvas */}
      <div className="flex-1 min-h-[300px]">
        <Editor
          height="100%"
          language={language === "sql" ? "sql" : language === "javascript" ? "javascript" : "python"}
          value={code}
          theme="vs-dark"
          onChange={(val) => onChangeCode(val || "")}
          onMount={handleEditorMount}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            roundedSelection: true,
            scrollBeyondLastLine: false,
            readOnly: false,
            automaticLayout: true,
            tabSize: 4,
            wordWrap: "on",
          }}
        />
      </div>
    </div>
  );
}
