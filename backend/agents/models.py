from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Literal
from datetime import date


# Tier indicates the authority of a grounding source. The Evaluator and the UI
# use this to prefer official disclosures over generic news, and to clearly
# flag rows that came from a deterministic offline fallback.
SourceTier = Literal["OFFICIAL_DISCLOSURE", "OFFICIAL_IR", "NEWS", "FALLBACK"]


class GroundingSource(BaseModel):
    metric_type: Literal["ASP", "Q", "REVENUE", "COGS"]
    target_quarter: str  # "2024-Q3"
    value: float
    unit: str  # "USD", "KRW", "Units"
    source_name: str
    url: HttpUrl
    # `extraction_date` is when *we* fetched the page. `article_date` is when
    # the underlying article / filing was published. SPEC § 2.3.1 freshness is
    # anchored on the article date so we never treat a freshly scraped 2-year
    # old article as fresh.
    extraction_date: date
    article_date: Optional[date] = None
    tier: SourceTier = "NEWS"


class Edge(BaseModel):
    id: str  # "A-B"
    source: str  # Company ID A
    target: str  # Company ID B
    estimated_revenue_krw: float
    p_as_usd: Optional[float] = None
    q_units: Optional[float] = None
    grounding_sources: List[GroundingSource] = []
    has_conflict: bool = False


class Node(BaseModel):
    id: str  # "한미반도체"
    name: str
    type: Literal["TARGET", "SUPPLIER", "CUSTOMER"]
    reported_cogs_krw: Optional[float] = None  # Evaluator uses this
    edges_out: List[str] = []  # List of edge IDs
    edges_in: List[str] = []


class SupplyChainGraph(BaseModel):
    target_quarter: str
    nodes: List[Node]
    edges: List[Edge]
    conflict_nodes: List[str] = []


class ConflictDetail(BaseModel):
    type: Literal[
        "COGS_EXCEEDED",
        "MISSING_GROUNDING",
        "DATA_CONFLICT",
        "DOUBLE_ENTRY_MISMATCH",
        "STALE_GROUNDING",
        "PXQ_INCONSISTENT",
    ]
    message: str
    target_edge_ids: List[str] = []
    target_node_ids: List[str] = []


class ValidationResult(BaseModel):
    is_valid: bool
    conflicts: List[ConflictDetail] = []
    feedback_for_regenerator: Optional[str] = None  # Evaluator generates this prompt
