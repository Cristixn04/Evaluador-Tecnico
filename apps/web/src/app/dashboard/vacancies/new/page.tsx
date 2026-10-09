"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type Vacancy } from "@/lib/api/client";
import {
  Sparkles,
  ArrowLeft,
  CheckCircle2,
  X,
  Plus,
  Loader2,
  FileText,
  Save,
} from "lucide-react";

const TEMPLATES = [
  {
    name: "Fintech PSE (Python Senior)",
    title: "Senior Backend Engineer - Pasarela PSE",
    description: `Buscamos un Ingeniero de Backend Senior en Colombia para liderar la arquitectura de conciliación de pagos con PSE y liquidación bancaria en nuestra Fintech.
Requisitos:
- 5+ años de experiencia sólida en Python y frameworks modernos como FastAPI o Django.
- Diseño de bases de datos relacionales en PostgreSQL con alta concurrencia y transacciones ACID.
- Manejo de tareas asíncronas con Redis y Celery/ARQ.
- Contenerización con Docker y despliegues en AWS.
- Deseable: Experiencia en protocolos ACH, idempotencia y microservicios con Apache Kafka.`,
  },
  {
    name: "Startup Logística (Next.js Mid)",
    title: "Frontend Developer - Tracking en Tiempo Real",
    description: `En nuestra startup de logística y envíos urbanos en Bogotá requerimos un desarrollador Frontend Mid para la plataforma de monitoreo de rutas en vivo.
Requisitos:
- 3+ años en JavaScript moderno y TypeScript.
- Dominio de React 18+ y Next.js (App Router).
- Maquetación avanzada con Tailwind CSS y componentes accesibles.
- Deseable: Experiencia con WebSockets para streaming de coordenadas y pruebas con Vitest.`,
  },
  {
    name: "E-Commerce (Data Engineer)",
    title: "Data Engineer - Modelado de Ventas",
    description: `Empresa líder de retail digital busca Data Engineer para optimizar pipelines de datos y consultas analíticas.
Requisitos:
- Dominio experto de SQL avanzado y PostgreSQL.
- Python para pipelines ETL y automatización.
- Modelado de bases de datos dimensionales (Star schema / Snowflake).
- Deseable: Manejo de dbt, BigQuery o Apache Airflow.`,
  },
];

