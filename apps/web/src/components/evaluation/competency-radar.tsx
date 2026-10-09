"use client";

import React from "react";
import {
  ResponsiveContainer,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Tooltip,
} from "recharts";

interface CompetencyRadarProps {
  competencies: Record<string, number>;
  selectedCompetency?: string | null;
  onSelectCompetency?: (competency: string) => void;
}

export function CompetencyRadar({
  competencies,
  selectedCompetency,
  onSelectCompetency,
}: CompetencyRadarProps) {
  const chartData = Object.entries(competencies).map(([name, score]) => ({
    subject: name,
    score: score,
    fullMark: 5,
  }));

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      return (
        <div className="bg-slate-900/95 border border-slate-700/80 rounded-lg p-2.5 shadow-xl text-xs backdrop-blur-md">
          <p className="font-semibold text-slate-100">{data.subject}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-cyan-400 font-mono font-bold text-sm">
              {data.score.toFixed(1)} / 5.0
            </span>
            <span className="text-slate-400">
              ({Math.round((data.score / 5) * 100)}%)
            </span>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="w-full h-[320px] flex flex-col items-center justify-center relative">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart
          cx="50%"
          cy="50%"
          outerRadius="72%"
          data={chartData}
          onClick={(e: any) => {
            if (e && e.activeLabel && onSelectCompetency) {
              onSelectCompetency(e.activeLabel);
            }
          }}
        >
          <PolarGrid stroke="#334155" strokeDasharray="3 3" />
          <PolarAngleAxis
            dataKey="subject"
            tick={(props: any) => {
              const { payload, x, y } = props;
              const isSelected = selectedCompetency === payload?.value;
              return (
                <text
                  x={x}
                  y={y}
                  className={`text-[11px] font-medium transition-colors cursor-pointer select-none ${
                    isSelected
                      ? "fill-cyan-300 font-bold drop-shadow-[0_0_8px_rgba(6,182,212,0.6)]"
                      : "fill-slate-300 hover:fill-slate-100"
                  }`}
                  textAnchor="middle"
                  onClick={() => onSelectCompetency?.(payload?.value)}
                >
                  {payload?.value}
                </text>
              );
            }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 5]}
            tickCount={6}
            stroke="#475569"
            tick={{ fill: "#64748b", fontSize: 10 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Radar
            name="Score Candidato"
            dataKey="score"
            stroke="#06b6d4"
            fill="#06b6d4"
            fillOpacity={0.38}
            strokeWidth={2.5}
            dot={{ r: 4, fill: "#22d3ee", stroke: "#083344", strokeWidth: 1.5 }}
            activeDot={{ r: 6, fill: "#38bdf8", stroke: "#ffffff", strokeWidth: 2 }}
          />
        </RadarChart>
      </ResponsiveContainer>

      <div className="text-[11px] text-slate-400 mt-[-8px] flex items-center gap-1.5">
        <span className="inline-block w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
        <span>Haz clic en un vértice para filtrar las evidencias auditadas</span>
      </div>
    </div>
  );
}
