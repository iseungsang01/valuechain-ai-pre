"use client";

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
  const tier = source.tier || "FALLBACK";
  const date = source.article_date || source.extraction_date;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-white/10 bg-white/5 p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2">
          <span className="text-xs font-mono text-zinc-500 mt-0.5 shrink-0">[{index}]</span>
          <span className="text-xs font-medium text-zinc-200 break-words">
            {source.source_name}
          </span>
        </div>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider ${tierColors[tier]}`}
        >
          {tier.replace("_", " ")}
        </span>
      </div>
      
      <div className="ml-6 flex flex-col gap-1.5">
        <div className="text-[10px] text-zinc-400">
          {date && <span>{date.split("T")[0]} • </span>}
          <span className="font-mono text-zinc-300">
            {source.metric_type}: {source.value.toLocaleString()} {source.unit}
          </span>
        </div>

        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-[10px] text-emerald-400 hover:text-emerald-300 hover:underline w-fit"
          >
            <ExternalLink className="h-3 w-3 shrink-0" />
            <span className="break-all line-clamp-1 hover:line-clamp-none">{source.url}</span>
          </a>
        )}
      </div>
    </div>
  );
}
