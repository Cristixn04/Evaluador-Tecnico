"use client";

import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import type { InterviewTrajectory, TrajectorySnapshot } from "@/lib/api/client";
import {
  Play,
  Pause,
  SkipBack,
  SkipForward,
  RotateCcw,
  CheckCircle,
  XCircle,
  Clock,
  Code2,
  Copy,
  Check,
  FileCode,
  Sparkles,
} from "lucide-react";

const Editor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

interface TrajectoryPlayerProps {
  trajectory: InterviewTrajectory;
}

export function TrajectoryPlayer({ trajectory }: TrajectoryPlayerProps) {
  const snapshots = trajectory.snapshots || [];
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState<1 | 2>(1);
  const [copied, setCopied] = useState(false);

  const currentSnapshot: TrajectorySnapshot | undefined = snapshots[currentIndex];

  // Temporizador para reproducción automática
  useEffect(() => {
    if (!isPlaying) return;

    const intervalTime = playbackSpeed === 1 ? 2500 : 1250;
    const timer = setInterval(() => {
      setCurrentIndex((prev) => {
        if (prev >= snapshots.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, intervalTime);

    return () => clearInterval(timer);
  }, [isPlaying, playbackSpeed, snapshots.length]);

  const handleCopyCode = () => {
    if (!currentSnapshot) return;
    navigator.clipboard.writeText(currentSnapshot.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const formatSeconds = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  if (snapshots.length === 0) {
    return (
      <div className="p-8 rounded-xl bg-slate-900/50 border border-slate-800 text-center text-sm text-slate-400">
        No hay snapshots de código registrados en la trayectoria.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/90 overflow-hidden shadow-2xl flex flex-col">
      {/* Header del Reproductor */}
      <div className="px-5 py-4 border-b border-slate-800 bg-slate-950/60 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-cyan-950/80 border border-cyan-800/60 flex items-center justify-center text-cyan-400">
            <Code2 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-100 flex items-center gap-2">
              Reproductor de Trayectoria de Depuración
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800/80">
                Paso {currentIndex + 1} de {snapshots.length}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Inspecciona paso a paso cómo evolucionó el razonamiento y el código durante la sesión.
            </p>
          </div>
        </div>

        {/* Metadatos del Snapshot Actual */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Tiempo */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-800/80 border border-slate-700/60 text-xs text-slate-200 font-mono">
            <Clock className="w-3.5 h-3.5 text-cyan-400" />
            <span>Minuto {formatSeconds(currentSnapshot?.timestamp_offset_seconds || 0)}</span>
          </div>

          {/* Fase */}
          <span className="px-2.5 py-1 rounded-md bg-slate-800/80 border border-slate-700/60 text-xs text-purple-300 font-semibold font-mono">
            {currentSnapshot?.phase}
          </span>

          {/* Resultado de Tests en este snapshot */}
          {currentSnapshot?.total_tests !== undefined && currentSnapshot.total_tests > 0 && (
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-medium border ${
                currentSnapshot.execution_status === "success"
                  ? "bg-emerald-950/80 border-emerald-700/60 text-emerald-300"
                  : "bg-rose-950/80 border-rose-700/60 text-rose-300"
              }`}
            >
              {currentSnapshot.execution_status === "success" ? (
                <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
              ) : (
                <XCircle className="w-3.5 h-3.5 text-rose-400" />
              )}
              <span>
                {currentSnapshot.tests_passed}/{currentSnapshot.total_tests} tests
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Nota Explicativa del Momento */}
      {currentSnapshot?.event_note && (
        <div className="px-5 py-2.5 bg-cyan-950/30 border-b border-cyan-900/40 flex items-center gap-2.5 text-xs text-cyan-200">
          <Sparkles className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
          <span className="font-medium">{currentSnapshot.event_note}</span>
        </div>
      )}

      {/* Visor de Código (Monaco Editor en modo lectura) */}
      <div className="relative h-[380px] bg-[#1e1e1e]">
        <Editor
          height="100%"
          language={currentSnapshot?.language || "python"}
          value={currentSnapshot?.code || ""}
          theme="vs-dark"
          options={{
            readOnly: true,
            domReadOnly: true,
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            scrollBeyondLastLine: false,
            renderWhitespace: "selection",
            automaticLayout: true,
          }}
        />

        {/* Botón Flotante para Copiar */}
        <button
          onClick={handleCopyCode}
          className="absolute top-3 right-3 px-3 py-1.5 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700/80 text-xs text-slate-300 flex items-center gap-1.5 shadow-lg backdrop-blur-sm transition-all"
          title="Copiar código en este snapshot"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400">Copiado</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copiar código</span>
            </>
          )}
        </button>
      </div>

      {/* Barra de Controles y Timeline Scrubber */}
      <div className="px-5 py-4 bg-slate-950/80 border-t border-slate-800 space-y-3">
        {/* Scrubber slider con marcas */}
        <div className="relative flex items-center">
          <input
            type="range"
            min={0}
            max={snapshots.length - 1}
            value={currentIndex}
            onChange={(e) => {
              setCurrentIndex(parseInt(e.target.value, 10));
              setIsPlaying(false);
            }}
            className="w-full h-2 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-cyan-400 focus:outline-none"
          />
        </div>

        {/* Hitos / Marcadores visuales de snapshots */}
        <div className="flex justify-between px-1">
          {snapshots.map((snap, idx) => {
            const isCurrent = idx === currentIndex;
            const isSuccess = snap.execution_status === "success";
            const isFailure = snap.execution_status === "test_failure";

            return (
              <button
                key={idx}
                onClick={() => {
                  setCurrentIndex(idx);
                  setIsPlaying(false);
                }}
                className="group flex flex-col items-center focus:outline-none"
                title={`Paso ${idx + 1}: ${snap.event_note || snap.phase}`}
              >
                <div
                  className={`w-3 h-3 rounded-full transition-all border ${
                    isCurrent
                      ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-950 scale-125"
                      : "opacity-70 group-hover:opacity-100 group-hover:scale-110"
                  } ${
                    isSuccess
                      ? "bg-emerald-500 border-emerald-300"
                      : isFailure
                      ? "bg-rose-500 border-rose-300"
                      : "bg-slate-500 border-slate-400"
                  }`}
                />
                <span className="text-[10px] text-slate-500 font-mono mt-1 group-hover:text-slate-300">
                  {formatSeconds(snap.timestamp_offset_seconds)}
                </span>
              </button>
            );
          })}
        </div>

        {/* Controles de reproducción */}
        <div className="flex items-center justify-between pt-1">
          <div className="flex items-center gap-2">
            {/* Reiniciar */}
            <button
              onClick={() => {
                setCurrentIndex(0);
                setIsPlaying(false);
              }}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 transition-colors"
              title="Ir al inicio"
            >
              <RotateCcw className="w-4 h-4" />
            </button>

            {/* Paso anterior */}
            <button
              onClick={() => {
                setCurrentIndex((prev) => Math.max(0, prev - 1));
                setIsPlaying(false);
              }}
              disabled={currentIndex === 0}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="Paso anterior"
            >
              <SkipBack className="w-4 h-4" />
            </button>

            {/* Play / Pausa */}
            <button
              onClick={() => {
                if (currentIndex >= snapshots.length - 1) {
                  setCurrentIndex(0);
                }
                setIsPlaying(!isPlaying);
              }}
              className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-slate-950 font-semibold text-xs flex items-center gap-1.5 shadow-md shadow-cyan-900/40 transition-all"
            >
              {isPlaying ? (
                <>
                  <Pause className="w-4 h-4 fill-current" />
                  <span>Pausar</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  <span>Reproducir</span>
                </>
              )}
            </button>

            {/* Paso siguiente */}
            <button
              onClick={() => {
                setCurrentIndex((prev) => Math.min(snapshots.length - 1, prev + 1));
                setIsPlaying(false);
              }}
              disabled={currentIndex === snapshots.length - 1}
              className="p-2 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              title="Paso siguiente"
            >
              <SkipForward className="w-4 h-4" />
            </button>
          </div>

          {/* Velocidad de Reproducción */}
          <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs">
            <button
              onClick={() => setPlaybackSpeed(1)}
              className={`px-2 py-0.5 rounded font-mono font-medium transition-colors ${
                playbackSpeed === 1
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-800"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              1x
            </button>
            <button
              onClick={() => setPlaybackSpeed(2)}
              className={`px-2 py-0.5 rounded font-mono font-medium transition-colors ${
                playbackSpeed === 2
                  ? "bg-cyan-950 text-cyan-300 border border-cyan-800"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              2x
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
