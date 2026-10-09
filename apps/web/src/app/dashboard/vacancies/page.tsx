"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, type Vacancy, type InvitationResponse } from "@/lib/api/client";
import {
  Briefcase,
  PlusCircle,
  UserPlus,
  Copy,
  Check,
  Shield,
  Loader2,
  ExternalLink,
} from "lucide-react";

export default function VacanciesPage() {
  const [vacancies, setVacancies] = useState<Vacancy[]>([]);
  const [loading, setLoading] = useState(true);

  // Estado del modal de invitación
  const [invitingVacancy, setInvitingVacancy] = useState<Vacancy | null>(null);
  const [candidateName, setCandidateName] = useState("");
  const [candidateEmail, setCandidateEmail] = useState("");
  const [invitingLoading, setInvitingLoading] = useState(false);
  const [generatedInvitation, setGeneratedInvitation] = useState<InvitationResponse | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function loadData() {
      try {
        const data = await api.getVacancies();
        setVacancies(data);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleSendInvitation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!invitingVacancy) return;
    setInvitingLoading(true);

    try {
      const inv = await api.createInvitation(invitingVacancy.id, {
        candidate_name: candidateName,
        candidate_email: candidateEmail,
      });
      setGeneratedInvitation(inv);
    } catch (err) {
      console.error(err);
    } finally {
      setInvitingLoading(false);
    }
  };

  const handleCopyLink = () => {
    if (generatedInvitation?.access_url) {
      navigator.clipboard.writeText(generatedInvitation.access_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const closeInvitationModal = () => {
    setInvitingVacancy(null);
    setCandidateName("");
    setCandidateEmail("");
    setGeneratedInvitation(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Vacantes y Perfiles Técnicos</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Gestiona los requerimientos de cada vacante y genera enlaces de evaluación para tus candidatos.
          </p>
        </div>
        <Link href="/dashboard/vacancies/new">
          <Button className="gap-2">
            <PlusCircle className="h-4 w-4" />
            Nueva Vacante con IA
          </Button>
        </Link>
      </div>

      {/* Vacancies List */}
      {loading ? (
        <div className="p-12 text-center text-sm text-muted-foreground border rounded-xl border-dashed">
          Cargando vacantes...
        </div>
      ) : vacancies.length === 0 ? (
        <Card className="p-12 text-center border-dashed">
          <Briefcase className="h-10 w-10 text-muted-foreground mx-auto mb-3 opacity-50" />
          <h3 className="text-base font-semibold">No hay vacantes configuradas</h3>
          <p className="text-sm text-muted-foreground mb-4 mt-1">
            Pega una descripción de vacante para extraer automáticamente las competencias con IA.
          </p>
          <Link href="/dashboard/vacancies/new">
            <Button>Crear Vacante Ahora</Button>
          </Link>
        </Card>
      ) : (
        <div className="space-y-4">
          {vacancies.map((vacancy) => (
            <Card key={vacancy.id} className="border-border/70 hover:border-border transition-all">
              <CardHeader className="pb-3">
                <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-lg">{vacancy.title}</CardTitle>
                      <Badge variant="outline" className="font-mono text-xs uppercase">
                        {vacancy.profile?.primary_language}
                      </Badge>
                      <Badge variant="secondary" className="capitalize text-xs">
                        {vacancy.seniority}
                      </Badge>
                    </div>
                    <CardDescription className="text-xs">
                      Categoría: {vacancy.role_category} · ID: {vacancy.id} · Creada el{" "}
                      {new Date(vacancy.created_at).toLocaleDateString("es-CO")}
                    </CardDescription>
                  </div>

                  <Button
                    size="sm"
                    className="gap-1.5 self-start sm:self-auto shrink-0"
                    onClick={() => {
                      setInvitingVacancy(vacancy);
                      setGeneratedInvitation(null);
                    }}
                  >
                    <UserPlus className="h-4 w-4" />
                    Invitar Candidato
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3 pt-1">
                <div>
                  <span className="text-xs font-semibold text-muted-foreground block mb-1.5">
                    Habilidades Obligatorias Extraídas:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {vacancy.profile?.required_skills?.map((skill) => (
                      <Badge key={skill} variant="secondary" className="text-xs font-normal">
                        {skill}
                      </Badge>
                    ))}
                  </div>
                </div>

                {vacancy.profile?.preferred_skills && vacancy.profile.preferred_skills.length > 0 && (
                  <div>
                    <span className="text-xs font-semibold text-muted-foreground block mb-1.5">
                      Deseables:
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {vacancy.profile.preferred_skills.map((skill) => (
                        <Badge
                          key={skill}
                          variant="outline"
                          className="text-xs font-normal text-muted-foreground"
                        >
                          {skill}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Modal / Overlay de Invitación de Candidato */}
      {invitingVacancy && (
        <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm flex items-center justify-center p-4">
          <Card className="w-full max-w-lg border-border shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-lg">Generar Invitación Técnica</CardTitle>
                <Badge variant="outline" className="text-[10px] font-mono">
                  Privacidad por Diseño
                </Badge>
              </div>
              <CardDescription>
                Vacante: <strong className="text-foreground">{invitingVacancy.title}</strong>
              </CardDescription>
            </CardHeader>

            {!generatedInvitation ? (
              <form onSubmit={handleSendInvitation}>
                <CardContent className="space-y-4">
                  <div className="p-3 text-xs rounded-md bg-muted/40 border border-border/60 flex items-start gap-2.5">
                    <Shield className="h-4 w-4 text-emerald-500 shrink-0 mt-0.5" />
                    <span className="text-muted-foreground">
                      Los datos personales que ingreses aquí se guardan de forma aislada. La sala de entrevista y el evaluador solo recibirán un código anónimo (`masked_candidate_id`).
                    </span>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="candName">Nombre completo del candidato</Label>
                    <Input
                      id="candName"
                      placeholder="Ej. Juan Pérez"
                      value={candidateName}
                      onChange={(e) => setCandidateName(e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="candEmail">Correo electrónico</Label>
                    <Input
                      id="candEmail"
                      type="email"
                      placeholder="juan.perez@ejemplo.com"
                      value={candidateEmail}
                      onChange={(e) => setCandidateEmail(e.target.value)}
                      required
                    />
                  </div>
                </CardContent>
                <div className="p-6 pt-0 flex items-center justify-end gap-2">
                  <Button type="button" variant="ghost" onClick={closeInvitationModal}>
                    Cancelar
                  </Button>
                  <Button type="submit" disabled={invitingLoading}>
                    {invitingLoading ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Generando...
                      </>
                    ) : (
                      "Generar Enlace Único"
                    )}
                  </Button>
                </div>
              </form>
            ) : (
              <CardContent className="space-y-4 pt-2">
                <div className="p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/20 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-emerald-400">
                      Enlace de Evaluación Creado
                    </span>
                    <Badge variant="secondary" className="font-mono text-xs">
                      {generatedInvitation.masked_candidate_id}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Comparte este enlace con el candidato. Expira en 72 horas.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label>Enlace de Acceso a la Sala:</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      readOnly
                      value={generatedInvitation.access_url}
                      className="font-mono text-xs bg-muted/30"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="icon"
                      onClick={handleCopyLink}
                      className="shrink-0"
                    >
                      {copied ? <Check className="h-4 w-4 text-emerald-500" /> : <Copy className="h-4 w-4" />}
                    </Button>
                  </div>
                </div>

                <div className="pt-4 flex items-center justify-between">
                  <a
                    href={generatedInvitation.access_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-primary hover:underline flex items-center gap-1 font-medium"
                  >
                    Abrir sala como candidato <ExternalLink className="h-3 w-3" />
                  </a>
                  <Button variant="default" size="sm" onClick={closeInvitationModal}>
                    Listo
                  </Button>
                </div>
              </CardContent>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}
