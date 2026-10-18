"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Briefcase,
  Users,
  PlusCircle,
  LayoutDashboard,
  LogOut,
  Building2,
  Shield,
} from "lucide-react";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const handleLogout = () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token");
    }
    router.push("/login");
  };

  const navItems = [
    {
      label: "Resumen",
      href: "/dashboard",
      icon: LayoutDashboard,
      active: pathname === "/dashboard",
    },
    {
      label: "Vacantes",
      href: "/dashboard/vacancies",
      icon: Briefcase,
      active: pathname === "/dashboard/vacancies",
    },
    {
      label: "Nueva Vacante",
      href: "/dashboard/vacancies/new",
      icon: PlusCircle,
      active: pathname === "/dashboard/vacancies/new",
    },
  ];

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Top Navigation */}
      <header className="sticky top-0 z-40 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 max-w-screen-2xl items-center justify-between px-6">
          <div className="flex items-center gap-6">
            <Link href="/dashboard" className="flex items-center gap-2.5">
              <div className="h-8 w-8 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-bold text-sm">
                ET
              </div>
              <span className="font-bold text-base tracking-tight hidden sm:inline-block">
                Evaluador Técnico
              </span>
            </Link>

            <div className="h-4 w-[1px] bg-border hidden sm:block" />

            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Building2 className="h-3.5 w-3.5 text-primary" />
              <span className="font-medium text-foreground">Tech Colombia SAS</span>
              <Badge variant="secondary" className="text-[10px] py-0 px-1.5 font-mono">
                Staffing
              </Badge>
            </div>
          </div>

          {/* Right Action */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mr-2 hidden md:flex">
              <Shield className="h-3.5 w-3.5 text-emerald-500" />
              <span>Entrevistas Ciega a PII</span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleLogout}
              className="text-xs gap-1.5 text-muted-foreground hover:text-foreground"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Cerrar Sesión</span>
            </Button>
          </div>
        </div>

        {/* Sub Navigation Bar */}
        <div className="border-t border-border/30 bg-muted/10">
          <div className="container max-w-screen-2xl px-6 flex items-center gap-1 overflow-x-auto py-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.href} href={item.href}>
                  <Button
                    variant={item.active ? "secondary" : "ghost"}
                    size="sm"
                    className={`h-8 gap-2 text-xs font-medium ${
                      item.active ? "bg-secondary text-foreground shadow-sm" : "text-muted-foreground"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.label}
                  </Button>
                </Link>
              );
            })}
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 container max-w-screen-2xl px-6 py-8">
        {children}
      </main>
    </div>
  );
}
