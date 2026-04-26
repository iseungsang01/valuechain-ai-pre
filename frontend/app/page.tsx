"use client";

import { useState } from "react";
import { ControlBar } from "@/components/ControlBar";
import { SupplyChainGraph } from "@/components/SupplyChainGraph";
import { ThoughtLog } from "@/components/ThoughtLog";
import { EdgeDetailPanel } from "@/components/EdgeDetailPanel";
import { useAgentStream } from "@/hooks/useAgentStream";

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"] as const;

export default function Home() {
  const [targetNode, setTargetNode] = useState("SK Hynix");
  const [year, setYear] = useState(2024);
  const [quarter, setQuarter] = useState<string>("Q3");
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const { status, logs, activity, graph, error, start, stop } = useAgentStream();

  const selectedQuarter = `${year}-${quarter}`;
  const isStreaming = status === "connecting" || status === "streaming";
  const selectedEdge = graph?.edges.find(e => e.id === selectedEdgeId) ?? null;

  return (
    <main className="flex h-screen w-full flex-col gap-4 px-6 py-5">
      <ControlBar
        quarters={[...QUARTERS]}
        year={year}
        onYearChange={setYear}
        selectedQuarter={quarter}
        onQuarterChange={setQuarter}
        targetNode={targetNode}
        onTargetNodeChange={setTargetNode}
        status={status}
        onAnalyze={() =>
          start({ targetNode: targetNode.trim(), targetQuarter: selectedQuarter })
        }
        onStop={stop}
      />

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          <strong className="font-semibold">Connection error:</strong> {error}
          {" "}— make sure the FastAPI backend is running at the configured base
          URL ({process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}).
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
        <SupplyChainGraph 
          graph={graph} 
          isLoading={isStreaming} 
          selectedEdgeId={selectedEdgeId}
          onEdgeClick={setSelectedEdgeId}
        />
        <ThoughtLog logs={logs} isStreaming={isStreaming} activity={activity} />
        <div className="col-start-1 row-start-1 relative pointer-events-none overflow-hidden rounded-2xl">
          <EdgeDetailPanel edge={selectedEdge} onClose={() => setSelectedEdgeId(null)} />
        </div>
      </div>

      <footer className="text-center text-xs text-zinc-500">
        Quarter <span className="text-zinc-300">{selectedQuarter}</span> · Pipeline:
        Data Collector → Estimator → Evaluator → Feedback Loop · Network
        consistency enforced via double-entry edges.
      </footer>
    </main>
  );
}
