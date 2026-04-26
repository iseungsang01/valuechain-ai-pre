import json
from google import genai
from typing import List, Dict
import os

from .base import BaseAgent
from .models import SupplyChainGraph, Node, Edge, GroundingSource

class EstimatorAgent(BaseAgent):
    def __init__(self, client: genai.Client, model_id: str):
        super().__init__(role="Estimator", client=client, model_id=model_id)

    def generate_graph(self, target_quarter: str, sources: List[GroundingSource]) -> SupplyChainGraph:
        """
        Synthesizes grounding sources to build the initial PxQ supply chain graph.
        """
        print(f"[{self.role}] Synthesizing data into initial PxQ graph for {target_quarter}...")
        
        # 🚨 Important 24h Hackathon Strategy:
        # In a real-world scenario, we'd use the LLM (`self.prompt_model`) to parse the sources 
        # and construct the JSON. To ensure we have a working, robust demo 
        # that showcases the Evaluator/Feedback Loop in 24 hours, 
        # we will use a deterministic mock of the output.
        # However, the Evaluator will still perform real analysis on this graph.

        nodes = []
        edges = []
        
        if target_quarter == "2024-Q3":
            # Nodes
            target_node = Node(id="SK Hynix", name="SK Hynix", type="TARGET", reported_cogs_krw=100000.0) # Mocked COGS
            nodes.append(target_node)
            
            nodes.append(Node(id="TSMC", name="TSMC", type="SUPPLIER"))
            nodes.append(Node(id="Apple", name="Apple", type="CUSTOMER"))
            nodes.append(Node(id="NVIDIA", name="NVIDIA", type="CUSTOMER"))
            
            # Edges with Grounding (A -> B = A's Rev, B's Cost)
            edges.append(Edge(
                id="TSMC-SK Hynix",
                source="TSMC",
                target="SK Hynix",
                estimated_revenue_krw=30000.0,
                grounding_sources=[s for s in sources if s.source_name == "Supply Chain Analysis Report (Mock)"],
                has_conflict=False
            ))
            
            # This edge has conflict in the sources (ASP is missing in reality)
            edges.append(Edge(
                id="SK Hynix-NVIDIA",
                source="SK Hynix",
                target="NVIDIA",
                estimated_revenue_krw=90000.0,
                p_as_usd=150.0,
                q_units=600000.0,
                grounding_sources=[s for s in sources if s.metric_type == "ASP"],
                has_conflict=False
            ))
            
            # Mock COGS (SK Hynix Cost) to set up Over-estimation error later
            edges.append(Edge(
                id="Other-SK Hynix",
                source="Other Suppliers",
                target="SK Hynix",
                estimated_revenue_krw=80000.0, # (30000 + 80000) > 100000 COGS 🚨
                grounding_sources=[], # No grounding for other suppliers yet
                has_conflict=False
            ))

        # Build initial graph object
        graph = SupplyChainGraph(
            target_quarter=target_quarter,
            nodes=nodes,
            edges=edges
        )
        
        # Link Edges to Nodes (Edges Out/In)
        for edge in graph.edges:
            for node in graph.nodes:
                if node.id == edge.source:
                    node.edges_out.append(edge.id)
                if node.id == edge.target:
                    node.edges_in.append(edge.id)
        
        return graph