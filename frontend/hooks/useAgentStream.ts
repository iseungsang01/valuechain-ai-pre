"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentLogEntry,
  CollectingEventData,
  CurrentActivity,
  EstimatingEventData,
  EvaluatingEventData,
  FeedbackEventData,
  ResultEventData,
  SSEEventType,
  SupplyChainGraph,
} from "@/types";

const BACKEND_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type AnalysisStatus =
  | "idle"
  | "connecting"
  | "streaming"
  | "complete"
  | "error";

export interface UseAgentStreamReturn {
  status: AnalysisStatus;
  logs: AgentLogEntry[];
  graph: SupplyChainGraph | null;
  error: string | null;
  activity: CurrentActivity | null;
  start: (params: { targetNode: string; targetQuarter: string }) => void;
  stop: () => void;
  reset: () => void;
}

let logCounter = 0;
const nextLogId = () => `log_${Date.now()}_${++logCounter}`;

const buildLog = (
  event: SSEEventType,
  message: string,
  level: AgentLogEntry["level"] = "info",
  extras?: Partial<AgentLogEntry>,
): AgentLogEntry => ({
  id: nextLogId(),
  timestamp: Date.now(),
  event,
  level,
  message,
  ...(extras ?? {}),
});

/** Compact human-readable description for a granular progress sub-event. */
function describeProgress(
  phase: SSEEventType,
  data: CollectingEventData | FeedbackEventData | EstimatingEventData | EvaluatingEventData,
): { detail: string; logMessage?: string; level?: AgentLogEntry["level"] } {
  const subEvent = (data as { event?: string }).event;
  const node = (data as { node?: string }).node;
  switch (subEvent) {
    case "network_start":
      return {
        detail: `${(data as { total_nodes?: number }).total_nodes ?? 0}개 노드 수집 시작`,
        logMessage: `Network: ${(data as { nodes?: string[] }).nodes?.join(", ") ?? ""}`,
      };
    case "node_start":
      return { detail: `${node} 데이터 수집 중` };
    case "tier_start": {
      const tier = (data as { tier?: string }).tier;
      return { detail: `${node} · ${tier} 검색 중` };
    }
    case "tier_done": {
      const tier = (data as { tier?: string }).tier;
      const found = (data as { found?: number }).found ?? 0;
      return { detail: `${node} · ${tier} → ${found}건` };
    }
    case "activity": {
      const action = (data as { action?: string }).action ?? "";
      return { detail: `${node ? node + " · " : ""}${action}` };
    }
    case "source_extracted": {
      const metric = (data as { metric?: string }).metric;
      const value = (data as { value?: number }).value;
      const unit = (data as { unit?: string }).unit ?? "";
      const sourceName = (data as { source_name?: string }).source_name ?? "";
      const url = (data as { url?: string }).url;
      return {
        detail: `${node} · ${metric}=${value}${unit ? " " + unit : ""}`,
        logMessage: `📑 ${node} ${metric}=${value}${unit ? " " + unit : ""} ← ${sourceName}`,
        level: "success",
      };
    }
    case "node_done": {
      const found = (data as { sources_found?: number }).sources_found ?? 0;
      const completed = (data as { completed?: number }).completed;
      const total = (data as { total?: number }).total;
      return {
        detail: `✓ ${node} 완료 (${found}건)${completed && total ? ` · ${completed}/${total}` : ""}`,
        logMessage: `✓ ${node}: ${found} source(s) collected${completed && total ? ` (${completed}/${total} nodes done)` : ""}`,
        level: found > 0 ? "success" : "info",
      };
    }
    case "node_failed": {
      const completed = (data as { completed?: number }).completed;
      const total = (data as { total?: number }).total;
      const err = (data as { error?: string }).error;
      return {
        detail: `✗ ${node} 실패`,
        logMessage: `✗ ${node} failed${err ? `: ${err}` : ""}${completed && total ? ` (${completed}/${total})` : ""}`,
        level: "warning",
      };
    }
    case "network_done": {
      const totalSources = (data as { total_sources?: number }).total_sources ?? 0;
      const totalNodes = (data as { total_nodes?: number }).total_nodes ?? 0;
      return {
        detail: `네트워크 수집 완료: ${totalSources}건 (${totalNodes}개 노드)`,
        logMessage: `Network collection done: ${totalSources} source(s) across ${totalNodes} node(s).`,
        level: "success",
      };
    }
    case "recollect_start": {
      const totalNodes = (data as { total_nodes?: number }).total_nodes ?? 0;
      return {
        detail: `${totalNodes}개 노드 재수집 중`,
        logMessage: `Re-collecting grounding for ${totalNodes} node(s)...`,
        level: "warning",
      };
    }
    case "heartbeat": {
      const label = (data as { label?: string }).label ?? "thinking";
      const elapsed = (data as { elapsed_seconds?: number }).elapsed_seconds;
      return { detail: `${label}${elapsed != null ? ` · ${elapsed}s` : ""}` };
    }
    default:
      return { detail: phase + " 진행 중" };
  }
}

