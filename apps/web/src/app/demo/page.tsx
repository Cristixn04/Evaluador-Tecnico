"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { CompetencyRadar } from "@/components/evaluation/competency-radar";
import dynamic from "next/dynamic";
import {
  Sparkles,
  Play,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Shield,
  RotateCcw,
  Send,
  Bot,
  User,
  Terminal,
  FileCheck,
  Award,
  ChevronRight,
  HelpCircle,
  Eye,
  Lock,
} from "lucide-react";

// Importación dinámica de Monaco Editor para soporte SSR Next.js
const MonacoEditor = dynamic(() => import("@monaco-editor/react"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-slate-950 font-mono text-xs text-slate-500">
      Cargando Monaco Editor...
    </div>
  ),
});

interface DemoProblem {
  id: string;
  title: string;
  seniority: string;
  category: string;
  timeLimit: string;
  description: string;
  constraints: string[];
  initialCode: string;
  tests: { name: string; input: string; expected: string }[];
}

const DEMO_PROBLEMS: DemoProblem[] = [
  {
    id: "pse-reconciliation",
    title: "Conciliación de Pagos PSE (Fintech Colombia)",
    seniority: "Senior",
    category: "Backend / Algorítmico",
    timeLimit: "35 mins",
    description:
      "Una pasarela de pagos colombiana recibe dos extractos diarios: uno del banco recaudador ACH/PSE y otro del ledger transaccional interno. Debes implementar la función reconcile_transactions(bank_records, internal_records) que identifique transacciones conciliadas, discrepancias de valor y transacciones pendientes en tiempo O(N log N) o O(N).",
    constraints: [
      "N <= 100,000 transacciones por extracto diario",
      "Complejidad de tiempo máxima permitida: O(N log N)",
      "Manejo de estados: APPROVED, REJECTED, PENDING",
    ],
    initialCode: `from typing import List, Dict, Any

def reconcile_transactions(
    bank_records: List[Dict[str, Any]], 
    internal_records: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Concilia extractos bancarios PSE con el ledger interno.
    
    Retorna un diccionario con:
    - 'matched': int (coincidencia exacta en id y monto)
    - 'discrepancies': List[str] (mismo id, monto diferente)
    - 'unmatched_bank': List[str] (presente en banco pero no en ledger)
    - 'unmatched_internal': List[str] (presente en ledger pero no en banco)
    """
    bank_map = {b['id']: b for b in bank_records}
    internal_map = {i['id']: i for i in internal_records}
    
    matched = 0
    discrepancies = []
    
    # Identificar coincidencias y discrepancias
    for txn_id, b_txn in bank_map.items():
        if txn_id in internal_map:
            i_txn = internal_map[txn_id]
            if b_txn['amount'] == i_txn['amount']:
                matched += 1
            else:
                discrepancies.append(txn_id)
                
    unmatched_bank = [tid for tid in bank_map if tid not in internal_map]
    unmatched_internal = [tid for tid in internal_map if tid not in bank_map]
    
    return {
        "matched": matched,
        "discrepancies": sorted(discrepancies),
        "unmatched_bank": sorted(unmatched_bank),
        "unmatched_internal": sorted(unmatched_internal)
    }
`,
    tests: [
      { name: "Conciliación transacciones idénticas", input: "10 transacciones coincidentes", expected: "matched: 10, discrepancias: 0" },
      { name: "Detección de discrepancia en montos", input: "txn_005 banco $150k vs ledger $145k", expected: "discrepancies: ['txn_005']" },
      { name: "Transacciones huérfanas en ACH", input: "txn_099 solo en banco", expected: "unmatched_bank: ['txn_099']" },
    ],
  },
  {
    id: "uvt-payroll",
    title: "Retención en la Fuente UVT (Nómina Colombia 2026)",
    seniority: "Mid / Junior",
    category: "Backend / Lógica Tributaria",
    timeLimit: "30 mins",
    description:
      "Implementa la función calculate_withholding_tax(gross_salary, dependents, prepay_health) conforme al Estatuto Tributario colombiano con UVT 2026 ($49,799 COP). Aplica deducciones de ley (dependientes máx 32 UVT, medicina prepagada máx 16 UVT) y los rangos de la tabla del Art. 383.",
    constraints: [
      "Valor UVT 2026: $49,799 COP",
      "Rango 0 a 95 UVT: Tarifa 0%",
      "Rango >95 a 150 UVT: (Ingreso Laboral Gravable en UVT - 95 UVT) * 19%",
    ],
    initialCode: `UVT_2026 = 49_799

def calculate_withholding_tax(gross_salary: float, dependents: int, prepay_health: float) -> float:
    """
    Calcula la retención en la fuente laboral para nómina colombiana.
    """
    # 1. Aportes obligatorios de salud y pensión (8%)
    mandatory_pension_health = gross_salary * 0.08
    net_base = gross_salary - mandatory_pension_health
    
    # 2. Deducciones (dependientes y prepagada con topes)
    dep_deduction = min(gross_salary * 0.10, 32 * UVT_2026) if dependents > 0 else 0
    health_deduction = min(prepay_health, 16 * UVT_2026)
    
    taxable_income = max(0.0, net_base - dep_deduction - health_deduction)
    taxable_uvt = taxable_income / UVT_2026
    
    # 3. Aplicación de tabla Art. 383
    if taxable_uvt <= 95:
        tax_uvt = 0.0
    elif taxable_uvt <= 150:
        tax_uvt = (taxable_uvt - 95) * 0.19
    else:
        tax_uvt = ((taxable_uvt - 150) * 0.28) + (10 * 0.19)
        
    return round(tax_uvt * UVT_2026, 2)
`,
    tests: [
      { name: "Salario menor al rango base (< 95 UVT)", input: "Salario $3.5M COP", expected: "Retención: $0 COP" },
      { name: "Salario medio con deducción de 1 dependiente", input: "Salario $8M COP, 1 dependiente", expected: "Retención calculada acorde a rango 19%" },
      { name: "Salario alto con medicina prepagada tope", input: "Salario $18M COP", expected: "Retención calculada acorde a rango 28%" },
    ],
  },
];

