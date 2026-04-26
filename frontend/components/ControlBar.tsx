"use client";

import { Loader2, Play, Square } from "lucide-react";
import { motion } from "framer-motion";
import type { AnalysisStatus } from "@/hooks/useAgentStream";

interface ControlBarProps {
  quarters: string[];
  year: number;
  onYearChange: (year: number) => void;
  selectedQuarter: string;
  onQuarterChange: (quarter: string) => void;
  targetNode: string;
  onTargetNodeChange: (value: string) => void;
  status: AnalysisStatus;
  onAnalyze: () => void;
  onStop: () => void;
}

const statusCopy: Record<AnalysisStatus, string> = {
  idle: "Ready",
  connecting: "Connecting to backend",
  streaming: "AI agents are reasoning",
  complete: "Analysis complete",
  error: "Something went wrong",
};

const statusDot: Record<AnalysisStatus, string> = {
  idle: "bg-zinc-500",
  connecting: "bg-amber-400 animate-pulse",
  streaming: "bg-emerald-400 animate-pulse",
  complete: "bg-emerald-500",
  error: "bg-red-500",
};

export function ControlBar({
  quarters,
  year,
  onYearChange,
  selectedQuarter,
  onQuarterChange,
  targetNode,
  onTargetNodeChange,
  status,
  onAnalyze,
  onStop,
}: ControlBarProps) {
  const isBusy = status === "connecting" || status === "streaming";

  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-white/10 bg-zinc-950/70 px-5 py-4 backdrop-blur lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3 text-zinc-100">
          <span className="text-xs uppercase tracking-[0.2em] text-emerald-400">
            ValueChain AI
          </span>
          <span className="hidden h-4 w-px bg-white/10 sm:inline-block" />
          <h1 className="text-base font-semibold sm:text-lg">
            Quarterly Supply Chain Estimator
          </h1>
        </div>
        <p className="text-xs text-zinc-400">
          Pick a target company and quarter — the multi-agent pipeline will
          estimate, evaluate, and self-correct the network in real time.
        </p>
      </div>

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <label className="flex flex-col gap-1 text-xs text-zinc-400">
          <span className="font-medium uppercase tracking-wider">
            Target Company
          </span>
          <input
            value={targetNode}
            onChange={(event) => onTargetNodeChange(event.target.value)}
            placeholder="e.g. 한미반도체"
            disabled={isBusy}
            className="h-9 w-48 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-zinc-100 outline-none transition focus:border-emerald-400/60 focus:ring-2 focus:ring-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-60"
          />
        </label>

        <div className="flex flex-col gap-1 text-xs text-zinc-400">
          <span className="font-medium uppercase tracking-wider">Year · Quarter</span>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={year}
              min={1900}
              max={2999}
              step={1}
              disabled={isBusy}
              onChange={(event) => {
                const next = parseInt(event.target.value, 10);
                if (!Number.isNaN(next)) onYearChange(next);
              }}
              className="h-9 w-24 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-zinc-100 outline-none transition focus:border-emerald-400/60 focus:ring-2 focus:ring-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-60"
            />
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 p-1">
              {quarters.map((quarter) => {
                const isActive = quarter === selectedQuarter;
                return (
                  <button
                    key={quarter}
                    type="button"
                    disabled={isBusy}
                    onClick={() => onQuarterChange(quarter)}
                    className={`relative rounded-md px-3 py-1.5 text-xs font-medium transition ${
                      isActive
                        ? "text-zinc-950"
                        : "text-zinc-300 hover:text-zinc-100 disabled:opacity-50"
                    }`}
                  >
                    {isActive && (
                      <motion.span
                        layoutId="quarter-indicator"
                        className="absolute inset-0 rounded-md bg-emerald-400"
                        transition={{ type: "spring", stiffness: 320, damping: 28 }}
                      />
                    )}
                    <span className="relative">{quarter}</span>
                  </button>
                );
              })}
            </div>
          </div>
          <span className="text-[10px] text-zinc-500">선택한 분기로 다음 분석 실행 ({year}-{selectedQuarter})</span>
        </div>

        <div className="flex items-center gap-3 lg:pl-3">
          <div className="flex items-center gap-2 text-xs text-zinc-300">
            <span className={`h-2 w-2 rounded-full ${statusDot[status]}`} />
            {statusCopy[status]}
          </div>
          {isBusy ? (
            <button
              type="button"
              onClick={onStop}
              className="inline-flex h-9 items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 text-sm font-medium text-red-300 transition hover:bg-red-500/20"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          ) : (
            <button
              type="button"
              onClick={onAnalyze}
              disabled={!targetNode.trim()}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-emerald-400 px-4 text-sm font-semibold text-zinc-950 shadow-[0_0_30px_-10px_rgba(52,211,153,0.8)] transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:bg-zinc-700 disabled:text-zinc-400 disabled:shadow-none"
            >
              {status === "complete" ? (
                <>
                  <Loader2 className="h-4 w-4" />
                  Re-analyze
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Analyze
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
