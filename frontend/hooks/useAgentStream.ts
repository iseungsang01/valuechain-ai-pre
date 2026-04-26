"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type {
  AgentLogEntry,
  CollectingEventData,
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
): AgentLogEntry => ({
  id: nextLogId(),
  timestamp: Date.now(),
  event,
  level,
  message,
});

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

  const abortControllerRef = useRef<AbortController | null>(null);

  const appendLog = useCallback((entry: AgentLogEntry) => {
    setLogs((prev) => [...prev, entry]);
  }, []);

  const handleEvent = useCallback(
    (eventName: string, dataRaw: string) => {
      const eventType = eventName as SSEEventType;
      switch (eventType) {
        case "COLLECTING": {
          const data = safeParse<CollectingEventData>(dataRaw);
          if (!data) return;
          if (data.status === "in_progress") {
            appendLog(
              buildLog(
                "COLLECTING",
                data.message ?? "Collecting time-bound grounding sources...",
              ),
            );
          } else {
            appendLog(
              buildLog(
                "COLLECTING",
                `Collected ${data.sources_count ?? 0} grounding sources.`,
                "success",
              ),
            );
          }
          break;
        }
        case "ESTIMATING": {
          const data = safeParse<EstimatingEventData>(dataRaw);
          if (!data) return;
          appendLog(
            buildLog(
              "ESTIMATING",
              data.message ??
                (data.status === "in_progress"
                  ? "Synthesizing PxQ supply chain network..."
                  : "Initial estimation complete."),
              data.status === "complete" ? "success" : "info",
            ),
          );
          break;
        }
        case "EVALUATING": {
          const data = safeParse<EvaluatingEventData>(dataRaw);
          if (!data) return;
          appendLog(
            buildLog(
              "EVALUATING",
              data.message ??
                (data.status === "in_progress"
                  ? "Evaluating network consistency & self-reflection..."
                  : "Network consistency check complete."),
              data.status === "complete" ? "success" : "info",
            ),
          );
          break;
        }
        case "FEEDBACK": {
          const data = safeParse<FeedbackEventData>(dataRaw);
          if (!data) return;
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
          setStatus("complete");
          break;
        }
        default:
          // Ignore unknown event types but keep the stream alive.
          break;
      }
    },
    [appendLog],
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

  return { status, logs, graph, error, start, stop, reset };
}
