import type { Metadata } from "next";
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
    <html lang="es" className="dark">
      <body className="min-h-screen bg-background font-sans antialiased text-foreground">
        {children}
      </body>
    </html>
  );
}