const STAGES = ["CLARIFY", "DESIGN", "CODING", "PROBE", "WRAPUP", "EVALUATE"] as const;

export default function DemoPage() {
  const [selectedProblem, setSelectedProblem] = useState<DemoProblem>(DEMO_PROBLEMS[0]);
  const [code, setCode] = useState(selectedProblem.initialCode);
  const [currentStage, setCurrentStage] = useState<(typeof STAGES)[number]>("CLARIFY");
  const [chatMessages, setChatMessages] = useState<
    { speaker: "agent" | "candidate"; content: string; time: string }[]
  >([
    {
      speaker: "agent",
      content: `¡Hola! Bienvenido a la sesión de evaluación técnica. Tenemos el problema "${DEMO_PROBLEMS[0].title}". Tómate un momento para leer los requerimientos. ¿Tienes alguna pregunta de clarificación sobre los límites de memoria, formatos de fecha o casos borde?`,
      time: "00:01",
    },
  ]);
  const [inputText, setInputText] = useState("");
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [showReport, setShowReport] = useState(false);
  const [testOutput, setTestOutput] = useState<string | null>(null);
  const [telemetryEvents, setTelemetryEvents] = useState<string[]>(["Sesión iniciada", "Editor enfocado"]);

  useEffect(() => {
    setCode(selectedProblem.initialCode);
    setChatMessages([
      {
        speaker: "agent",
        content: `¡Hola! Bienvenido al problema "${selectedProblem.title}". Tómate un momento para revisar el enunciado. ¿Tienes alguna pregunta sobre los requisitos o casos especiales antes de diseñar tu solución?`,
        time: "00:01",
      },
    ]);
    setCurrentStage("CLARIFY");
    setShowReport(false);
    setTestOutput(null);
  }, [selectedProblem]);

  const handleSendMessage = () => {
    if (!inputText.trim()) return;

    const userMsg = inputText.trim();
    const newChat = [
      ...chatMessages,
      { speaker: "candidate" as const, content: userMsg, time: "00:15" },
    ];
    setChatMessages(newChat);
    setInputText("");

    // Respuesta inteligente simulada según la fase
    setTimeout(() => {
      let reply = "";
      if (currentStage === "CLARIFY") {
        reply =
          "Excelente pregunta. Para este escenario, asume que los identificadores de transacción son UUIDs v4 únicos y que los extractos bancarios no contienen montos negativos ni duplicados malformados.";
        setCurrentStage("DESIGN");
      } else if (currentStage === "DESIGN") {
        reply =
          "Tu propuesta de utilizar tablas hash (diccionarios en Python) garantiza un tiempo de búsqueda O(1) promedio y complejidad global O(N). Me parece un enfoque sólido. Procede a la implementación en el editor.";
        setCurrentStage("CODING");
      } else if (currentStage === "CODING") {
        reply =
          "He detectado que estás estructurando la lógica de reconciliación. Recuerda ejecutar los casos de prueba para validar que no queden transacciones huérfanas sin procesar.";
      } else if (currentStage === "PROBE") {
        reply =
          "Pregunta de sondeo anti-cheat cognitivo: ¿Qué pasaría si el extracto bancario superara la memoria RAM disponible (e.g. 50 millones de registros)? ¿Cómo adaptarías tu algoritmo?";
        setCurrentStage("WRAPUP");
      } else {
        reply =
          "Tu justificación técnica es consistente con la implementación. Hemos concluido la interacción interactiva. Haz clic en 'Generar Reporte Defendible' para obtener tu evaluación con IA.";
      }

      setChatMessages((prev) => [
        ...prev,
        { speaker: "agent", content: reply, time: "00:16" },
      ]);
    }, 700);
  };

  const handleRunTests = () => {
    setTestOutput("Ejecutando suite de pruebas automatizadas...\n");
    setTelemetryEvents((prev) => [...prev, `Ejecución de pruebas disparada a las ${new Date().toLocaleTimeString()}`]);
    setTimeout(() => {
      setTestOutput(
        `✓ [TEST 1/3]: ${selectedProblem.tests[0].name} (PASÓ - 12ms)\n` +
          `✓ [TEST 2/3]: ${selectedProblem.tests[1].name} (PASÓ - 8ms)\n` +
          `✓ [TEST 3/3]: ${selectedProblem.tests[2].name} (PASÓ - 14ms)\n\n` +
          `Resumen: 3/3 pruebas superadas exitosamente (100% de cobertura). Sandbox aislado Judge0 CE.`
      );
      if (currentStage === "CODING") {
        setCurrentStage("PROBE");
        setChatMessages((prev) => [
          ...prev,
          {
            speaker: "agent",
            content:
              "¡Muy bien! Todas las pruebas unitarias pasaron. Ahora te haré una pregunta técnica de verificación cognitiva: ¿Cuál es la complejidad temporal y espacial de tu solución y cómo se comportaría ante un pico de concurrencia?",
            time: "00:20",
          },
        ]);
      }
    }, 800);
  };

  const handleFinishAndEvaluate = () => {
    setIsEvaluating(true);
    setTimeout(() => {
      setIsEvaluating(false);
      setShowReport(true);
    }, 1200);
  };

  return (
    <div className="flex flex-col min-h-screen bg-slate-950 text-slate-100">
      {/* Header Demo */}
      <header className="border-b border-slate-800 bg-slate-900/90 backdrop-blur px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary/20 border border-primary/40 flex items-center justify-center font-bold text-primary">
              ET
            </div>
            <span className="font-bold text-sm tracking-tight text-white">
              Evaluador Técnico <span className="text-cyan-400 font-mono text-xs ml-1">Modo Demo Offline</span>
            </span>
          </Link>
          <div className="hidden md:flex items-center gap-2">
            <span className="text-xs text-slate-400">Problema:</span>
            <select
              value={selectedProblem.id}
              onChange={(e) => {
                const found = DEMO_PROBLEMS.find((p) => p.id === e.target.value);
                if (found) setSelectedProblem(found);
              }}
              className="bg-slate-800 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
            >
              {DEMO_PROBLEMS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title} ({p.seniority})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Phase Stepper */}
        <div className="hidden lg:flex items-center gap-1.5 bg-slate-950/80 border border-slate-800 rounded-full px-3 py-1">
          {STAGES.map((s, idx) => {
            const isActive = currentStage === s;
            const isDone = STAGES.indexOf(currentStage) > idx;
            return (
              <div key={s} className="flex items-center gap-1">
                <span
                  className={`text-[10px] font-mono px-2 py-0.5 rounded-full transition-colors ${
                    isActive
                      ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40"
                      : isDone
                      ? "text-slate-400 bg-slate-900"
                      : "text-slate-600"
                  }`}
                >
                  {s}
                </span>
                {idx < STAGES.length - 1 && <span className="text-slate-700 text-xs">›</span>}
              </div>
            );
          })}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          <Badge variant="outline" className="text-[11px] border-emerald-500/30 text-emerald-400 gap-1 hidden sm:flex">
            <Shield className="h-3 w-3" /> Ley 1581 Habeas Data
          </Badge>
          {!showReport ? (
            <Button
              size="sm"
              onClick={handleFinishAndEvaluate}
              disabled={isEvaluating}
              className="bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white text-xs gap-1.5 font-medium shadow-md shadow-cyan-950"
            >
              <Award className="h-3.5 w-3.5" />
              {isEvaluating ? "Evaluando con Rúbrica..." : "Generar Reporte Defendible"}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowReport(false)}
              className="text-xs border-slate-700 gap-1"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Volver al Entorno de Código
            </Button>
          )}
        </div>
      </header>

      {/* Main Workspace */}
      {!showReport ? (
        <div className="flex-1 grid grid-cols-1 lg:grid-cols-12 overflow-hidden min-h-[calc(100vh-65px)]">
          {/* Left Column: Problem & Conversational Agent (5 Cols) */}
          <div className="lg:col-span-5 border-r border-slate-800 flex flex-col bg-slate-900/40">
            {/* Problem Statement Card */}
            <div className="p-4 border-b border-slate-800/80 max-h-[42%] overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-cyan-400">
                  {selectedProblem.category}
                </span>
                <Badge variant="secondary" className="text-[10px]">
                  Nivel: {selectedProblem.seniority}
                </Badge>
              </div>
              <h2 className="text-base font-bold text-slate-100 mb-2">{selectedProblem.title}</h2>
              <p className="text-xs text-slate-300 leading-relaxed mb-3">
                {selectedProblem.description}
              </p>
              <div className="space-y-1 bg-slate-950/70 p-2.5 rounded border border-slate-800/80">
                <span className="text-[11px] font-semibold text-slate-400 block mb-1">Restricciones:</span>
                {selectedProblem.constraints.map((c, i) => (
                  <div key={i} className="text-[11px] text-slate-400 flex items-center gap-1.5">
                    <span className="h-1 w-1 rounded-full bg-cyan-400" />
                    <span>{c}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Simulated AI Agent Chat */}
            <div className="flex-1 flex flex-col min-h-0 bg-slate-950/40">
              <div className="px-4 py-2 bg-slate-900/60 border-b border-slate-800/60 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot className="h-4 w-4 text-cyan-400" />
                  <span className="text-xs font-semibold text-slate-200">
                    Entrevistador IA (Agente Socrático)
                  </span>
                </div>
                <span className="text-[10px] font-mono text-emerald-400 flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" /> Activo
                </span>
              </div>

              {/* Chat Messages */}
              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {chatMessages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex gap-2.5 text-xs ${
                      msg.speaker === "candidate" ? "justify-end" : "justify-start"
                    }`}
                  >
                    {msg.speaker === "agent" && (
                      <div className="h-6 w-6 rounded-full bg-cyan-950 border border-cyan-700/60 flex items-center justify-center shrink-0">
                        <Bot className="h-3 w-3 text-cyan-400" />
                      </div>
                    )}
                    <div
                      className={`rounded-lg px-3 py-2 max-w-[85%] leading-relaxed ${
                        msg.speaker === "candidate"
                          ? "bg-blue-600 text-white"
                          : "bg-slate-800/90 text-slate-200 border border-slate-700/60"
                      }`}
                    >
                      {msg.content}
                    </div>
                    {msg.speaker === "candidate" && (
                      <div className="h-6 w-6 rounded-full bg-blue-950 border border-blue-700/60 flex items-center justify-center shrink-0">
                        <User className="h-3 w-3 text-blue-400" />
                      </div>
                    )}
                  </div>
                ))}
              </div>

              {/* Chat Input */}
              <div className="p-3 border-t border-slate-800/80 bg-slate-900/70 flex gap-2">
                <input
                  type="text"
                  placeholder="Pregúntale al agente o explica tu enfoque..."
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                  className="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                />
                <Button size="sm" onClick={handleSendMessage} className="bg-cyan-600 hover:bg-cyan-500 px-3">
                  <Send className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          </div>

          {/* Right Column: Code Editor & Test Runner (7 Cols) */}
          <div className="lg:col-span-7 flex flex-col bg-slate-950">
            {/* Editor Top Bar */}
            <div className="px-4 py-2 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-xs font-mono text-slate-300 flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-cyan-400" /> solution.py
                </span>
                <span className="text-[11px] text-slate-500 font-mono">Python 3.12</span>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={handleRunTests}
                  className="bg-emerald-600 hover:bg-emerald-500 text-white text-xs h-7 px-3 gap-1.5"
                >
                  <Play className="h-3 w-3" /> Ejecutar Pruebas
                </Button>
              </div>
            </div>

            {/* Monaco Editor Container */}
            <div className="flex-1 min-h-[380px] relative">
              <MonacoEditor
                height="100%"
                language="python"
                theme="vs-dark"
                value={code}
                onChange={(newVal) => setCode(newVal || "")}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  tabSize: 4,
                  automaticLayout: true,
                }}
              />
            </div>

            {/* Test Console & Telemetry Monitor */}
            <div className="h-48 border-t border-slate-800 bg-slate-950 flex flex-col">
              <div className="px-4 py-1.5 bg-slate-900/70 border-b border-slate-800 flex items-center justify-between">
                <span className="text-xs font-mono text-slate-400 flex items-center gap-1.5">
                  <Terminal className="h-3.5 w-3.5 text-cyan-400" /> Consola de Ejecución & Telemetría Ética
                </span>
                <span className="text-[10px] font-mono text-slate-500">
                  Anti-Cheat Telemetry: Sin cámaras invasivas
                </span>
              </div>
              <div className="p-3 flex-1 font-mono text-xs text-slate-300 overflow-y-auto bg-slate-950/90 whitespace-pre-wrap">
                {testOutput || (
                  <span className="text-slate-600">
                    Haz clic en "Ejecutar Pruebas" para compilar y validar tu solución contra los casos de prueba unitarios.
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Instant Defensible Evaluation Report View */
        <div className="flex-1 max-w-6xl mx-auto w-full p-6 space-y-6">
          {/* Report Top Hero */}
          <div className="bg-gradient-to-r from-slate-900 to-slate-850 border border-slate-800 rounded-xl p-6 shadow-xl relative overflow-hidden">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 mb-2">
                  <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/40 px-2.5 py-0.5 text-xs font-mono">
                    DICTAMEN: HIRE (RECOMENDADO)
                  </Badge>
                  <span className="text-xs font-mono text-slate-400">
                    ID Candidato: <strong className="text-slate-200">CAND-DEMO-7F2A</strong> (Anonimizado)
                  </span>
                </div>
                <h1 className="text-2xl font-bold text-white tracking-tight">
                  Informe Defendible de Evaluación Técnica con IA
                </h1>
                <p className="text-xs text-slate-400 mt-1">
                  Vacante: {selectedProblem.title} • Evaluación ciega a sesgos demográficos
                </p>
              </div>

              {/* Overall Score Badge */}
              <div className="bg-slate-950/80 border border-slate-700 rounded-xl px-5 py-3 text-center">
                <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                  Puntaje Global Rúbrica
                </span>
                <span className="text-3xl font-extrabold text-cyan-400 font-mono">4.7</span>
                <span className="text-xs text-slate-400 ml-1">/ 5.0</span>
              </div>
            </div>
          </div>

          {/* Grid: Competency Radar & Forensic Evidence */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Radar Card (5 Cols) */}
            <div className="lg:col-span-5 bg-slate-900/60 border border-slate-800 rounded-xl p-5 flex flex-col justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-100 mb-1">Radar de 5 Dimensiones</h3>
                <p className="text-xs text-slate-400 mb-4">
                  Distribución armonizada de competencias técnicas evaluadas objetivamente:
                </p>
                <div className="w-full flex items-center justify-center">
                  <CompetencyRadar
                    competencies={{
                      "Resolución de Problemas": 4.8,
                      "Razonamiento Algorítmico": 4.6,
                      "Calidad de Código": 5.0,
                      "Comunicación Técnica": 4.7,
                      "Gestión de Complejidad": 4.5,
                    }}
                  />
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-mono">
                <span>Auditoría SHA-256:</span>
                <span className="text-cyan-400 truncate max-w-[200px]">
                  e9b7f32a8190c4de198c3...
                </span>
              </div>
            </div>

            {/* Forensic Evidence & Justification (7 Cols) */}
            <div className="lg:col-span-7 bg-slate-900/60 border border-slate-800 rounded-xl p-5 space-y-4">
              <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                <FileCheck className="h-4 w-4 text-cyan-400" /> Evidencias Forenses Verificables
              </h3>
              <p className="text-xs text-slate-400">
                Cada calificación está respaldada por citas directas del turno conversacional y snapshots de código:
              </p>

              <div className="space-y-3">
                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-cyan-300">Razonamiento Algorítmico (4.6 / 5.0)</span>
                    <Badge variant="outline" className="text-[10px] text-slate-400">Turno 4 • Fase DESIGN</Badge>
                  </div>
                  <p className="text-slate-300 italic border-l-2 border-cyan-500 pl-2">
                    "Optó por lookup tables en O(1) evitando un bucle anidado O(N²), reconociendo el cuello de botella con 100,000 transacciones."
                  </p>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-emerald-300">Calidad de Código y Tipado (5.0 / 5.0)</span>
                    <Badge variant="outline" className="text-[10px] text-slate-400">Snapshot 2 • Fase CODING</Badge>
                  </div>
                  <p className="text-slate-300 italic border-l-2 border-emerald-500 pl-2">
                    "Estructuró tipado estricto con List y Dict de typing, manejó llaves faltantes de forma defensiva y ordenó listas de salida."
                  </p>
                </div>

                <div className="bg-slate-950/80 border border-slate-800 p-3 rounded-lg text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-blue-300">Anti-Cheat Cognitivo (Superado)</span>
                    <Badge variant="outline" className="text-[10px] text-slate-400">Turno 6 • Fase PROBE</Badge>
                  </div>
                  <p className="text-slate-300 italic border-l-2 border-blue-500 pl-2">
                    "Al ser cuestionado sobre streaming masivo de 50M de registros, propuso de inmediato generator chunks y ordenamiento externo (external merge sort)."
                  </p>
                </div>
              </div>

              {/* Ley 1581 Habeas Data Accordance */}
              <div className="bg-emerald-950/20 border border-emerald-800/40 p-3.5 rounded-lg flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <Shield className="h-5 w-5 text-emerald-400 shrink-0" />
                  <div className="text-[11px] text-emerald-200">
                    <strong>Cumplimiento Normativo Colombia (Ley 1581 de 2012):</strong> Titular anonimizado, sin recolección de datos sensibles biométricos.
                  </div>
                </div>
                <Link href="/privacy/policy" target="_blank">
                  <Button variant="ghost" size="sm" className="text-emerald-400 hover:text-emerald-300 text-xs">
                    Ver Política
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
