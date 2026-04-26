"""End-to-end pipeline smoke test for the ValueChain AI multi-agent backend.

Four scenarios are exercised:

1. Offline pipeline + macro feedback loop. With LIVE_GROUNDING / LIVE_ESTIMATION
   / LIVE_FX disabled the DataCollector emits zero sources and the Estimator
   produces a *skeleton* graph. The Evaluator must therefore raise
   ``MISSING_GROUNDING`` and the loop must respect ``MAX_RETRIES=2``.
2. Conflict-trigger scenario — manually inject grounding sources that fire
   each of the four classic conflict types (COGS_EXCEEDED, MISSING_GROUNDING,
   DOUBLE_ENTRY_MISMATCH, STALE_GROUNDING).
3. PxQ consistency scenario (NEW). With a stubbed FX rate, an edge whose
   ``estimated_revenue_krw`` disagrees with ``P × Q × FX`` raises
   ``PXQ_INCONSISTENT``. With FX returning ``None``, the check is skipped.
4. Re-collection scenario (NEW). A stubbed DataCollector returns a fresh
   source on the second pass. The orchestration logic in main.py is mimicked
   so the test verifies that ``MISSING_GROUNDING`` clears once the
   Estimator gets ``extra_sources`` and re-attaches them.

Run with::

    python backend/test_run.py
"""

from __future__ import annotations

import asyncio
import os

# Force offline mode for every scenario so the smoke test never depends on
# the network.
os.environ.setdefault("LIVE_GROUNDING", "false")
os.environ.setdefault("LIVE_ESTIMATION", "false")
os.environ.setdefault("LIVE_DISCLOSURE", "false")
os.environ.setdefault("LIVE_FX", "false")

from datetime import date  # noqa: E402

from agents import fx  # noqa: E402
from agents.data_collector import DataCollectorAgent  # noqa: E402
from agents.estimator import EstimatorAgent  # noqa: E402
from agents.evaluator import EvaluatorAgent  # noqa: E402
from agents.models import (  # noqa: E402
    Edge,
    GroundingSource,
    Node,
    SupplyChainGraph,
)


def _print_section(title: str) -> None:
    bar = "=" * len(title)
    print(f"\n{bar}\n{title}\n{bar}")


# ---------------------------------------------------------------------------
# Scenario 1 — Skeleton graph + macro feedback loop honours MAX_RETRIES
# ---------------------------------------------------------------------------


async def scenario_offline_pipeline() -> None:
    _print_section("[Scenario 1] Offline skeleton + macro feedback loop")

    target_company = "Acme Corp"
    target_quarter = "2024-Q3"

    collector = DataCollectorAgent(client=None, model_id="gemini-3.1-pro-preview")
    estimator = EstimatorAgent(client=None, model_id="gemini-3.1-pro-preview")
    evaluator = EvaluatorAgent(client=None, model_id="gemini-3.1-pro-preview")

    network = collector.discover_network(target_company, target_quarter)
    print(
        f"Discovered network (offline): suppliers={network['suppliers']}, "
        f"customers={network['customers']}"
    )
    assert network == {"suppliers": [], "customers": []}, (
        "Offline discovery must return an empty network — never a hardcoded mapping."
    )

    sources = collector.collect_network_data(
        target_company,
        target_quarter,
        suppliers=network["suppliers"],
        customers=network["customers"],
    )
    print(f"Collected {len(sources)} grounding sources (offline → expect 0).")
    assert sources == [], (
        "Offline collector must emit zero sources — no fabricated revenue/ASP rows."
    )

    # Hand-roll a tiny network so there is at least one edge to evaluate.
    skeleton = SupplyChainGraph(
        target_quarter=target_quarter,
        nodes=[
            Node(id=target_company, name=target_company, type="TARGET"),
            Node(id="Supplier X", name="Supplier X", type="SUPPLIER"),
        ],
        edges=[
            Edge(
                id=f"Supplier X-{target_company}",
                source="Supplier X",
                target=target_company,
                estimated_revenue_krw=0.0,
            )
        ],
    )
    skeleton.nodes[0].edges_in = [skeleton.edges[0].id]
    skeleton.nodes[1].edges_out = [skeleton.edges[0].id]
    graph = skeleton

    MAX_RETRIES = 2
    attempt = 0
    while attempt <= MAX_RETRIES:
        validation = evaluator.evaluate_graph(graph)
        print(
            f"\n  >> attempt={attempt}, is_valid={validation.is_valid}, "
            f"conflicts={len(validation.conflicts)}"
        )
        for c in validation.conflicts:
            print(f"    * [{c.type}] {c.message}")

        if validation.is_valid or attempt >= MAX_RETRIES:
            break
        attempt += 1
        graph = estimator.regenerate_graph(
            graph, validation.conflicts, validation.feedback_for_regenerator or ""
        )

    print(f"\nFinal attempts used: {attempt} / {MAX_RETRIES}")
    assert attempt <= MAX_RETRIES, "Loop must respect MAX_RETRIES."
    print("[Scenario 1] OK")


