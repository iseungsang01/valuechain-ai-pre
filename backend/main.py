import asyncio
import json
import os
import queue
import time
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


async def _drain_progress(future: asyncio.Future, progress_queue: "queue.Queue", sse_event: str):
    """Async-generator that yields SSE frames for every item that landed in
    ``progress_queue`` while ``future`` is still running, then drains any
    leftover items after the future completes. Caller awaits ``future``
    afterwards to obtain the agent's return value."""
    while not future.done():
        try:
            event_name, payload = progress_queue.get(timeout=0.05)
        except queue.Empty:
            await asyncio.sleep(0.02)
            continue
        yield {
            "event": sse_event,
            "data": json.dumps(
                {"status": "progress", "event": event_name, **payload},
                ensure_ascii=False,
            ),
        }
    while True:
        try:
            event_name, payload = progress_queue.get_nowait()
        except queue.Empty:
            break
        yield {
            "event": sse_event,
            "data": json.dumps(
                {"status": "progress", "event": event_name, **payload},
                ensure_ascii=False,
            ),
        }


async def _heartbeat(
    future: asyncio.Future,
    sse_event: str,
    label: str,
    started_at: float,
    interval: float = 2.0,
):
    """Emit a "still working" tick every ``interval`` seconds while a future
    runs. Used for opaque single-LLM-call phases (Estimator, Evaluator) so
    the UI doesn't flatline."""
    while not future.done():
        await asyncio.sleep(interval)
        if future.done():
            break
        elapsed = round(time.time() - started_at, 1)
        yield {
            "event": sse_event,
            "data": json.dumps(
                {
                    "status": "progress",
                    "event": "heartbeat",
                    "label": label,
                    "elapsed_seconds": elapsed,
                },
                ensure_ascii=False,
            ),
        }


