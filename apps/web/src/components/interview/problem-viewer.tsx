import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { AlertCircle, CheckCircle2, FileCode, Layers } from "lucide-react";

interface ProblemViewerProps {
  problem: {
    id: string;
    title: string;
    difficulty: string;
    language: string;
    scenario_preview: string;
    tags?: string[];
  };
}

export function ProblemViewer({ problem }: ProblemViewerProps) {
  return (
    <div className="h-full overflow-y-auto p-5 space-y-5 text-sm">
      {/* Title & Metadata */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono text-xs uppercase text-primary">
            {problem.language}
          </Badge>
          <Badge variant="secondary" className="text-xs capitalize">
            Nivel: {problem.difficulty}
          </Badge>
        </div>
        <h2 className="text-xl font-bold tracking-tight text-foreground">
          {problem.title}
        </h2>
        <div className="flex flex-wrap gap-1.5 pt-1">
          {problem.tags?.map((t) => (
            <Badge key={t} variant="outline" className="text-[11px] font-normal text-muted-foreground">
              #{t}
            </Badge>
          ))}
        </div>
      </div>

      {/* Real World Scenario */}
      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <Layers className="h-4 w-4 text-primary" />
          Escenario Real
        </h3>
        <p className="text-muted-foreground leading-relaxed text-xs sm:text-sm">
          {problem.scenario_preview}
        </p>
      </div>

      {/* Technical Objective */}
      <div className="p-4 rounded-lg bg-muted/30 border border-border/50 space-y-2 text-xs">
        <span className="font-bold text-foreground block">
          🎯 Objetivo de la prueba:
        </span>
        <ul className="space-y-1.5 text-muted-foreground list-disc pl-4">
          <li>
            Implementar la función <code className="text-primary font-mono font-semibold">reconcile_transactions(internal_ledger, bank_statement)</code>.
          </li>
          <li>
            Identificar transacciones exactamente conciliadas, discrepancias de monto y registros huérfanos.
          </li>
          <li>
            Garantizar idempotencia: si un lote se procesa dos veces, el resultado debe ser idéntico.
          </li>
        </ul>
      </div>

      {/* Constraints */}
      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <AlertCircle className="h-4 w-4 text-yellow-500" />
          Restricciones y Criterios de Evaluación
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
          <div className="p-2.5 rounded bg-card border border-border/60">
            <span className="text-muted-foreground block text-[10px] uppercase font-sans">Complejidad Temporal</span>
            <span className="text-foreground font-semibold">O(N log N) o mejor O(N)</span>
          </div>
          <div className="p-2.5 rounded bg-card border border-border/60">
            <span className="text-muted-foreground block text-[10px] uppercase font-sans">Complejidad Espacial</span>
            <span className="text-foreground font-semibold">O(N) memoria auxiliar</span>
          </div>
        </div>
      </div>

      {/* Example Cases */}
      <div className="space-y-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
          <FileCode className="h-4 w-4 text-blue-400" />
          Ejemplo de Entrada y Salida
        </h3>
        <Card className="bg-muted/20 border-border/60">
          <CardContent className="p-3 font-mono text-xs space-y-2">
            <div>
              <span className="text-muted-foreground block text-[10px]">Entrada:</span>
              <pre className="text-foreground overflow-x-auto p-2 bg-background/50 rounded">
{`internal = [
  {"id": "tx_101", "amount": 150000.0, "status": "PENDING"}
]
statement = [
  {"id": "tx_101", "amount": 150000.0, "code": "ACH_OK"}
]`}
              </pre>
            </div>
            <div>
              <span className="text-muted-foreground block text-[10px]">Salida esperada:</span>
              <pre className="text-emerald-400 overflow-x-auto p-2 bg-background/50 rounded">
{`{"matched": 1, "discrepancies": 0, "orphans": 0}`}
              </pre>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
