"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, AlertTriangle, CheckCircle2, Database, Eye, Sparkles, ChevronRight } from "lucide-react";
import type { AgentLogEntry, CurrentActivity, SSEEventType } from "@/types";

interface ThoughtLogProps {
  logs: AgentLogEntry[];
  isStreaming: boolean;
  activity?: CurrentActivity | null;
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

export function ThoughtLog({ logs, isStreaming, activity }: ThoughtLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [now, setNow] = useState(() => Date.now());

  // Force re-render every second to update "elapsed" in the banner.
  useEffect(() => {
    if (!isStreaming) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [isStreaming]);

  // Auto-scroll to the latest log entry whenever the list grows.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [logs.length, activity]);

  const grouped = useMemo(() => logs, [logs]);

  // Banner elapsed time formatting
  const getElapsedStr = () => {
    if (!activity) return "";
    const ms = now - activity.startedAt;
    return ` · ${Math.floor(ms / 1000)}s`;
  };

  return (
    <aside
      aria-label="Agent thought process log"
      className="flex h-full w-full flex-col overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/70 backdrop-blur"
    >
      <header className="flex flex-col border-b border-white/10 bg-zinc-900/40">
        <div className="flex items-center justify-between px-5 py-4">
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
        </div>

        {/* Live Activity Banner */}
        <AnimatePresence>
          {isStreaming && activity && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-white/5 bg-zinc-950/50"
            >
              <div className="flex items-center gap-3 px-5 py-3">
                {(() => {
                  const Icon = eventMeta[activity.phase].icon;
                  const color = eventMeta[activity.phase].color;
                  return <Icon className={`h-4 w-4 animate-pulse ${color}`} />;
                })()}
                <div className="flex flex-1 flex-col gap-0.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium uppercase tracking-wider text-zinc-300">
                      {activity.label}
                      {getElapsedStr()}
                    </span>
                    {activity.total != null && activity.completed != null && (
                      <span className="text-xs text-zinc-500">
                        {activity.completed} / {activity.total}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-zinc-100/90 truncate">
                    {activity.detail}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
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
          <ol className="space-y-2">
            <AnimatePresence initial={false}>
              {grouped.map((log) => {
                const meta = eventMeta[log.event];
                const Icon = meta.icon;

                // Render progress sub-events compactly
                if (log.isProgress) {
                  return (
                    <motion.li
                      key={log.id}
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      className="ml-6 pl-3 border-l border-white/10 text-xs text-zinc-400 py-1"
                    >
                      <div className="flex items-start gap-2">
                        <ChevronRight className="h-3.5 w-3.5 shrink-0 text-zinc-600 mt-0.5" />
                        <div className="flex flex-col gap-0.5">
                          <span>{log.message}</span>
                          {log.url && (
                            <a
                              href={log.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[10px] text-zinc-500 hover:text-sky-400 truncate max-w-[280px] sm:max-w-xs transition-colors"
                            >
                              {log.url}
                            </a>
                          )}
                        </div>
                      </div>
                    </motion.li>
                  );
                }

                // Render main milestone events
                return (
                  <motion.li
                    key={log.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`rounded-xl border px-3 py-2.5 text-sm ${levelStyle[log.level]} mt-4 first:mt-0`}
                  >
                    <div className="mb-1.5 flex items-center justify-between text-xs">
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
                    <p className="text-zinc-200/95 leading-relaxed font-medium">
                      {log.message}
                    </p>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ol>
        )}
        <div ref={bottomRef} className="h-4" />
      </div>
    </aside>
  );
}
