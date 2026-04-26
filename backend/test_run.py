import os
import json
import asyncio
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup GenAI Client
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-3.1-pro-preview"

# Import new agents and models
from agents.data_collector import DataCollectorAgent
from agents.estimator import EstimatorAgent
from agents.evaluator import EvaluatorAgent
from agents.models import SupplyChainGraph

async def test_full_pipeline():
    print("--- Starting ValueChain AI Agent Pipeline Test ---")
    
    # 1. Instantiate Agents
    data_collector = DataCollectorAgent(client=genai_client, model_id=MODEL_ID)
    estimator = EstimatorAgent(client=genai_client, model_id=MODEL_ID)
    evaluator = EvaluatorAgent(client=genai_client, model_id=MODEL_ID)
    
    # 2. Test parameters
    target_company = "SK Hynix"
    target_quarter = "2024-Q3"
    
    # --- PHASE 1: COLLECTING ---
    print("\n[Test] Running Data Collector...")
    grounding_sources = data_collector.collect_quarterly_data(target_company, target_quarter)
    print(f"[Test] Found {len(grounding_sources)} grounding sources.")
    
    # --- PHASE 2: ESTIMATING ---
    print("\n[Test] Running Estimator...")
    initial_graph = estimator.generate_graph(target_quarter, grounding_sources)
    print(f"[Test] Initial graph generated with {len(initial_graph.nodes)} nodes and {len(initial_graph.edges)} edges.")
    print("[Test] Initial Graph JSON (truncated):")
    # print(initial_graph.model_dump_json(indent=2)[:500] + "...")

    # --- PHASE 3: EVALUATING ---
    print("\n[Test] Running Evaluator...")
    validation_result = evaluator.evaluate_graph(initial_graph)
    print(f"[Test] Validation complete. Is valid: {validation_result.is_valid}")
    
    if not validation_result.is_valid:
        print(f"[Test] Found {len(validation_result.conflicts)} conflicts.")
        for conflict in validation_result.conflicts:
            print(f"  🚨 Conflict: Type={conflict.type}, Msg={conflict.message}")
            print(f"     Target Edges: {conflict.target_edge_ids}")
            
        print("\n[Test] Feedback generated for Estimator:")
        print(validation_result.feedback_for_regenerator)
    else:
        print("[Test] Graph validated successfully.")
        
    print("\n--- ✅ Pipeline Test Complete ✅ ---")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())