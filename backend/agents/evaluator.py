import json
from google import genai
from typing import List, Tuple

from .base import BaseAgent
from .models import SupplyChainGraph, Node, Edge, ValidationResult, ConflictDetail

class EvaluatorAgent(BaseAgent):
    def __init__(self, client: genai.Client, model_id: str):
        super().__init__(role="Evaluator", client=client, model_id=model_id)

    def evaluate_graph(self, graph: SupplyChainGraph) -> ValidationResult:
        """
        Performs network consistency checks and generates feedback.
        """
        print(f"[{self.role}] Evaluating network consistency for {graph.target_quarter}...")
        
        conflicts = []
        
        # 1. COGS Consistency Check
        cogs_conflicts = self._check_cogs_consistency(graph)
        conflicts.extend(cogs_conflicts)
        
        # 2. Grounding Integrity Check
        grounding_conflicts = self._check_grounding_integrity(graph)
        conflicts.extend(grounding_conflicts)
        
        # Determine overall validity
        is_valid = len(conflicts) == 0
        
        # Generate feedback prompt if invalid
        feedback = None
        if not is_valid:
            print(f"[{self.role}] Conflicts detected! Generating macro-feedback loop prompt...")
            feedback = self._generate_feedback_prompt(conflicts)
            
        return ValidationResult(
            is_valid=is_valid,
            conflicts=conflicts,
            feedback_for_regenerator=feedback
        )

    def _check_cogs_consistency(self, graph: SupplyChainGraph) -> List[ConflictDetail]:
        """Checks if sum of input edges exceeds reported COGS for nodes."""
        conflicts = []
        for node in graph.nodes:
            if node.type == "TARGET" and node.reported_cogs_krw:
                # Sum estimated cost from all suppliers
                total_supply_cost = 0.0
                supplier_edge_ids = []
                
                for edge_id in node.edges_in:
                    # Find the actual edge object
                    edge = next((e for e in graph.edges if e.id == edge_id), None)
                    if edge:
                        total_supply_cost += edge.estimated_revenue_krw
                        supplier_edge_ids.append(edge.id)
                
                if total_supply_cost > node.reported_cogs_krw:
                    msg = (f"Over-estimation: Sum of supply costs ({total_supply_cost:,.0f} KRW) for "
                           f"node '{node.id}' exceeds its reported COGS ({node.reported_cogs_krw:,.0f} KRW).")
                    conflicts.append(ConflictDetail(
                        type="COGS_EXCEEDED",
                        message=msg,
                        target_edge_ids=supplier_edge_ids,
                        target_node_ids=[node.id]
                    ))
        return conflicts

    def _check_grounding_integrity(self, graph: SupplyChainGraph) -> List[ConflictDetail]:
        """Checks if all edges have proper grounding sources."""
        conflicts = []
        for edge in graph.edges:
            if not edge.grounding_sources:
                 conflicts.append(ConflictDetail(
                        type="MISSING_GROUNDING",
                        message=f"Missing Grounding: Edge '{edge.id}' has no verified sources.",
                        target_edge_ids=[edge.id]
                    ))
        return conflicts

    def _generate_feedback_prompt(self, conflicts: List[ConflictDetail]) -> str:
        """Synthesizes conflicts into a prompt for the Estimator agent."""
        # This is a critical step. We want the LLM to analyze the conflicts 
        # and provide instructions. For the demo, we mock the feedback.
        
        cogs_conflict = next((c for c in conflicts if c.type == "COGS_EXCEEDED"), None)
        missing_grounding = next((c for c in conflicts if c.type == "MISSING_GROUNDING"), None)
        
        feedback_msgs = []
        
        if cogs_conflict:
            feedback_msgs.append(
                f"- CRITICAL COGS EXCEEDED in node '{cogs_conflict.target_node_ids[0]}'. "
                f"The sum of supply edges {cogs_conflict.target_edge_ids} is too high. "
                f"Please re-analyze the supply mix and re-estimate the Q values for these edges."
            )
            
        if missing_grounding:
             feedback_msgs.append(
                f"- Missing verified sources for edge '{missing_grounding.target_edge_ids[0]}'. "
                f"Please do a deep search for specific ASP or Revenue figures for this transaction."
            )
            
        return "\n".join(feedback_msgs)