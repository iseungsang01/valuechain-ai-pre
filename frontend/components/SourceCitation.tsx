"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import type { GroundingSource } from "@/types";

const tierColors = {
  OFFICIAL_DISCLOSURE: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  OFFICIAL_IR: "bg-sky-500/20 text-sky-400 border-sky-500/30",
  NEWS: "bg-zinc-500/20 text-zinc-400 border-zinc-500/30",
  FALLBACK: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

interface SourceCitationProps {
  source: GroundingSource;
  index: number;
}

export function SourceCitation({ source, index }: SourceCitationProps) {
  const [isOpen, setIsOpen] = useState(false);
  const tier = source.tier || "FALLBACK";
  const date = source.article_date || source.extraction_date;

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        aria-pressed={isOpen}
        aria-describedby={`citation-tooltip-${index}`}
        className="inline-flex h-5 items-center justify-center rounded bg-zinc-800 px-1.5 text-[10px] font-medium text-zinc-300 transition-colors hover:bg-zinc-700 hover:text-white focus:outline-none focus:ring-2 focus:ring-emerald-400/50"
      >
        [{index}]
      </button>

      {isOpen && (
        <div
          id={`citation-tooltip-${index}`}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-50 mb-2 w-64 -translate-x-1/2 rounded-lg border border-white/10 bg-zinc-900 p-3 shadow-xl"
        >
          <div className="mb-2 flex items-start justify-between gap-2">
            <span className="font-medium text-zinc-100 line-clamp-2 text-xs">
              {source.source_name}
            </span>
            <span
              className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${tierColors[tier]}`}
            >
              {tier.replace("_", " ")}
            </span>
          </div>
          
          <div className="mb-2 text-[10px] text-zinc-400">
            {date && <div>Date: {date.split("T")[0]}</div>}
            <div className="mt-1 font-mono text-zinc-300">
              {source.metric_type}: {source.value.toLocaleString()} {source.unit}
            </div>
          </div>

          {source.url && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[10px] text-emerald-400 hover:text-emerald-300 hover:underline"
            >
              <ExternalLink className="h-3 w-3" />
              View Source
            </a>
          )}
        </div>
      )}
    </div>
  );
}