def _make_progress_sink() -> "tuple[queue.Queue, callable]":
    """Returns a thread-safe queue and a callback that pushes ``(name, payload)``
    tuples onto it. The callback is safe to invoke from any worker thread."""
    q: queue.Queue = queue.Queue()

    def callback(event_name: str, payload: Dict[str, Any]) -> None:
        try:
            q.put_nowait((event_name, payload))
        except Exception:
            # queue is unbounded so this should not happen, but never let
            # the agent crash because of a progress hiccup.
            pass

    return q, callback


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
        await asyncio.sleep(0.05)

        # Network discovery is a single LLM call -- run it inline (fast).
        discover_q, discover_cb = _make_progress_sink()
        loop = asyncio.get_running_loop()
        discover_future = loop.run_in_executor(
            None,
            lambda: data_collector.discover_network(
                req.target_node, req.target_quarter, progress_callback=discover_cb
            ),
        )
        async for frame in _drain_progress(discover_future, discover_q, "COLLECTING"):
            yield frame
        network = await discover_future

        # --- PHASE 1: COLLECTING (network-wide) ---------------------------
        suppliers = network.get("suppliers", []) or []
        customers = network.get("customers", []) or []
        yield _sse(
            "COLLECTING",
            {
                "status": "in_progress",
                "message": (
                    f"Collecting grounding sources for {1 + len(suppliers)}"
                    f"+{len(customers)} nodes..."
                ),
                "suppliers": suppliers,
                "customers": customers,
            },
        )
        await asyncio.sleep(0.05)

        collect_q, collect_cb = _make_progress_sink()
        collect_started = time.time()
        collect_future = loop.run_in_executor(
            None,
            lambda: data_collector.collect_network_data(
                req.target_node,
                req.target_quarter,
                suppliers=suppliers,
                customers=customers,
                progress_callback=collect_cb,
            ),
        )
        async for frame in _drain_progress(collect_future, collect_q, "COLLECTING"):
            yield frame
        grounding_sources = await collect_future

        yield _sse(
            "COLLECTING",
            {
                "status": "complete",
                "sources_count": len(grounding_sources),
                "elapsed_seconds": round(time.time() - collect_started, 1),
            },
        )

        # --- PHASE 2: ESTIMATING -------------------------------------------
        estimate_started = time.time()
        yield _sse(
            "ESTIMATING",
            {
                "status": "in_progress",
                "message": (
                    f"Synthesizing PxQ network from {len(grounding_sources)} grounding source(s)..."
                ),
                "sources_count": len(grounding_sources),
            },
        )
        await asyncio.sleep(0.05)

        # Estimator is a single long LLM call. Stream a heartbeat every ~2s
        # so the UI shows elapsed time / "still thinking" instead of going
        # silent. The graph build itself runs on a worker thread.
        estimate_future = loop.run_in_executor(
            None,
            lambda: estimator.generate_graph(
                req.target_quarter,
                grounding_sources,
                target_node=req.target_node,
                suppliers=suppliers,
                customers=customers,
            ),
        )
        async for frame in _heartbeat(estimate_future, "ESTIMATING", "Estimator LLM 추론 중", estimate_started):
            yield frame
        graph = await estimate_future

        yield _sse(
            "ESTIMATING",
            {
                "status": "complete",
                "elapsed_seconds": round(time.time() - estimate_started, 1),
                "edges_count": len(graph.edges),
                "nodes_count": len(graph.nodes),
            },
        )

        # --- PHASE 3 + 4: EVALUATE → FEEDBACK loop -------------------------
        validation: ValidationResult | None = None
        attempt = 0
        # Pool of grounding sources. Re-collection passes append into this so
        # subsequent regenerations have a richer evidence base.
        grounding_pool: list = list(grounding_sources)

        while attempt <= MAX_RETRIES:
            evaluate_started = time.time()
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
            await asyncio.sleep(0.05)

            evaluate_future = loop.run_in_executor(None, lambda: evaluator.evaluate_graph(graph))
            async for frame in _heartbeat(
                evaluate_future,
                "EVALUATING",
                f"Evaluator 일관성 검사 (attempt {attempt})",
                evaluate_started,
            ):
                yield frame
            validation = await evaluate_future

            if validation.is_valid:
                yield _sse(
                    "EVALUATING",
                    {
                        "status": "complete",
                        "attempt": attempt,
                        "elapsed_seconds": round(time.time() - evaluate_started, 1),
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
                recollect_q, recollect_cb = _make_progress_sink()
                recollect_started = time.time()
                recollect_future = loop.run_in_executor(
                    None,
                    lambda: data_collector.recollect_for_edges(
                        edges_to_recollect,
                        req.target_quarter,
                        progress_callback=recollect_cb,
                    ),
                )
                async for frame in _drain_progress(recollect_future, recollect_q, "FEEDBACK"):
                    yield frame
                extra_sources = await recollect_future
                grounding_pool.extend(extra_sources)
                yield _sse(
                    "FEEDBACK",
                    {
                        "status": "in_progress",
                        "attempt": attempt,
                        "recollected_sources_count": len(extra_sources),
                        "elapsed_seconds": round(time.time() - recollect_started, 1),
                        "message": (
                            f"Re-collected {len(extra_sources)} source(s) for "
                            f"{len(edges_to_recollect)} edge(s) before regeneration."
                        ),
                    },
                )

            regenerate_started = time.time()
            yield _sse(
                "ESTIMATING",
                {
                    "status": "in_progress",
                    "attempt": attempt,
                    "message": f"Regenerating graph (attempt {attempt})...",
                },
            )
            regenerate_future = loop.run_in_executor(
                None,
                lambda: estimator.regenerate_graph(
                    graph,
                    validation.conflicts,
                    validation.feedback_for_regenerator or "",
                    extra_sources=extra_sources,
                ),
            )
            async for frame in _heartbeat(
                regenerate_future,
                "ESTIMATING",
                f"Estimator 재생성 (attempt {attempt})",
                regenerate_started,
            ):
                yield frame
            graph = await regenerate_future
            yield _sse(
                "ESTIMATING",
                {
                    "status": "complete",
                    "attempt": attempt,
                    "elapsed_seconds": round(time.time() - regenerate_started, 1),
                },
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
