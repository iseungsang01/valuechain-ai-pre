"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, AlertTriangle } from "lucide-react";
import type { SupplyChainEdge } from "@/types";
import { SourceCitation } from "./SourceCitation";

interface EdgeDetailPanelProps {
  edge: SupplyChainEdge | null;
  onClose: () => void;
}

export function EdgeDetailPanel({ edge, onClose }: EdgeDetailPanelProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return (
    <AnimatePresence>
      {edge && (
        <motion.div
          initial={{ x: "100%", opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: "100%", opacity: 0 }}
          transition={{ type: "spring", damping: 25, stiffness: 200 }}
          role="dialog"
          aria-labelledby="edge-detail-title"
          className="col-start-1 row-start-1 justify-self-end z-40 w-80 h-full border-l border-white/10 bg-zinc-950/95 p-5 shadow-2xl backdrop-blur-xl rounded-r-2xl overflow-y-auto pointer-events-auto"
        >
          <div className="mb-6 flex items-start justify-between">
            <div>
              <h2 id="edge-detail-title" className="text-sm font-semibold text-zinc-100">
                Edge Details
              </h2>
              <p className="mt-1 text-xs text-zinc-400">
                {edge.source} <span className="text-zinc-500">→</span> {edge.target}
              </p>
            </div>
            <button
              onClick={onClose}
              className="rounded-md p-1 text-zinc-400 transition-colors hover:bg-white/10 hover:text-white"
              aria-label="Close panel"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-6">
            {/* Revenue Formula */}
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                Revenue Estimate
              </h3>
              {typeof edge.p_as_usd === "number" && typeof edge.q_units === "number" ? (
                <div className="rounded-lg border border-white/10 bg-white/5 p-3">
                  <div className="font-mono text-xs text-zinc-300">
                    <span className="text-emerald-400">${edge.p_as_usd.toLocaleString()}</span>
                    <span className="mx-1 text-zinc-500">×</span>
                    <span className="text-sky-400">{edge.q_units.toLocaleString()}</span>
                    <span className="mx-1 text-zinc-500">=</span>
                    <span className="font-semibold text-zinc-100">
                      {edge.estimated_revenue_krw.toLocaleString()} ₩
                    </span>
                  </div>
                </div>
              ) : (
                <div className="rounded-lg border border-white/10 bg-white/5 p-3 text-xs text-zinc-400">
                  Only <span className="font-mono text-zinc-300">{edge.estimated_revenue_krw.toLocaleString()} ₩</span> is available. P/Q breakdown missing.
                </div>
              )}
            </section>

            {/* Conflicts */}
            {edge.has_conflict && (
              <section>
                <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                  Status
                </h3>
                <div className="flex items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-400">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  <span>Conflict detected in feedback loop</span>
                </div>
              </section>
            )}

            {/* Citations */}
            <section>
              <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                Grounding Sources
              </h3>
              {edge.grounding_sources.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {edge.grounding_sources.map((source, idx) => (
                    <SourceCitation key={idx} source={source} index={idx + 1} />
                  ))}
                </div>
              ) : (
                <p className="text-xs text-zinc-500 italic">
                  No grounding yet — feedback loop will re-collect.
                </p>
              )}
            </section>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
