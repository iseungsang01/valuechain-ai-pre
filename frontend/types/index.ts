// MVContract: TypeScript interfaces matching backend/agents/models.py
// Keep this file aligned with the FastAPI backend's Pydantic models.

export type MetricType = "ASP" | "Q" | "REVENUE" | "COGS";

// Tier indicates source authority. UI uses it to colour-code citations and
// to dim FALLBACK rows; backend Evaluator/Estimator prefer higher tiers when
// resolving conflicts.
export type SourceTier =
  | "OFFICIAL_DISCLOSURE"
  | "OFFICIAL_IR"
  | "NEWS"
  | "FALLBACK";

export interface GroundingSource {
  metric_type: MetricType;
  target_quarter: string; // e.g. "2024-Q3"
  value: number;
  unit: string;
  source_name: string;
  url: string;
  extraction_date: string; // ISO date — when we fetched the page
  article_date?: string | null; // ISO date — publication date of the source
  tier?: SourceTier;
}

export type NodeType = "TARGET" | "SUPPLIER" | "CUSTOMER";

export interface SupplyChainNode {
  id: string;
  name: string;
  type: NodeType;
  reported_cogs_krw?: number | null;
  edges_out: string[];
  edges_in: string[];
}

export interface SupplyChainEdge {
  id: string;
  source: string;
  target: string;
  estimated_revenue_krw: number;
  p_as_usd?: number | null;
  q_units?: number | null;
  grounding_sources: GroundingSource[];
  has_conflict: boolean;
}

export interface SupplyChainGraph {
  target_quarter: string;
  nodes: SupplyChainNode[];
  edges: SupplyChainEdge[];
  conflict_nodes: string[];
}

export type ConflictType =
  | "COGS_EXCEEDED"
  | "MISSING_GROUNDING"
  | "DATA_CONFLICT"
  | "DOUBLE_ENTRY_MISMATCH"
  | "STALE_GROUNDING"
  | "PXQ_INCONSISTENT";

export interface ConflictDetail {
  type: ConflictType;
  message: string;
  target_edge_ids: string[];
  target_node_ids: string[];
}

// SSE Stream Events emitted by the backend's `/api/analyze` endpoint.
export type SSEEventType =
  | "COLLECTING"
  | "ESTIMATING"
  | "EVALUATING"
  | "FEEDBACK"
  | "RESULT";

// Granular progress sub-events the backend emits while a phase is running.
// Each carries `status: "progress"` plus an `event` discriminator.
export type ProgressSubEvent =
  | "network_start"
  | "node_start"
  | "tier_start"
  | "tier_done"
  | "activity"
  | "source_extracted"
  | "node_done"
  | "node_failed"
  | "network_done"
  | "recollect_start"
  | "heartbeat";

export interface ProgressPayload {
  status: "progress";
  event: ProgressSubEvent;
  // Optional contextual fields (presence depends on event type).
  node?: string;
  tier?: SourceTier | string;
  action?: string;
  query?: string;
  url?: string;
  metric?: MetricType;
  value?: number;
  unit?: string;
  source_name?: string;
  found?: number;
  sources_found?: number;
  total_sources?: number;
  total_nodes?: number;
  completed?: number;
  total?: number;
  count?: number;
  nodes?: string[];
  // For heartbeat
  label?: string;
  elapsed_seconds?: number;
  error?: string;
}

export interface CollectingEventData {
  status: "in_progress" | "complete" | "progress";
  message?: string;
  sources_count?: number;
  suppliers?: string[];
  customers?: string[];
  elapsed_seconds?: number;
  // Progress sub-event payload (when status === "progress")
  event?: ProgressSubEvent;
  node?: string;
  tier?: string;
  action?: string;
  url?: string;
  metric?: MetricType;
  value?: number;
  unit?: string;
  source_name?: string;
  found?: number;
  sources_found?: number;
  total_sources?: number;
  total_nodes?: number;
  completed?: number;
  total?: number;
  count?: number;
  nodes?: string[];
  label?: string;
  error?: string;
}

export interface EstimatingEventData {
  status: "in_progress" | "complete" | "progress";
  message?: string;
  sources_count?: number;
  edges_count?: number;
  nodes_count?: number;
  elapsed_seconds?: number;
  attempt?: number;
  event?: ProgressSubEvent;
  label?: string;
}

export interface EvaluatingEventData {
  status: "in_progress" | "complete" | "progress";
  message?: string;
  attempt?: number;
  elapsed_seconds?: number;
  event?: ProgressSubEvent;
  label?: string;
}

export interface FeedbackEventData {
  status: "in_progress" | "complete" | "progress";
  conflicts_count?: number;
  conflicts?: ConflictDetail[];
  feedback?: string | null;
  // Set when the orchestrator re-collected grounding sources between
  // regeneration passes (SPEC § 2.3 macro feedback loop).
  recollected_sources_count?: number;
  message?: string;
  attempt?: number;
  elapsed_seconds?: number;
  // Progress sub-event payload (when status === "progress")
  event?: ProgressSubEvent;
  node?: string;
  tier?: string;
  action?: string;
  url?: string;
  metric?: MetricType;
  value?: number;
  unit?: string;
  source_name?: string;
  found?: number;
  sources_found?: number;
  completed?: number;
  total?: number;
  label?: string;
  error?: string;
}

// Backend emits the entire SupplyChainGraph as the RESULT payload.
export type ResultEventData = SupplyChainGraph;

// Discriminated union covering every event the UI must handle.
export type SSEEvent =
  | { event: "COLLECTING"; data: CollectingEventData }
  | { event: "ESTIMATING"; data: EstimatingEventData }
  | { event: "EVALUATING"; data: EvaluatingEventData }
  | { event: "FEEDBACK"; data: FeedbackEventData }
  | { event: "RESULT"; data: ResultEventData };

// UI-side log entry rendered in the Agent Thought Process panel.
export type LogLevel = "info" | "warning" | "error" | "success";

export interface AgentLogEntry {
  id: string;
  timestamp: number;
  event: SSEEventType;
  level: LogLevel;
  message: string;
  // When set, this entry is a granular progress event rather than a milestone.
  // Frontend dims them and groups them under their parent phase.
  isProgress?: boolean;
  // For source_extracted events: lets the UI link to the citation.
  url?: string;
  // For node-scoped progress, lets the UI badge the entry by company.
  node?: string;
}

// Latest "what is the agent doing right now" snapshot — drives the live
// activity banner above the log so the user always sees motion.
export interface CurrentActivity {
  phase: SSEEventType;
  label: string;
  detail?: string;
  node?: string;
  // Per-phase progress: e.g. 3 of 6 nodes done.
  completed?: number;
  total?: number;
  // For heartbeat-style updates, seconds since the phase started.
  elapsedSeconds?: number;
  startedAt: number;
}
