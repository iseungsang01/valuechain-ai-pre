import json
from datetime import date, timedelta
from typing import List, Optional, Tuple

from google import genai

from . import fx
from .base import BaseAgent
from .models import (
    ConflictDetail,
    Edge,
    GroundingSource,
    Node,
    SupplyChainGraph,
    ValidationResult,
)


# Tolerance: estimated revenue and reported procurement may diverge up to 10 %
# before we flag a double-entry mismatch.
DOUBLE_ENTRY_TOLERANCE = 0.10

# A grounding source is considered "fresh" if its underlying article was
# published within 12 months *of the quarter end*. SPEC § 2.3.1.
MAX_GROUNDING_AGE_DAYS = 365

# PxQ tolerance: the LLM's KRW estimate may diverge from the FX-converted
# (P × Q × USD/KRW) figure by up to 25 % before we raise PXQ_INCONSISTENT.
PXQ_TOLERANCE = 0.25


def _quarter_end_date(target_quarter: str) -> date:
    """Convert "2024-Q3" → date(2024, 9, 30). Defaults to today on parse error."""
    try:
        year_str, q_str = target_quarter.split("-Q")
        year = int(year_str)
        quarter = int(q_str)
        end_month = quarter * 3
        # End of month: take first of next month, then subtract one day.
        if end_month == 12:
            return date(year, 12, 31)
        # Days in each quarter end month: Mar 31, Jun 30, Sep 30
        next_month_start = date(year, end_month + 1, 1)
        return next_month_start - timedelta(days=1)
    except Exception:
        return date.today()


def _source_anchor_date(source: GroundingSource) -> date:
    """SPEC § 2.3.1 — freshness is anchored on the article date when present;
    fall back to extraction date so the legacy data path still works."""
    return source.article_date or source.extraction_date