const safeParse = <T,>(raw: string): T | null => {
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
};

/**
 * SSE-style hook for the ValueChain AI multi-agent pipeline.
 *
 * The backend's `/api/analyze` endpoint is a POST endpoint that streams Server-Sent
 * Events. The native EventSource API only supports GET, so we use `fetch` + a
 * ReadableStream reader to parse SSE frames manually.
 */
export function useAgentStream(): UseAgentStreamReturn {
  const [status, setStatus] = useState<AnalysisStatus>("idle");
  const [logs, setLogs] = useState<AgentLogEntry[]>([]);
  const [graph, setGraph] = useState<SupplyChainGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activity, setActivity] = useState<CurrentActivity | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  // Tracks when each phase started so heartbeats can show elapsed seconds
  // without backend round-trips.
  const phaseStartedAtRef = useRef<Partial<Record<SSEEventType, number>>>({});

  const appendLog = useCallback((entry: AgentLogEntry) => {
    setLogs((prev) => [...prev, entry]);
  }, []);

  const updateActivity = useCallback(
    (phase: SSEEventType, label: string, detail?: string, extras?: Partial<CurrentActivity>) => {
      const startedAt = phaseStartedAtRef.current[phase] ?? Date.now();
      phaseStartedAtRef.current[phase] = startedAt;
      setActivity({
        phase,
        label,
        detail,
        startedAt,
        ...extras,
      });
    },
    [],
  );

  const handleEvent = useCallback(
    (eventName: string, dataRaw: string) => {
      const eventType = eventName as SSEEventType;
      switch (eventType) {
        case "COLLECTING": {
          const data = safeParse<CollectingEventData>(dataRaw);
          if (!data) return;
          if (data.status === "in_progress") {
            phaseStartedAtRef.current["COLLECTING"] = Date.now();
            updateActivity("COLLECTING", "Data Collector", data.message ?? "Collecting...");
            appendLog(
              buildLog(
                "COLLECTING",
                data.message ?? "Collecting time-bound grounding sources...",
              ),
            );
          } else if (data.status === "progress") {
            const { detail, logMessage, level } = describeProgress("COLLECTING", data);
            updateActivity("COLLECTING", "Data Collector", detail, {
              node: data.node,
              completed: data.completed,
              total: data.total,
            });
            if (logMessage) {
              appendLog(
                buildLog("COLLECTING", logMessage, level ?? "info", {
                  isProgress: true,
                  url: data.url,
                  node: data.node,
                }),
              );
            }
          } else {
            const elapsed = data.elapsed_seconds;
            appendLog(
              buildLog(
                "COLLECTING",
                `Collected ${data.sources_count ?? 0} grounding sources${elapsed != null ? ` in ${elapsed}s` : ""}.`,
                "success",
              ),
            );
          }
          break;
        }
        case "ESTIMATING": {
          const data = safeParse<EstimatingEventData>(dataRaw);
          if (!data) return;
          if (data.status === "progress") {
            const { detail } = describeProgress("ESTIMATING", data);
            updateActivity("ESTIMATING", "Estimator", detail, {
              elapsedSeconds: data.elapsed_seconds,
            });
          } else if (data.status === "in_progress") {
            phaseStartedAtRef.current["ESTIMATING"] = Date.now();
            updateActivity(
              "ESTIMATING",
              "Estimator",
              data.message ?? "Synthesizing PxQ supply chain network...",
            );
            appendLog(
              buildLog(
                "ESTIMATING",
                data.message ?? "Synthesizing PxQ supply chain network...",
              ),
            );
          } else {
            const elapsed = data.elapsed_seconds;
            const edges = data.edges_count;
            const nodes = data.nodes_count;
            const summary = [
              "Estimation complete",
              edges != null && nodes != null ? `(${nodes} nodes, ${edges} edges)` : null,
              elapsed != null ? `in ${elapsed}s` : null,
            ]
              .filter(Boolean)
              .join(" ");
            appendLog(buildLog("ESTIMATING", summary + ".", "success"));
          }
          break;
        }
        case "EVALUATING": {
          const data = safeParse<EvaluatingEventData>(dataRaw);
          if (!data) return;
          if (data.status === "progress") {
            const { detail } = describeProgress("EVALUATING", data);
            updateActivity("EVALUATING", "Evaluator", detail, {
              elapsedSeconds: data.elapsed_seconds,
            });
          } else if (data.status === "in_progress") {
            phaseStartedAtRef.current["EVALUATING"] = Date.now();
            updateActivity(
              "EVALUATING",
              "Evaluator",
              data.message ?? "Evaluating network consistency...",
            );
            appendLog(
              buildLog(
                "EVALUATING",
                data.message ?? "Evaluating network consistency & self-reflection...",
              ),
            );
          } else {
            const elapsed = data.elapsed_seconds;
            appendLog(
              buildLog(
                "EVALUATING",
                `${data.message ?? "Evaluation complete"}${elapsed != null ? ` (${elapsed}s)` : ""}`,
                "success",
              ),
            );
          }
          break;
        }
        case "FEEDBACK": {
          const data = safeParse<FeedbackEventData>(dataRaw);
          if (!data) return;
          if (data.status === "progress") {
            const { detail, logMessage, level } = describeProgress("FEEDBACK", data);
            updateActivity("FEEDBACK", "Feedback Loop", detail, {
              node: data.node,
              completed: data.completed,
              total: data.total,
            });
            if (logMessage) {
              appendLog(
                buildLog("FEEDBACK", logMessage, level ?? "warning", {
                  isProgress: true,
                  url: data.url,
                  node: data.node,
                }),
              );
            }
            break;
          }
          // Non-progress FEEDBACK: either conflict report or recollection summary.
          if (typeof data.conflicts_count === "number") {
            appendLog(
              buildLog(
                "FEEDBACK",
                `${data.conflicts_count} conflict(s) detected. Triggering feedback loop...`,
                "warning",
              ),
            );
            for (const conflict of data.conflicts ?? []) {
              appendLog(
                buildLog(
                  "FEEDBACK",
                  `[${conflict.type}] ${conflict.message}`,
                  "warning",
                ),
              );
            }
            if (data.feedback) {
              appendLog(buildLog("FEEDBACK", `> ${data.feedback}`, "warning"));
            }
          }
          if (typeof data.recollected_sources_count === "number" && data.message) {
            appendLog(buildLog("FEEDBACK", data.message, "info"));
          }
          break;
        }
        case "RESULT": {
          const data = safeParse<ResultEventData>(dataRaw);
          if (!data) return;
          setGraph(data);
          appendLog(
            buildLog(
              "RESULT",
              `Final graph rendered (${data.nodes.length} nodes, ${data.edges.length} edges).`,
              "success",
            ),
          );
          setActivity(null);
          setStatus("complete");
          break;
        }
        default:
          // Ignore unknown event types but keep the stream alive.
          break;
      }
    },
    [appendLog, updateActivity],
  );

  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
  }, []);

  const reset = useCallback(() => {
    stop();
    setStatus("idle");
    setLogs([]);
    setGraph(null);
    setError(null);
    setActivity(null);
  }, [stop]);

  const start = useCallback(
    async ({
      targetNode,
      targetQuarter,
    }: {
      targetNode: string;
      targetQuarter: string;
    }) => {
      // Cancel any in-flight stream before starting a new one.
      stop();
      setLogs([]);
      setGraph(null);
      setError(null);
      setActivity(null);
      phaseStartedAtRef.current = {};
      setStatus("connecting");

      const controller = new AbortController();
      abortControllerRef.current = controller;

      try {
        const response = await fetch(`${BACKEND_BASE_URL}/api/analyze`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
          },
          body: JSON.stringify({
            target_node: targetNode,
            target_quarter: targetQuarter,
          }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          throw new Error(
            `Backend returned ${response.status} ${response.statusText}`,
          );
        }

        setStatus("streaming");
        appendLog(
          buildLog(
            "COLLECTING",
            `Connected to backend pipeline for ${targetNode} (${targetQuarter}).`,
          ),
        );

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // SSE frames are separated by a blank line (\n\n).
          let separatorIndex: number;
          while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
            const frame = buffer.slice(0, separatorIndex);
            buffer = buffer.slice(separatorIndex + 2);

            let eventName = "message";
            const dataLines: string[] = [];

            for (const rawLine of frame.split("\n")) {
              const line = rawLine.replace(/\r$/, "");
              if (!line || line.startsWith(":")) continue;
              if (line.startsWith("event:")) {
                eventName = line.slice("event:".length).trim();
              } else if (line.startsWith("data:")) {
                dataLines.push(line.slice("data:".length).trim());
              }
            }

            if (dataLines.length > 0) {
              handleEvent(eventName, dataLines.join("\n"));
            }
          }
        }

        // If the stream closed without a RESULT event, flag completion gracefully.
        setStatus((current) => (current === "complete" ? current : "complete"));
      } catch (err) {
        if (controller.signal.aborted) {
          // User-initiated stop; do not surface as error.
          return;
        }
        const message =
          err instanceof Error ? err.message : "Unknown SSE failure";
        setError(message);
        setStatus("error");
        appendLog(buildLog("FEEDBACK", `Connection error: ${message}`, "error"));
      } finally {
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      }
    },
    [appendLog, handleEvent, stop],
  );

  // Cleanup on unmount.
  useEffect(() => () => stop(), [stop]);

  return { status, logs, activity, graph, error, start, stop, reset };
}
