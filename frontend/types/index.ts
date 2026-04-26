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

export interface CollectingEventData {
  status: "in_progress" | "complete";
  message?: string;
  sources_count?: number;
}

export interface EstimatingEventData {
  status: "in_progress" | "complete";
  message?: string;
}

export interface EvaluatingEventData {
  status: "in_progress" | "complete";
  message?: string;
}

export interface FeedbackEventData {
  status: "in_progress" | "complete";
  conflicts_count?: number;
  conflicts?: ConflictDetail[];
  feedback?: string | null;
  // Set when the orchestrator re-collected grounding sources between
  // regeneration passes (SPEC § 2.3 macro feedback loop).
  recollected_sources_count?: number;
  message?: string;
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
}