export default function NewVacancyPage() {
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [rawDescription, setRawDescription] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Perfil analizado (extraído)
  const [analyzedVacancy, setAnalyzedVacancy] = useState<Vacancy | null>(null);
  const [requiredSkills, setRequiredSkills] = useState<string[]>([]);
  const [preferredSkills, setPreferredSkills] = useState<string[]>([]);
  const [seniority, setSeniority] = useState<"junior" | "mid" | "senior" | "lead">("senior");
  const [newSkillInput, setNewSkillInput] = useState("");

  const handleApplyTemplate = (tpl: (typeof TEMPLATES)[0]) => {
    setTitle(tpl.title);
    setRawDescription(tpl.description);
    setAnalyzedVacancy(null);
  };

  const handleAnalyze = async () => {
    if (!rawDescription.trim()) return;
    setIsAnalyzing(true);

    try {
      const result = await api.createVacancy({
        title: title || "Vacante sin título",
        raw_description: rawDescription,
      });

      setAnalyzedVacancy(result);
      setRequiredSkills(result.profile?.required_skills || []);
      setPreferredSkills(result.profile?.preferred_skills || []);
      setSeniority(result.seniority);
    } catch (err) {
      console.error(err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleRemoveSkill = (skillToRemove: string, isRequired: boolean) => {
    if (isRequired) {
      setRequiredSkills(requiredSkills.filter((s) => s !== skillToRemove));
    } else {
      setPreferredSkills(preferredSkills.filter((s) => s !== skillToRemove));
    }
  };

  const handleAddSkill = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSkillInput.trim()) return;
    if (!requiredSkills.includes(newSkillInput.trim())) {
      setRequiredSkills([...requiredSkills, newSkillInput.trim()]);
    }
    setNewSkillInput("");
  };

  const handleSaveAndFinish = () => {
    setIsSaving(true);
    setTimeout(() => {
      setIsSaving(false);
      router.push("/dashboard/vacancies");
    }, 600);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Top Breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href="/dashboard/vacancies"
          className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Volver a vacantes
        </Link>
        <Badge variant="outline" className="text-xs font-mono">
          IA Vacancy Parser
        </Badge>
      </div>

      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Crear Vacante con Análisis de IA</h1>
        <p className="text-sm text-muted-foreground">
          Pega el texto libre de la oferta laboral o usa una plantilla. Nuestro agente estructurará las competencias técnicas requeridas para la entrevista.
        </p>
      </div>

      {/* Templates Selector */}
      <div className="space-y-2">
        <span className="text-xs font-semibold text-muted-foreground">
          Plantillas Rápidas de Vacantes Reales:
        </span>
        <div className="flex flex-wrap gap-2">
          {TEMPLATES.map((tpl) => (
            <Button
              key={tpl.name}
              type="button"
              variant="outline"
              size="sm"
              className="text-xs gap-1.5 h-8 bg-card"
              onClick={() => handleApplyTemplate(tpl)}
            >
              <FileText className="h-3.5 w-3.5 text-primary" />
              {tpl.name}
            </Button>
          ))}
        </div>
      </div>

      {/* Form Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input Column */}
        <Card className="border-border/70">
          <CardHeader>
            <CardTitle className="text-base">Descripción de la Vacante</CardTitle>
            <CardDescription className="text-xs">
              Pega los requerimientos tal como los publicas en LinkedIn o portales de empleo.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="title">Título del Cargo</Label>
              <Input
                id="title"
                placeholder="Ej. Senior Backend Developer"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="desc">Texto de la Oferta / Requisitos</Label>
              <Textarea
                id="desc"
                rows={12}
                placeholder="Pega aquí la descripción completa..."
                value={rawDescription}
                onChange={(e) => setRawDescription(e.target.value)}
                className="font-sans text-xs leading-relaxed"
              />
            </div>

            <Button
              className="w-full gap-2 shadow-sm"
              onClick={handleAnalyze}
              disabled={isAnalyzing || !rawDescription.trim()}
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Analizando competencias con IA...
                </>
              ) : (
                <>
                  <Sparkles className="h-4 w-4" />
                  Analizar con IA
                </>
              )}
            </Button>
          </CardContent>
        </Card>

        {/* Parsed Profile Column */}
        <Card className="border-border/70">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="text-base">Perfil Extraído por la IA</CardTitle>
              {analyzedVacancy && (
                <Badge variant="secondary" className="text-emerald-400 gap-1 text-[11px]">
                  <CheckCircle2 className="h-3 w-3" />
                  Listo
                </Badge>
              )}
            </div>
            <CardDescription className="text-xs">
              Revisa y ajusta las competencias antes de vincular el banco de problemas técnicos.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {isAnalyzing ? (
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Skeleton className="h-4 w-28" />
                  <Skeleton className="h-8 w-full" />
                </div>
                <div className="space-y-2">
                  <Skeleton className="h-4 w-36" />
                  <div className="flex gap-2">
                    <Skeleton className="h-7 w-20 rounded-full" />
                    <Skeleton className="h-7 w-24 rounded-full" />
                    <Skeleton className="h-7 w-16 rounded-full" />
                  </div>
                </div>
                <div className="space-y-2">
                  <Skeleton className="h-4 w-40" />
                  <Skeleton className="h-16 w-full" />
                </div>
              </div>
            ) : !analyzedVacancy ? (
              <div className="py-16 text-center text-muted-foreground text-xs space-y-2 border rounded-lg border-dashed">
                <Sparkles className="h-8 w-8 mx-auto opacity-30 text-primary" />
                <p>Haz clic en "Analizar con IA" para estructurar los requerimientos.</p>
              </div>
            ) : (
              <div className="space-y-4 animate-in fade-in duration-300">
                {/* Seniority Selector */}
                <div className="space-y-1.5">
                  <Label className="text-xs">Nivel de Seniority Sugerido:</Label>
                  <div className="flex gap-2">
                    {(["junior", "mid", "senior", "lead"] as const).map((lvl) => (
                      <Button
                        key={lvl}
                        type="button"
                        size="sm"
                        variant={seniority === lvl ? "default" : "outline"}
                        className="h-7 text-xs capitalize"
                        onClick={() => setSeniority(lvl)}
                      >
                        {lvl}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Primary Language */}
                <div className="space-y-1">
                  <Label className="text-xs">Lenguaje Principal de Evaluación:</Label>
                  <div className="p-2 rounded bg-muted/30 border border-border/40 font-mono text-xs uppercase text-primary font-bold">
                    {analyzedVacancy.profile?.primary_language || "python"}
                  </div>
                </div>

                {/* Required Skills Chips */}
                <div className="space-y-2">
                  <Label className="text-xs">Habilidades Obligatorias (Evaluadas en Sala):</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {requiredSkills.map((skill) => (
                      <Badge
                        key={skill}
                        variant="secondary"
                        className="gap-1 py-1 px-2.5 text-xs font-normal"
                      >
                        <span>{skill}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveSkill(skill, true)}
                          className="hover:text-destructive transition-colors ml-0.5"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>

                  {/* Add Skill Input */}
                  <form onSubmit={handleAddSkill} className="flex gap-2 pt-1">
                    <Input
                      placeholder="Añadir otra habilidad..."
                      value={newSkillInput}
                      onChange={(e) => setNewSkillInput(e.target.value)}
                      className="h-8 text-xs"
                    />
                    <Button type="submit" size="sm" variant="outline" className="h-8 text-xs gap-1">
                      <Plus className="h-3.5 w-3.5" />
                      Agregar
                    </Button>
                  </form>
                </div>

                {/* Preferred Skills */}
                <div className="space-y-1.5">
                  <Label className="text-xs">Habilidades Deseables:</Label>
                  <div className="flex flex-wrap gap-1.5">
                    {preferredSkills.map((skill) => (
                      <Badge
                        key={skill}
                        variant="outline"
                        className="gap-1 py-0.5 px-2 text-xs font-normal text-muted-foreground"
                      >
                        <span>{skill}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveSkill(skill, false)}
                          className="hover:text-destructive transition-colors"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                </div>

                <div className="pt-4 border-t border-border/40">
                  <Button
                    className="w-full gap-2"
                    onClick={handleSaveAndFinish}
                    disabled={isSaving}
                  >
                    {isSaving ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="h-4 w-4" />
                    )}
                    Guardar y Activar Vacante
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
