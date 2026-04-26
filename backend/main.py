import asyncio
import json
import os
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

# Load environment variables
load_dotenv()

# Setup GenAI Client (Initialize ONCE for all agents)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
MODEL_ID = "gemini-3.1-pro-preview"  # Hackathon: Pro for better reasoning

# SPEC § 2.3 — Macro feedback loop is capped at two retry passes.
MAX_RETRIES = 2

# Import new agents
from agents.data_collector import DataCollectorAgent
from agents.estimator import EstimatorAgent
from agents.evaluator import EvaluatorAgent
from agents.models import SupplyChainGraph, ValidationResult

app = FastAPI(
    title="ValueChain AI API",
    description="Supply Chain 기반 기업 재무 추정 및 분석 에이전트",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalysisRequest(BaseModel):
    target_node: str  # Initial company to analyze
    target_quarter: str  # Format: "2024-Q3"


def _sse(event: str, payload: Dict[str, Any]) -> Dict[str, str]:
    return {"event": event, "data": json.dumps(payload, ensure_ascii=False)}


def _validation_payload(result: ValidationResult, attempt: int) -> Dict[str, Any]:
    return {
        "status": "in_progress",
        "attempt": attempt,
        "conflicts_count": len(result.conflicts),
        "conflicts": [c.model_dump() for c in result.conflicts],
        "feedback": result.feedback_for_regenerator,
    }


@app.get("/")
def read_root():
    return {"status": "ValueChain AI Backend is running"}


@app.post("/api/analyze")
async def run_analysis(req: AnalysisRequest):
    """
    Starts the full multi-agent pipeline with SSE streaming.
    Implements SPEC § 2.3 macro feedback loop with up to MAX_RETRIES rounds.
    """

    async def stream_generator():
        # Instantiate agents, passing the shared client/model.
        data_collector = DataCollectorAgent(client=genai_client, model_id=MODEL_ID)
        estimator = EstimatorAgent(client=genai_client, model_id=MODEL_ID)
        evaluator = EvaluatorAgent(client=genai_client, model_id=MODEL_ID)

        # --- PHASE 0: NETWORK DISCOVERY (Spec § 2.1 quarterly network) -----
        yield _sse(
            "COLLECTING",
            {
                "status": "in_progress",
                "message": (
                    f"Discovering supply network around {req.target_node} "
                    f"for {req.target_quarter}..."
                ),
            },
        )
        await asyncio.sleep(0.2)

        network = data_collector.discover_network(
            req.target_node, req.target_quarter
        )

        # --- PHASE 1: COLLECTING (network-wide) ---------------------------
        yield _sse(
            "COLLECTING",
            {
                "status": "in_progress",
                "message": (
                    f"Collecting grounding sources for {1 + len(network.get('suppliers', []))}"
                    f"+{len(network.get('customers', []))} nodes..."
                ),
                "suppliers": network.get("suppliers", []),
                "customers": network.get("customers", []),
            },
        )
        await asyncio.sleep(0.2)

        grounding_sources = data_collector.collect_network_data(
            req.target_node,
            req.target_quarter,
            suppliers=network.get("suppliers"),
            customers=network.get("customers"),
        )

        yield _sse(
            "COLLECTING",
            {"status": "complete", "sources_count": len(grounding_sources)},
        )

        # --- PHASE 2: ESTIMATING -------------------------------------------
        yield _sse(
            "ESTIMATING",
            {
                "status": "in_progress",
                "message": "Synthesizing grounding sources into a PxQ supply chain network...",
            },
        )
        await asyncio.sleep(0.3)

        graph = estimator.generate_graph(
            req.target_quarter,
            grounding_sources,
            target_node=req.target_node,
            suppliers=network.get("suppliers"),
            customers=network.get("customers"),
        )

        yield _sse("ESTIMATING", {"status": "complete"})

        # --- PHASE 3 + 4: EVALUATE → FEEDBACK loop -------------------------
        validation: ValidationResult | None = None
        attempt = 0
        # Pool of grounding sources. Re-collection passes append into this so
        # subsequent regenerations have a richer evidence base.
        grounding_pool: list = list(grounding_sources)

        while attempt <= MAX_RETRIES:
            yield _sse(
                "EVALUATING",
                {
                    "status": "in_progress",
                    "attempt": attempt,
                    "message": (
                        "Evaluating network consistency"
                        + (f" (retry {attempt})" if attempt > 0 else "")
                        + "..."
                    ),
                },
            )
            await asyncio.sleep(0.3)

            validation = evaluator.evaluate_graph(graph)

            if validation.is_valid:
                yield _sse(
                    "EVALUATING",
                    {
                        "status": "complete",
                        "attempt": attempt,
                        "message": "Graph validated successfully.",
                    },
                )
                break

            # Surface the feedback details to the UI/log panel.
            yield _sse("FEEDBACK", _validation_payload(validation, attempt))

            yield _sse(
                "EVALUATING",
                {
                    "status": "complete",
                    "attempt": attempt,
                    "message": (
                        f"{len(validation.conflicts)} conflict(s) found; "
                        + (
                            "regenerating graph..."
                            if attempt < MAX_RETRIES
                            else "max retries reached, returning best-effort graph."
                        )
                    ),
                },
            )

            if attempt >= MAX_RETRIES:
                break

            attempt += 1

            # SPEC § 2.3 macro feedback: re-collect grounding for any edge that
            # was flagged as MISSING_GROUNDING or STALE_GROUNDING before
            # regenerating the graph. Without this step those conflicts could
            # never resolve because the Estimator alone cannot manufacture a
            # source.
            extra_sources = []
            stale_or_missing_edge_ids = {
                eid
                for c in validation.conflicts
                if c.type in ("MISSING_GROUNDING", "STALE_GROUNDING")
                for eid in c.target_edge_ids
            }
            if stale_or_missing_edge_ids:
                edges_to_recollect = [
                    e for e in graph.edges if e.id in stale_or_missing_edge_ids
                ]
                extra_sources = data_collector.recollect_for_edges(
                    edges_to_recollect, req.target_quarter
                )
                grounding_pool.extend(extra_sources)
                yield _sse(
                    "FEEDBACK",
                    {
                        "status": "in_progress",
                        "attempt": attempt,
                        "recollected_sources_count": len(extra_sources),
                        "message": (
                            f"Re-collected {len(extra_sources)} source(s) for "
                            f"{len(edges_to_recollect)} edge(s) before regeneration."
                        ),
                    },
                )

            graph = estimator.regenerate_graph(
                graph,
                validation.conflicts,
                validation.feedback_for_regenerator or "",
                extra_sources=extra_sources,
            )

        # --- PHASE 5: RESULT ------------------------------------------------
        result_payload = json.loads(graph.model_dump_json())
        if validation is not None:
            result_payload["validation"] = {
                "is_valid": validation.is_valid,
                "attempts": attempt,
                "conflicts_count": len(validation.conflicts),
            }
        yield {"event": "RESULT", "data": json.dumps(result_payload, ensure_ascii=False)}

    return EventSourceResponse(stream_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
