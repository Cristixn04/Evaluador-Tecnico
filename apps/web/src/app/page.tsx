import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, Terminal, Shield, Cpu, Code2, ArrowRight, Sparkles } from "lucide-react";

export default function Home() {
  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 max-w-screen-2xl items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-bold">
              ET
            </div>
            <div>
              <span className="font-bold text-lg tracking-tight">Evaluador Técnico</span>
              <span className="text-xs text-muted-foreground ml-2 font-mono">v0.1.0 (Sprint 1)</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/login">
              <Button variant="outline" size="sm" className="text-xs">
                Iniciar Sesión
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button size="sm" className="text-xs gap-1.5">
                Panel Reclutador <ArrowRight className="h-3.5 w-3.5" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 container max-w-screen-xl px-6 py-12">
        {/* Hero Section */}
        <div className="space-y-4 max-w-3xl mb-12">
          <Badge variant="outline" className="border-primary/40 text-primary px-3 py-1 text-xs">
            Inteligencia Artificial para Talento TI en Colombia
          </Badge>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-foreground">
            Evalúa el <span className="text-primary">razonamiento</span>, no solo la respuesta binaria.
          </h1>
          <p className="text-lg text-muted-foreground leading-relaxed">
            Agente de IA que conduce la entrevista técnica inicial, plantea problemas reales, analiza la trayectoria de depuración y entrega un informe defendible y libre de sesgos para tus vacantes.
          </p>
          <div className="flex flex-wrap gap-4 pt-2">
            <Link href="/dashboard/vacancies/new">
              <Button size="lg" className="gap-2">
                <Sparkles className="h-4 w-4" /> Probar Parser de Vacantes con IA
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button variant="outline" size="lg">
                Ver Panel de Control
              </Button>
            </Link>
          </div>
        </div>

        {/* Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12">
          <Card className="border-border/60 bg-card/50">
            <CardHeader className="pb-3">
              <div className="h-10 w-10 rounded-lg bg-blue-500/10 text-blue-400 flex items-center justify-center mb-2">
                <Code2 className="h-5 w-5" />
              </div>
              <CardTitle className="text-lg">Frontend & UX (Cristian)</CardTitle>
              <CardDescription>Sprint 1: Mocking con MSW y Vacantes</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-2 text-foreground font-medium">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Mocking con MSW activado en navegador</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Pantalla Crear Vacante con IA y chips</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Generador de invitaciones con PII aislada</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-card/50">
            <CardHeader className="pb-3">
              <div className="h-10 w-10 rounded-lg bg-purple-500/10 text-purple-400 flex items-center justify-center mb-2">
                <Cpu className="h-5 w-5" />
              </div>
              <CardTitle className="text-lg">Backend & IA (Samuel)</CardTitle>
              <CardDescription>Sprint 1: FastAPI + Grok Gateway</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-2 text-foreground font-medium">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Esqueleto FastAPI y healthcheck</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Modelos SQLAlchemy y contratos sincronizados</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>LLM Gateway compatible con Grok / OpenAI</span>
              </div>
            </CardContent>
          </Card>

          <Card className="border-border/60 bg-card/50">
            <CardHeader className="pb-3">
              <div className="h-10 w-10 rounded-lg bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-2">
                <Shield className="h-5 w-5" />
              </div>
              <CardTitle className="text-lg">Privacidad & Contratos</CardTitle>
              <CardDescription>Capa de Contratos (@evaluador/contracts)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-2 text-foreground font-medium">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Protocolo WebSocket tipado</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>PII segregada por diseño (Ley 1581)</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Desarrollo desacoplado con mocks</span>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Quick Command Guide */}
        <Card className="border-border/60 bg-muted/20">
          <CardHeader>
            <div className="flex items-center gap-2 font-mono text-sm text-muted-foreground">
              <Terminal className="h-4 w-4" />
              <span>Orquestación de Comandos (Makefile)</span>
            </div>
            <CardTitle className="text-base">Comandos Rápidos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono text-xs">
              <div className="bg-background/80 p-3 rounded-md border border-border/40">
                <span className="text-primary font-bold">make dev-web</span>
                <p className="text-muted-foreground mt-1">Next.js en puerto 3000 con MSW activo</p>
              </div>
              <div className="bg-background/80 p-3 rounded-md border border-border/40">
                <span className="text-primary font-bold">make dev-api</span>
                <p className="text-muted-foreground mt-1">FastAPI en puerto 8000</p>
              </div>
              <div className="bg-background/80 p-3 rounded-md border border-border/40">
                <span className="text-primary font-bold">make docker-up</span>
                <p className="text-muted-foreground mt-1">PostgreSQL 16 y Redis 7</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="border-t border-border/40 py-6 text-center text-xs text-muted-foreground">
        Evaluador Técnico de Candidatos · Proyecto Colaborativo Samuel & Cristian · Conforme con Ley 1581 de 2012
      </footer>
    </div>
  );
}