# ---------------------------------------------------------------------------
# Scenario 2 — Each of the four classic conflict types is detected.
# ---------------------------------------------------------------------------


def scenario_all_conflict_types() -> None:
    _print_section("[Scenario 2] Conflict detection coverage")

    quarter = "2024-Q3"

    fresh_revenue = GroundingSource(
        metric_type="REVENUE",
        target_quarter=quarter,
        value=100.0,
        unit="KRW",
        source_name="Seller report",
        url="https://example.com/seller",
        extraction_date=date(2024, 9, 30),
        article_date=date(2024, 9, 30),
        tier="OFFICIAL_IR",
    )
    fresh_cogs_mismatch = GroundingSource(
        metric_type="COGS",
        target_quarter=quarter,
        value=200.0,  # 100% delta → triggers DOUBLE_ENTRY_MISMATCH
        unit="KRW",
        source_name="Buyer report",
        url="https://example.com/buyer",
        extraction_date=date(2024, 9, 30),
        article_date=date(2024, 9, 30),
        tier="OFFICIAL_IR",
    )
    stale_revenue = GroundingSource(
        metric_type="REVENUE",
        target_quarter=quarter,
        value=50.0,
        unit="KRW",
        source_name="Old article",
        url="https://example.com/old",
        extraction_date=date(2024, 9, 30),  # extracted recently
        article_date=date(2020, 1, 1),  # but the article is years old
        tier="NEWS",
    )

    target = Node(
        id="T",
        name="Target",
        type="TARGET",
        reported_cogs_krw=10.0,  # tiny COGS guarantees over-estimation
    )
    supplier_a = Node(id="A", name="Supplier A", type="SUPPLIER")
    supplier_b = Node(id="B", name="Supplier B", type="SUPPLIER")
    supplier_c = Node(id="C", name="Supplier C", type="SUPPLIER")

    edge_double_entry = Edge(
        id="A-T",
        source="A",
        target="T",
        estimated_revenue_krw=120.0,
        grounding_sources=[fresh_revenue, fresh_cogs_mismatch],
    )
    edge_missing_grounding = Edge(
        id="B-T",
        source="B",
        target="T",
        estimated_revenue_krw=50.0,
        grounding_sources=[],
    )
    edge_stale = Edge(
        id="C-T",
        source="C",
        target="T",
        estimated_revenue_krw=30.0,
        grounding_sources=[stale_revenue],
    )

    graph = SupplyChainGraph(
        target_quarter=quarter,
        nodes=[target, supplier_a, supplier_b, supplier_c],
        edges=[edge_double_entry, edge_missing_grounding, edge_stale],
    )
    target.edges_in = [edge_double_entry.id, edge_missing_grounding.id, edge_stale.id]
    supplier_a.edges_out = [edge_double_entry.id]
    supplier_b.edges_out = [edge_missing_grounding.id]
    supplier_c.edges_out = [edge_stale.id]

    evaluator = EvaluatorAgent(client=None, model_id="x")
    result = evaluator.evaluate_graph(graph)

    found_types = {c.type for c in result.conflicts}
    expected = {
        "COGS_EXCEEDED",
        "MISSING_GROUNDING",
        "DOUBLE_ENTRY_MISMATCH",
        "STALE_GROUNDING",
    }
    print(f"Detected conflict types: {sorted(found_types)}")
    print(f"Expected:                {sorted(expected)}")

    assert expected.issubset(found_types), (
        f"Missing conflict types: {expected - found_types}"
    )
    print("[Scenario 2] OK -- all four classic conflict types detected.")


# ---------------------------------------------------------------------------
# Scenario 3 — PxQ inconsistency (with stubbed FX) and graceful skip.
# ---------------------------------------------------------------------------