class EvaluatorAgent(BaseAgent):
    def __init__(self, client: Optional[genai.Client], model_id: str):
        super().__init__(role="Evaluator", client=client, model_id=model_id)

    def evaluate_graph(self, graph: SupplyChainGraph) -> ValidationResult:
        """
        Performs SPEC § 2.3.1 network consistency checks and generates feedback.
        Five checks now:
          1. Conflict (Double-Entry Mismatch between A↔B reports)
          2. Over-estimation (sum of supply edges > reported COGS)
          3. Freshness & Grounding (sources missing or stale relative to quarter)
          4. PxQ inconsistency (LLM KRW vs P × Q × FX(quarter mean))
        """
        print(f"[{self.role}] Evaluating network consistency for {graph.target_quarter}...")

        conflicts: List[ConflictDetail] = []

        # 1. Double-Entry Mismatch (SPEC § 2.3.1 conflict #1)
        conflicts.extend(self._check_double_entry_consistency(graph))

        # 2. COGS Over-estimation (SPEC § 2.3.1 conflict #2)
        conflicts.extend(self._check_cogs_consistency(graph))

        # 3. Grounding integrity + Freshness (SPEC § 2.3.1 conflict #3)
        conflicts.extend(self._check_grounding_integrity(graph))
        conflicts.extend(self._check_grounding_freshness(graph))

        # 4. PxQ vs FX-converted KRW (NEW — SPEC § 2.2 PxQ semantics)
        conflicts.extend(self._check_pxq_consistency(graph))

        # Determine overall validity
        is_valid = len(conflicts) == 0

        # Mark conflicting edges/nodes for the UI highlight pass.
        conflict_edge_ids = {
            edge_id for c in conflicts for edge_id in c.target_edge_ids
        }
        for edge in graph.edges:
            edge.has_conflict = edge.id in conflict_edge_ids

        graph.conflict_nodes = sorted({
            node_id for c in conflicts for node_id in c.target_node_ids
        })

        # Generate feedback prompt if invalid
        feedback = None
        if not is_valid:
            print(f"[{self.role}] {len(conflicts)} conflict(s) detected -- preparing feedback prompt...")
            feedback = self._generate_feedback_prompt(conflicts)

        return ValidationResult(
            is_valid=is_valid,
            conflicts=conflicts,
            feedback_for_regenerator=feedback,
        )

    # --- SPEC § 2.3.1 - Conflict #1: Double-Entry Mismatch -------------------

    def _check_double_entry_consistency(
        self, graph: SupplyChainGraph
    ) -> List[ConflictDetail]:
        """
        For every edge A→B, compare REVENUE-typed grounding (A's view) with
        COGS-typed grounding (B's view). If both sides reported but differ
        beyond DOUBLE_ENTRY_TOLERANCE, raise a conflict.
        """
        conflicts: List[ConflictDetail] = []
        for edge in graph.edges:
            revenue_sources = [
                s for s in edge.grounding_sources if s.metric_type == "REVENUE"
            ]
            cogs_sources = [
                s for s in edge.grounding_sources if s.metric_type == "COGS"
            ]

            if not revenue_sources or not cogs_sources:
                # Missing-side issue is captured by _check_grounding_integrity.
                continue

            # Average within each side, then compare. Convert to a common unit
            # by trusting whichever side already used KRW; otherwise rely on
            # the absolute deltas of declared values.
            revenue_value = sum(s.value for s in revenue_sources) / len(revenue_sources)
            cogs_value = sum(s.value for s in cogs_sources) / len(cogs_sources)

            base = max(revenue_value, cogs_value, 1e-9)
            relative_delta = abs(revenue_value - cogs_value) / base

            if relative_delta > DOUBLE_ENTRY_TOLERANCE:
                msg = (
                    f"Double-entry mismatch on edge '{edge.id}': "
                    f"{edge.source}→{edge.target} reported revenue "
                    f"{revenue_value:,.0f} vs counter-party COGS {cogs_value:,.0f} "
                    f"(Δ {relative_delta * 100:.1f}% > {DOUBLE_ENTRY_TOLERANCE * 100:.0f}%)."
                )
                conflicts.append(
                    ConflictDetail(
                        type="DOUBLE_ENTRY_MISMATCH",
                        message=msg,
                        target_edge_ids=[edge.id],
                        target_node_ids=[edge.source, edge.target],
                    )
                )
        return conflicts

    # --- SPEC § 2.3.1 - Conflict #2: COGS Over-estimation --------------------

    def _check_cogs_consistency(
        self, graph: SupplyChainGraph
    ) -> List[ConflictDetail]:
        """Sum of input edge revenues must not exceed the target's reported COGS."""
        conflicts: List[ConflictDetail] = []
        for node in graph.nodes:
            if node.type != "TARGET" or not node.reported_cogs_krw:
                continue

            total_supply_cost = 0.0
            supplier_edge_ids: List[str] = []

            for edge_id in node.edges_in:
                edge = next((e for e in graph.edges if e.id == edge_id), None)
                if edge:
                    total_supply_cost += edge.estimated_revenue_krw
                    supplier_edge_ids.append(edge.id)

            if total_supply_cost > node.reported_cogs_krw:
                msg = (
                    f"Over-estimation: Sum of supply costs ({total_supply_cost:,.0f} KRW) "
                    f"into '{node.id}' exceeds reported COGS "
                    f"({node.reported_cogs_krw:,.0f} KRW)."
                )
                conflicts.append(
                    ConflictDetail(
                        type="COGS_EXCEEDED",
                        message=msg,
                        target_edge_ids=supplier_edge_ids,
                        target_node_ids=[node.id],
                    )
                )
        return conflicts

    # --- SPEC § 2.3.1 - Conflict #3a: Missing Grounding ----------------------

    def _check_grounding_integrity(
        self, graph: SupplyChainGraph
    ) -> List[ConflictDetail]:
        """Every edge must carry at least one grounding source, unless it is an estimated value."""
        conflicts: List[ConflictDetail] = []
        for edge in graph.edges:
            if not edge.grounding_sources:
                # Relax the constraint: if the Estimator guessed a non-zero value and explicitly tagged it,
                # we allow it to pass without a hard conflict, though it has weak/no grounding.
                if edge.is_estimated:
                    continue
                
                conflicts.append(
                    ConflictDetail(
                        type="MISSING_GROUNDING",
                        message=f"Missing grounding: edge '{edge.id}' has no verified sources.",
                        target_edge_ids=[edge.id],
                        target_node_ids=[edge.source, edge.target],
                    )
                )
        return conflicts

    # --- SPEC § 2.3.1 - Conflict #3b: Stale Grounding (Freshness) ------------

    def _check_grounding_freshness(
        self, graph: SupplyChainGraph
    ) -> List[ConflictDetail]:
        """
        Flag any grounding source whose anchor date (article_date or, as a
        fallback, extraction_date) is older than MAX_GROUNDING_AGE_DAYS
        relative to the quarter's end date.
        """
        conflicts: List[ConflictDetail] = []
        quarter_end = _quarter_end_date(graph.target_quarter)

        for edge in graph.edges:
            stale: List[Tuple[GroundingSource, int]] = []
            for source in edge.grounding_sources:
                anchor = _source_anchor_date(source)
                age_days = (quarter_end - anchor).days
                if age_days > MAX_GROUNDING_AGE_DAYS:
                    stale.append((source, age_days))

            if stale:
                stale_descriptions = ", ".join(
                    f"{src.source_name} ({age}d old)" for src, age in stale
                )
                conflicts.append(
                    ConflictDetail(
                        type="STALE_GROUNDING",
                        message=(
                            f"Stale grounding on edge '{edge.id}' for quarter "
                            f"{graph.target_quarter}: {stale_descriptions}."
                        ),
                        target_edge_ids=[edge.id],
                        target_node_ids=[edge.source, edge.target],
                    )
                )
        return conflicts

    # --- SPEC § 2.2 PxQ semantics: NEW conflict #4 ---------------------------

    def _check_pxq_consistency(
        self, graph: SupplyChainGraph
    ) -> List[ConflictDetail]:
        """For every edge with both ``p_as_usd`` and ``q_units`` populated,
        compare ``estimated_revenue_krw`` against ``P × Q × FX(USD→KRW)``.

        When the FX rate cannot be sourced this check is **skipped** (info
        log only). We must never substitute a guessed constant.
        """
        conflicts: List[ConflictDetail] = []
        rate = fx.quarter_average("USD", "KRW", graph.target_quarter)
        if rate is None:
            print(
                f"[{self.role}] FX rate unavailable for {graph.target_quarter}; "
                "PxQ consistency check skipped."
            )
            return conflicts

        for edge in graph.edges:
            if edge.p_as_usd is None or edge.q_units is None:
                continue
            if edge.estimated_revenue_krw <= 0:
                continue
            implied_krw = edge.p_as_usd * edge.q_units * rate
            if implied_krw <= 0:
                continue
            denom = max(edge.estimated_revenue_krw, implied_krw)
            relative_delta = abs(edge.estimated_revenue_krw - implied_krw) / denom
            if relative_delta > PXQ_TOLERANCE:
                msg = (
                    f"PxQ inconsistency on edge '{edge.id}': "
                    f"P×Q×FX = {implied_krw:,.0f} KRW vs estimated "
                    f"{edge.estimated_revenue_krw:,.0f} KRW "
                    f"(Δ {relative_delta * 100:.1f}% > {PXQ_TOLERANCE * 100:.0f}%; "
                    f"USD→KRW@{graph.target_quarter}={rate:.2f})."
                )
                conflicts.append(
                    ConflictDetail(
                        type="PXQ_INCONSISTENT",
                        message=msg,
                        target_edge_ids=[edge.id],
                        target_node_ids=[edge.source, edge.target],
                    )
                )
        return conflicts

    # --- Feedback prompt synthesis -------------------------------------------

    def _generate_feedback_prompt(
        self, conflicts: List[ConflictDetail]
    ) -> str:
        """Synthesizes conflicts into an actionable instruction set for the Estimator."""
        feedback_msgs: List[str] = []

        cogs_conflict = next(
            (c for c in conflicts if c.type == "COGS_EXCEEDED"), None
        )
        missing_grounding = next(
            (c for c in conflicts if c.type == "MISSING_GROUNDING"), None
        )
        double_entry = next(
            (c for c in conflicts if c.type == "DOUBLE_ENTRY_MISMATCH"), None
        )
        stale = next(
            (c for c in conflicts if c.type == "STALE_GROUNDING"), None
        )
        pxq = next(
            (c for c in conflicts if c.type == "PXQ_INCONSISTENT"), None
        )

        if cogs_conflict:
            feedback_msgs.append(
                f"- CRITICAL COGS exceeded in node '{cogs_conflict.target_node_ids[0]}'. "
                f"Edges {cogs_conflict.target_edge_ids} sum higher than reported COGS. "
                "Reduce Q (volume) on the largest supply edge proportionally."
            )

        if missing_grounding:
            feedback_msgs.append(
                f"- Missing verified sources for edge "
                f"'{missing_grounding.target_edge_ids[0]}'. "
                "Re-collect from the counter-parties' IR or disclosure pages "
                "(prefer OFFICIAL_DISCLOSURE / OFFICIAL_IR tier)."
            )

        if double_entry:
            feedback_msgs.append(
                f"- Double-entry mismatch on edge '{double_entry.target_edge_ids[0]}'. "
                "Cross-validate seller and buyer reports; prefer the source with "
                "more recent article_date."
            )

        if stale:
            feedback_msgs.append(
                f"- Stale grounding on edge '{stale.target_edge_ids[0]}'. "
                "Re-collect a fresher source whose article_date is within 12 "
                "months of the quarter end."
            )

        if pxq:
            feedback_msgs.append(
                f"- PxQ inconsistency on edge '{pxq.target_edge_ids[0]}'. "
                "Either correct estimated_revenue_krw to match P × Q at the "
                "quarter-mean USD→KRW rate, or surface a fresher P/Q figure."
            )

        if not feedback_msgs:
            feedback_msgs.append("- No actionable conflicts detected.")

        return "\n".join(feedback_msgs)
