"use client";

import { useEffect, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, AlertTriangle, CheckCircle2, Database, Eye, Sparkles } from "lucide-react";
import type { AgentLogEntry, SSEEventType } from "@/types";

interface ThoughtLogProps {
  logs: AgentLogEntry[];
  isStreaming: boolean;
}

const eventMeta: Record<
  SSEEventType,
  { label: string; icon: typeof Activity; color: string }
> = {
  COLLECTING: {
    label: "Data Collector",
    icon: Database,
    color: "text-sky-300",
  },
  ESTIMATING: {
    label: "Estimator",
    icon: Sparkles,
    color: "text-violet-300",
  },
  EVALUATING: {
    label: "Evaluator",
    icon: Eye,
    color: "text-emerald-300",
  },
  FEEDBACK: {
    label: "Feedback Loop",
    icon: AlertTriangle,
    color: "text-amber-300",
  },
  RESULT: {
    label: "Final Result",
    icon: CheckCircle2,
    color: "text-emerald-400",
  },
};

const levelStyle: Record<AgentLogEntry["level"], string> = {
  info: "border-white/10 bg-white/5",
  warning: "border-amber-500/40 bg-amber-500/10",
  error: "border-red-500/50 bg-red-500/10",
  success: "border-emerald-500/40 bg-emerald-500/10",
};

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp);
  return date.toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

export function ThoughtLog({ logs, isStreaming }: ThoughtLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the latest log entry whenever the list grows.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [logs.length]);

  const grouped = useMemo(() => logs, [logs]);

  return (
    <aside
      aria-label="Agent thought process log"
      className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/70 backdrop-blur"
    >
      <header className="flex items-center justify-between border-b border-white/10 px-5 py-4">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-emerald-400" />
          <h2 className="text-sm font-semibold tracking-wide text-zinc-100">
            Agent Thought Process
          </h2>
        </div>
        <span
          className={`flex items-center gap-2 text-xs ${
            isStreaming ? "text-emerald-400" : "text-zinc-500"
          }`}
        >
          <span
            className={`h-2 w-2 rounded-full ${
              isStreaming ? "animate-pulse bg-emerald-400" : "bg-zinc-600"
            }`}
          />
          {isStreaming ? "Live" : "Idle"}
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {grouped.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-zinc-500">
            <Sparkles className="h-6 w-6 text-zinc-600" />
            <p>
              Run an analysis to see the multi-agent reasoning trace appear in
              real time.
            </p>
          </div>
        ) : (
          <ol className="space-y-3">
            <AnimatePresence initial={false}>
              {grouped.map((log) => {
                const meta = eventMeta[log.event];
                const Icon = meta.icon;
                return (
                  <motion.li
                    key={log.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className={`rounded-xl border px-3 py-2 text-sm ${levelStyle[log.level]}`}
                  >
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <div className={`flex items-center gap-1.5 ${meta.color}`}>
                        <Icon className="h-3.5 w-3.5" />
                        <span className="font-medium uppercase tracking-wider">
                          {meta.label}
                        </span>
                      </div>
                      <time className="text-zinc-500" dateTime={new Date(log.timestamp).toISOString()}>
                        {formatTime(log.timestamp)}
                      </time>
                    </div>
                    <p className="text-zinc-200/90 leading-relaxed">
                      {log.message}
                    </p>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ol>
        )}
        <div ref={bottomRef} />
      </div>
    </aside>
  );
}