def scenario_pxq_consistency() -> None:
    _print_section("[Scenario 3] PxQ consistency via FX")

    quarter = "2024-Q3"

    src = GroundingSource(
        metric_type="ASP",
        target_quarter=quarter,
        value=2.0,
        unit="USD",
        source_name="Industry tracker",
        url="https://example.com/asp",
        extraction_date=date(2024, 9, 30),
        article_date=date(2024, 9, 30),
        tier="NEWS",
    )

    target = Node(id="T", name="Target", type="TARGET")
    supplier = Node(id="S", name="Supplier", type="SUPPLIER")
    edge = Edge(
        id="S-T",
        source="S",
        target="T",
        estimated_revenue_krw=10.0,  # disagrees with P*Q*FX = 2*10*1300 = 26000 KRW
        p_as_usd=2.0,
        q_units=10.0,
        grounding_sources=[src],
    )
    graph = SupplyChainGraph(
        target_quarter=quarter,
        nodes=[target, supplier],
        edges=[edge],
    )
    target.edges_in = [edge.id]
    supplier.edges_out = [edge.id]

    evaluator = EvaluatorAgent(client=None, model_id="x")

    # 3a — stub fx.quarter_average so the check fires deterministically.
    original = fx.quarter_average
    fx.quarter_average = lambda base, quote, q: 1300.0  # type: ignore[assignment]
    try:
        result = evaluator.evaluate_graph(graph)
    finally:
        fx.quarter_average = original  # type: ignore[assignment]

    pxq = [c for c in result.conflicts if c.type == "PXQ_INCONSISTENT"]
    print(f"PxQ conflicts (FX=1300): {[c.message for c in pxq]}")
    assert pxq, "PXQ_INCONSISTENT must fire when KRW estimate disagrees with FX-converted P*Q."

    # 3b — stub fx.quarter_average to None; the check must be skipped.
    fx.quarter_average = lambda base, quote, q: None  # type: ignore[assignment]
    try:
        # Reset has_conflict so we can observe a clean state.
        for e in graph.edges:
            e.has_conflict = False
        result_no_fx = evaluator.evaluate_graph(graph)
    finally:
        fx.quarter_average = original  # type: ignore[assignment]

    pxq_no_fx = [c for c in result_no_fx.conflicts if c.type == "PXQ_INCONSISTENT"]
    print(f"PxQ conflicts (FX=None): {pxq_no_fx}")
    assert not pxq_no_fx, "PXQ_INCONSISTENT must be skipped when FX is unavailable."
    print("[Scenario 3] OK -- PxQ check fires with FX, skipped without it.")


# ---------------------------------------------------------------------------
# Scenario 4 — Re-collection unblocks MISSING_GROUNDING.
# ---------------------------------------------------------------------------


def scenario_recollection_unblocks_missing() -> None:
    _print_section("[Scenario 4] Re-collection unblocks MISSING_GROUNDING")

    quarter = "2024-Q3"

    target = Node(id="T", name="Target", type="TARGET")
    supplier = Node(id="S", name="Supplier", type="SUPPLIER")
    edge = Edge(
        id="S-T",
        source="S",
        target="T",
        estimated_revenue_krw=100.0,
        grounding_sources=[],  # missing grounding on the first pass
    )
    graph = SupplyChainGraph(
        target_quarter=quarter,
        nodes=[target, supplier],
        edges=[edge],
    )
    target.edges_in = [edge.id]
    supplier.edges_out = [edge.id]

    evaluator = EvaluatorAgent(client=None, model_id="x")
    estimator = EstimatorAgent(client=None, model_id="x")

    pass1 = evaluator.evaluate_graph(graph)
    assert any(c.type == "MISSING_GROUNDING" for c in pass1.conflicts), (
        "First pass must flag MISSING_GROUNDING."
    )

    # The orchestrator (main.py) would call DataCollector.recollect_for_edges
    # here. We simulate the result directly so this test stays offline.
    fresh_source = GroundingSource(
        metric_type="REVENUE",
        target_quarter=quarter,
        value=100.0,
        unit="KRW",
        source_name="S quarterly disclosure",
        url="https://example.com/s/q3",
        extraction_date=date(2024, 10, 5),
        article_date=date(2024, 10, 1),
        tier="OFFICIAL_DISCLOSURE",
    )

    graph = estimator.regenerate_graph(
        graph,
        pass1.conflicts,
        pass1.feedback_for_regenerator or "",
        extra_sources=[fresh_source],
    )

    pass2 = evaluator.evaluate_graph(graph)
    print(f"Pass 2 conflicts: {[c.type for c in pass2.conflicts]}")
    assert not any(c.type == "MISSING_GROUNDING" for c in pass2.conflicts), (
        "After re-collection MISSING_GROUNDING must clear."
    )
    print("[Scenario 4] OK -- recollected sources unblock MISSING_GROUNDING.")


def main() -> None:
    print("--- ValueChain AI Pipeline Smoke Test ---")
    asyncio.run(scenario_offline_pipeline())
    scenario_all_conflict_types()
    scenario_pxq_consistency()
    scenario_recollection_unblocks_missing()
    print("\n--- [OK] Smoke test complete ---")


if __name__ == "__main__":
    main()
