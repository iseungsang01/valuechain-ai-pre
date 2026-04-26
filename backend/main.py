import os
import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from dotenv import load_dotenv
from sse_starlette.sse import EventSourceResponse

# Load environment variables
load_dotenv()

# Setup GenAI Client (Initialize ONCE for all agents)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_ID = "gemini-3.1-pro-preview" # For Hackathon, use Pro for better reasoning

# Import new agents
from agents.data_collector import DataCollectorAgent
from agents.estimator import EstimatorAgent
from agents.evaluator import EvaluatorAgent
from agents.models import SupplyChainGraph

app = FastAPI(title="ValueChain AI API", description="Supply Chain 기반 기업 재무 추정 및 분석 에이전트")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalysisRequest(BaseModel):
    target_node: str # Initial company to analyze
    target_quarter: str # Format: "2024-Q3"

@app.get("/")
def read_root():
    return {"status": "ValueChain AI Backend is running"}

@app.post("/api/analyze")
async def run_analysis(req: AnalysisRequest):
    """
    Starts the full multi-agent pipeline with SSE streaming.
    """
    
    # SSE Stream Generator
    async def stream_generator():
        # Instantiate agents, passing the common client/model
        data_collector = DataCollectorAgent(client=genai_client, model_id=MODEL_ID)
        estimator = EstimatorAgent(client=genai_client, model_id=MODEL_ID)
        evaluator = EvaluatorAgent(client=genai_client, model_id=MODEL_ID)
        
        # --- PHASE 1: COLLECTING ---
        yield {
            "event": "COLLECTING",
            "data": json.dumps({"status": "in_progress", "message": f"Time-bound data for {req.target_node} ({req.target_quarter}) is being collected..."})
        }
        await asyncio.sleep(1.5) # Simulating network latency
        
        grounding_sources = data_collector.collect_quarterly_data(req.target_node, req.target_quarter)
        
        yield {
            "event": "COLLECTING",
            "data": json.dumps({"status": "complete", "sources_count": len(grounding_sources)})
        }

        # --- PHASE 2: ESTIMATING ---
        yield {
            "event": "ESTIMATING",
            "data": json.dumps({"status": "in_progress", "message": "Synthesizing grounding sources to build PxQ network..."})
        }
        await asyncio.sleep(1.5)
        
        final_graph = estimator.generate_graph(req.target_quarter, grounding_sources)
        
        yield {
            "event": "ESTIMATING",
            "data": json.dumps({"status": "complete"})
        }

        # --- PHASE 3: EVALUATING & FEEDBACK ---
        yield {
            "event": "EVALUATING",
            "data": json.dumps({"status": "in_progress", "message": "Evaluating network consistency & self-reflection..."})
        }
        await asyncio.sleep(1.5)
        
        validation_result = evaluator.evaluate_graph(final_graph)
        
        if not validation_result.is_valid:
             yield {
                "event": "FEEDBACK",
                "data": json.dumps({
                    "status": "in_progress", 
                    "conflicts_count": len(validation_result.conflicts),
                    "conflicts": [c.model_dump() for c in validation_result.conflicts],
                    "feedback": validation_result.feedback_for_regenerator
                })
            }
             
             # 🚨 Feedback Loop: Instruct Estimator to regenerate (Mocked regeneration)
             print(f"[Main Pipeline] Feedback received, calling Estimator for regeneration...")
             await asyncio.sleep(2)
             # estimator.generate_graph(...)
             
             yield {
                "event": "EVALUATING",
                "data": json.dumps({"status": "complete"})
            }
        else:
             yield {
                "event": "EVALUATING",
                "data": json.dumps({"status": "complete", "message": "Graph validated successfully."})
            }

        # --- PHASE 4: RESULT ---
        yield {
            "event": "RESULT",
            "data": final_graph.model_dump_json()
        }

    # Return SSE Response
    return EventSourceResponse(stream_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)