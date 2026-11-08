"use client";

import React, { memo, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

/**
 * Normaliza Markdown proveniente de LLM para garantizar que listas compactas,
 * secciones técnicas y ejemplos JSON se conviertan en árboles sintácticos válidos
 * bajo CommonMark / GFM, preservando streaming y seguridad.
 */
function normalizeMarkdown(text: string): string {
  if (!text) return "";

  // 1. Convertir JSON inline/raw precedido por 'json' a bloques fenced si es JSON válido
  let result = text.replace(
    /(?:^|\n|\s)(?:json|JSON)\s*([\[{][\s\S]*?[\]}])(?=\s*(?:[A-Z]|$))/g,
    (match, jsonBody) => {
      try {
        const parsed = JSON.parse(jsonBody);
        return "\n\n```json\n" + JSON.stringify(parsed, null, 2) + "\n```\n\n";
      } catch {
        return match;
      }
    }
  );

  // 2. Separar encabezados de sección técnica si vienen pegados en el texto
  result = result.replace(
    /([.?!])\s+(Requerimientos|Restricciones|Ejemplo|Notas?|Objetivo|Salida esperada|Entrada):?/gi,
    "$1\n\n**$2:**\n\n"
  );

  // 3. Normalizar listas numeradas compactas para que CommonMark las reconozca como <ol>
  result = result.replace(/([.:])\s*(\d+\.\s+)/g, "$1\n\n$2");
  result = result.replace(/(\n\d+\.[^\n]+?)\s+(\d+\.\s+)/g, "$1\n$2");

  // 4. Normalizar viñetas compactas para que CommonMark las reconozca como <ul>
  result = result.replace(/([.:])\s*([*-]\s+)/g, "$1\n\n$2");
  result = result.replace(/(\n[*-][^\n]+?)\s+([*-]\s+)/g, "$1\n$2");

  return result;
}

export const MarkdownRenderer = memo(function MarkdownRenderer({
  content,
  className = "",
}: MarkdownRendererProps) {
  const normalizedContent = useMemo(() => normalizeMarkdown(content), [content]);

  return (
    <div className={`max-w-none text-xs sm:text-sm leading-relaxed space-y-1.5 break-words ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h1 className="text-base font-bold my-2 text-foreground border-b border-border/40 pb-1">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-sm font-bold my-2 text-foreground">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-xs sm:text-sm font-semibold my-1.5 text-primary">
              {children}
            </h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-xs font-semibold my-1 text-foreground">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="mb-2 last:mb-0 leading-relaxed text-foreground/95">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-5 my-2 space-y-1 text-foreground/90">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-5 my-2 space-y-1 text-foreground/90">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-relaxed pl-0.5">
              {children}
            </li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-foreground">
              {children}
            </strong>
          ),
          em: ({ children }) => (
            <em className="italic text-foreground/90">
              {children}
            </em>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-primary/60 pl-3 my-2 italic text-muted-foreground bg-muted/20 py-1 rounded-r">
              {children}
            </blockquote>
          ),
          pre: ({ children }) => <>{children}</>,
          code: ({ className, children, ...props }) => {
            const { node, ...rest } = props as { node?: unknown; [key: string]: unknown };
            const match = /language-(\w+)/.exec(className || "");
            const rawText = String(children).replace(/\n$/, "");
            const isMultiline = rawText.includes("\n");

            if (match || isMultiline) {
              const lang = match ? match[1] : "";
              return (
                <div className="my-2.5 rounded-lg overflow-hidden border border-border/70 bg-slate-950 text-slate-100 shadow-sm">
                  {lang && (
                    <div className="px-3 py-1 bg-slate-900/90 border-b border-slate-800 text-[10px] font-mono text-cyan-400 font-medium uppercase tracking-wider flex items-center justify-between">
                      <span>{lang}</span>
                    </div>
                  )}
                  <pre className="p-3 text-slate-100 font-mono text-xs overflow-x-auto leading-relaxed">
                    <code>{rawText}</code>
                  </pre>
                </div>
              );
            }

            return (
              <code
                className="bg-muted/80 text-foreground font-mono text-[11px] sm:text-xs px-1.5 py-0.5 rounded border border-border/50 font-medium"
                {...rest}
              >
                {rawText}
              </code>
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto my-2.5 rounded-lg border border-border/60">
              <table className="min-w-full text-xs divide-y divide-border/60">
                {children}
              </table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-muted/50 font-semibold text-foreground">
              {children}
            </thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-border/40 bg-card/40">
              {children}
            </tbody>
          ),
          tr: ({ children }) => (
            <tr className="hover:bg-muted/30 transition-colors">
              {children}
            </tr>
          ),
          th: ({ children }) => (
            <th className="px-3 py-2 text-left font-semibold text-foreground border-r border-border/40 last:border-0">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 border-r border-border/40 last:border-0 text-foreground/90">
              {children}
            </td>
          ),
          a: ({ href, children }) => {
            const isSafe =
              href &&
              (href.startsWith("http://") ||
                href.startsWith("https://") ||
                href.startsWith("/"));
            if (!isSafe) {
              return (
                <span className="text-muted-foreground underline">
                  {children}
                </span>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline hover:text-primary/80 transition-colors"
              >
                {children}
              </a>
            );
          },
          hr: () => <hr className="my-3 border-border/50" />,
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
});
