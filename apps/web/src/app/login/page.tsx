"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api/client";
import { ShieldCheck, ArrowLeft, Loader2, Sparkles } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      await api.login(email, password);
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Error al iniciar sesión");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDemoLogin = async () => {
    setEmail("reclutador@tech-colombia.co");
    setPassword("demo123456");
    setIsLoading(true);
    setError(null);

    try {
      await api.login("reclutador@tech-colombia.co", "demo123456");
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.message || "Error al iniciar sesión");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-gradient-to-b from-background to-muted/20">
      <div className="w-full max-w-md space-y-6">
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Volver al inicio
          </Link>
          <Badge variant="outline" className="font-mono text-xs">
            Sprint 1: Auth & Vacantes
          </Badge>
        </div>

        <Card className="border-border/80 shadow-lg">
          <CardHeader className="space-y-1">
            <div className="flex items-center gap-2 mb-1">
              <div className="h-8 w-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center font-bold text-sm">
                ET
              </div>
              <CardTitle className="text-xl">Panel de Reclutamiento</CardTitle>
            </div>
            <CardDescription>
              Inicia sesión para gestionar vacantes, invitar candidatos y auditar reportes.
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleSubmit}>
            <CardContent className="space-y-4">
              {error && (
                <div className="p-3 text-xs rounded-md bg-destructive/15 text-destructive border border-destructive/20 font-medium">
                  {error}
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="email">Correo Corporativo</Label>
                <Input
                  id="email"
                  type="email"
                  placeholder="reclutador@empresa.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="password">Contraseña</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </div>
            </CardContent>

            <CardFooter className="flex flex-col gap-3">
              <Button type="submit" className="w-full" disabled={isLoading}>
                {isLoading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Autenticando...
                  </>
                ) : (
                  "Iniciar Sesión"
                )}
              </Button>

              <div className="relative w-full my-1">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t border-border" />
                </div>
                <div className="relative flex justify-center text-xs uppercase">
                  <span className="bg-card px-2 text-muted-foreground">O usa</span>
                </div>
              </div>

              <Button
                type="button"
                variant="outline"
                className="w-full gap-2 border-primary/30 hover:bg-primary/5 text-primary"
                onClick={handleDemoLogin}
                disabled={isLoading}
              >
                <Sparkles className="h-4 w-4 text-primary" />
                Acceso Rápido Demo (1 Clic)
              </Button>
            </CardFooter>
          </form>
        </Card>

        <div className="flex items-center justify-center gap-2 text-xs text-muted-foreground">
          <ShieldCheck className="h-4 w-4 text-emerald-500" />
          <span>Acceso seguro protegido con tokens JWT y Ley 1581</span>
        </div>
      </div>
    </div>
  );
}
