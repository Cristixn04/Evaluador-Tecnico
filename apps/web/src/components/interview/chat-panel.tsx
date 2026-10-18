"use client";

import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { ChatMessage } from "@/lib/hooks/use-interview-socket";
import { Send, Bot, User, Sparkles, CornerDownLeft } from "lucide-react";

interface ChatPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSendMessage: (text: string) => void;
}

const QUICK_PROMPTS = [
  "¿Cómo debemos manejar las diferencias de centavos?",
  "¿El lote de entrada cabe completamente en memoria?",
  "Tengo una propuesta de diseño para compartir.",
];

export function ChatPanel({
  messages,
  isStreaming,
  onSendMessage,
}: ChatPanelProps) {
  const [inputText, setInputText] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll al recibir nuevos mensajes o tokens
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || isStreaming) return;
    onSendMessage(inputText);
    setInputText("");
  };

  const handleQuickPrompt = (prompt: string) => {
    if (isStreaming) return;
    onSendMessage(prompt);
  };

  return (
    <div className="flex flex-col h-full bg-background border-r border-border/40">
      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => {
          if (msg.speaker === "system") {
            return (
              <div
                key={msg.id}
                className="text-center my-2"
              >
                <span className="text-[11px] font-mono bg-muted/60 text-muted-foreground px-2.5 py-1 rounded-full border border-border/40">
                  ⚡ {msg.content}
                </span>
              </div>
            );
          }

          const isAgent = msg.speaker === "agent";

          return (
            <div
              key={msg.id}
              className={`flex items-start gap-2.5 ${
                isAgent ? "justify-start" : "justify-end"
              }`}
            >
              {isAgent && (
                <div className="h-7 w-7 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 mt-0.5">
                  <Bot className="h-4 w-4" />
                </div>
              )}

              <div
                className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-xs sm:text-sm leading-relaxed shadow-sm ${
                  isAgent
                    ? "bg-card border border-border/60 text-foreground"
                    : "bg-primary text-primary-foreground font-normal"
                }`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                <span
                  className={`text-[9px] block mt-1 ${
                    isAgent ? "text-muted-foreground" : "text-primary-foreground/70"
                  }`}
                >
                  {new Date(msg.timestamp).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>

              {!isAgent && (
                <div className="h-7 w-7 rounded-lg bg-secondary flex items-center justify-center text-foreground shrink-0 mt-0.5">
                  <User className="h-4 w-4" />
                </div>
              )}
            </div>
          );
        })}

        {isStreaming && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground italic pl-9 animate-pulse">
            <Sparkles className="h-3.5 w-3.5 text-primary" />
            <span>El entrevistador está escribiendo...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Quick Prompts Bar */}
      <div className="px-4 py-2 border-t border-border/30 bg-muted/10 flex gap-1.5 overflow-x-auto">
        {QUICK_PROMPTS.map((q) => (
          <button
            key={q}
            type="button"
            disabled={isStreaming}
            onClick={() => handleQuickPrompt(q)}
            className="text-[11px] whitespace-nowrap bg-background hover:bg-muted border border-border/60 text-muted-foreground hover:text-foreground px-2 py-1 rounded-md transition-colors disabled:opacity-50 shrink-0"
          >
            {q}
          </button>
        ))}
      </div>

      {/* Input Area */}
      <form
        onSubmit={handleSend}
        className="p-3 border-t border-border/50 bg-card/60 flex items-center gap-2"
      >
        <Input
          placeholder="Escribe tu pregunta o razonamiento..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          disabled={isStreaming}
          className="text-xs h-9 bg-background"
        />
        <Button
          type="submit"
          size="sm"
          disabled={isStreaming || !inputText.trim()}
          className="h-9 px-3 shrink-0 gap-1"
        >
          <Send className="h-3.5 w-3.5" />
          <CornerDownLeft className="h-3 w-3 opacity-60 hidden sm:inline" />
        </Button>
      </form>
    </div>
  );
}
