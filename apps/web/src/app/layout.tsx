import type { Metadata } from "next";
import { MswProvider } from "@/components/providers/msw-provider";
import { WebVitals } from "@/components/providers/web-vitals";
import { ThemeProvider } from "@/components/providers/theme-provider";
import { Toaster } from "@/components/ui/toaster";
import "./globals.css";

export const metadata: Metadata = {
  title: "Evaluador Técnico de Candidatos",
  description: "Entrevistas técnicas asistidas por IA con evaluación de razonamiento e informe defendible",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="es" className="dark" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased text-foreground">
        <ThemeProvider defaultTheme="dark">
          <WebVitals />
          <MswProvider>{children}</MswProvider>
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
