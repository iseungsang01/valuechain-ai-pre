from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Literal
from datetime import date

class GroundingSource(BaseModel):
    metric_type: Literal["ASP", "Q", "REVENUE", "COGS"]
    target_quarter: str # "2024-Q3"
    value: float
    unit: str # "USD", "KRW", "Units"
    source_name: str
    url: HttpUrl
    extraction_date: date

class Edge(BaseModel):
    id: str # "A-B"
    source: str # Company ID A
    target: str # Company ID B
    estimated_revenue_krw: float
    p_as_usd: Optional[float] = None
    q_units: Optional[float] = None
    grounding_sources: List[GroundingSource] = []
    has_conflict: bool = False

class Node(BaseModel):
    id: str # "SK Hynix"
    name: str
    type: Literal["TARGET", "SUPPLIER", "CUSTOMER"]
    reported_cogs_krw: Optional[float] = None # Evaluator uses this
    edges_out: List[str] = [] # List of edge IDs
    edges_in: List[str] = []

class SupplyChainGraph(BaseModel):
    target_quarter: str
    nodes: List[Node]
    edges: List[Edge]
    conflict_nodes: List[str] = []

class ConflictDetail(BaseModel):
    type: Literal["COGS_EXCEEDED", "MISSING_GROUNDING", "DATA_CONFLICT"]
    message: str
    target_edge_ids: List[str] = []
    target_node_ids: List[str] = []

class ValidationResult(BaseModel):
    is_valid: bool
    conflicts: List[ConflictDetail] = []
    feedback_for_regenerator: Optional[str] = None # Evaluator generates this prompt