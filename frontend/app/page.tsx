"use client";

import { useState } from "react";
import { ControlBar } from "@/components/ControlBar";
import { SupplyChainGraph } from "@/components/SupplyChainGraph";
import { ThoughtLog } from "@/components/ThoughtLog";
import { EdgeDetailPanel } from "@/components/EdgeDetailPanel";
import { useAgentStream } from "@/hooks/useAgentStream";

const QUARTERS = ["Q1", "Q2", "Q3", "Q4"] as const;

export default function Home() {
  const [targetNode, setTargetNode] = useState("SK하이닉스");
  const [year, setYear] = useState(2025);
  const [quarter, setQuarter] = useState<string>("Q1");
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [showThoughtLog, setShowThoughtLog] = useState(true);
  const { status, logs, activity, graph, error, start, stop } = useAgentStream();

  const selectedQuarter = `${year}-${quarter}`;
  const isStreaming = status === "connecting" || status === "streaming";
  
  const activeEdgeId = hoveredEdgeId ?? selectedEdgeId;
  const activeEdge = graph?.edges.find(e => e.id === activeEdgeId) ?? null;

  return (
    <main className="flex h-screen w-full flex-col gap-4 px-6 py-5 overflow-hidden">
      <ControlBar
        quarters={[...QUARTERS]}
        year={year}
        onYearChange={setYear}
        selectedQuarter={quarter}
        onQuarterChange={setQuarter}
        targetNode={targetNode}
        onTargetNodeChange={setTargetNode}
        status={status}
        onAnalyze={() => {
          setShowThoughtLog(true);
          start({ targetNode: targetNode.trim(), targetQuarter: selectedQuarter });
        }}
        onStop={stop}
      />

      {error && (
        <div className="z-50 rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          <strong className="font-semibold">Connection error:</strong> {error}
          {" "}— make sure the FastAPI backend is running at the configured base
          URL ({process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}).
        </div>
      )}

      <div className="relative flex-1 min-h-0 w-full overflow-hidden">
        <SupplyChainGraph 
          graph={graph} 
          isLoading={isStreaming} 
          selectedEdgeId={selectedEdgeId}
          onEdgeClick={(id) => setSelectedEdgeId(prev => prev === id ? null : id)}
          onEdgeHover={setHoveredEdgeId}
        />

        {/* Thought Log as a floating popup on the bottom left */}
        <div className={`absolute bottom-4 left-4 z-50 transition-all duration-300 ${showThoughtLog ? 'w-[400px] h-[500px] opacity-100' : 'w-auto h-auto opacity-80'}`}>
          {showThoughtLog ? (
            <div className="relative w-full h-full shadow-2xl">
              <ThoughtLog logs={logs} isStreaming={isStreaming} activity={activity} />
              <button 
                onClick={() => setShowThoughtLog(false)}
                className="absolute top-3 right-3 text-zinc-400 hover:text-white bg-zinc-800 rounded-md p-1"
                aria-label="Hide thought log"
              >
                Hide
              </button>
            </div>
          ) : (
            <button
              onClick={() => setShowThoughtLog(true)}
              className="bg-zinc-800 text-sm font-medium border border-white/10 shadow-lg text-white px-4 py-2 rounded-full flex items-center gap-2 hover:bg-zinc-700 transition"
            >
              <span className={`w-2 h-2 rounded-full ${isStreaming ? 'animate-pulse bg-emerald-400' : 'bg-zinc-500'}`} />
              Agent Status
            </button>
          )}
        </div>

        {/* Edge Detail Panel on the right */}
        <EdgeDetailPanel edge={activeEdge} onClose={() => {
          setSelectedEdgeId(null);
          setHoveredEdgeId(null);
        }} />
      </div>
    </main>
  );
}
