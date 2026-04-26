# ValueChain AI - SPEC/AGENT Alignment Changelog

Status: APPROVED by Momus (2026-04-26, 57s review). P2 frontend pulled into scope per user follow-up.
Owner: Sisyphus
Date: 2026-04-26
Scope decision (confirmed by user across two turns):
- **P0 + P1 backend**: remove hardcoded supply-chain mappings, remove implicit FX assumptions, prefer company-IR/official sources over generic web search, wire feedback-loop re-collection.
- **P2 frontend (in-scope as of follow-up)**: edge-click detail panel with P×Q calculation, `[n]`-style source citations with hover tooltip, edge stroke-width proportional to estimated revenue, and a quarter slider that reflects the active analysis. Backend types stay additive so the contract is forward-compatible.

---

## 1. Why this exists

`AGENT.md` and `SPEC.md` describe ValueChain AI as a quarterly, network-wide, source-grounded supply-chain estimator with a self-reflection feedback loop. Audit of the current code found that the demo path silently substitutes hardcoded data and never converts USD↔KRW, so the product's core value proposition is not actually being delivered:

- `backend/agents/data_collector.py:67-79` `_fallback_network` hardcodes SK Hynix→{TSMC, "Other Suppliers"} / {NVIDIA, Apple} and TSMC→{ASML, Tokyo Electron} / {NVIDIA, Apple, AMD}.
- `backend/agents/data_collector.py:82-128` `_deterministic_fallback` injects fixed numbers (175,731 KRW_HUNDRED_MILLION, ASP=150 USD, TSMC 30,000 KRW) and IR URLs as if they were grounded.
- `backend/agents/estimator.py:50-107` `_deterministic_graph` ships a fixed 4-node, 3-edge graph for `2024-Q3` with revenue 30,000 / 90,000 / 80,000 KRW, P=150 USD, Q=600,000 - this is what the current "demo" actually renders.
- `backend/agents/evaluator.py` compares `estimated_revenue_krw` against itself only; no FX, so `p_as_usd × q_units` is never validated against KRW totals.
- IR / 공시 / DART / SEC code paths do not exist; only static URLs in `_deterministic_fallback`.
- Feedback loop in `backend/main.py:149-204` re-runs Estimator only - DataCollector is never re-invoked, so `MISSING_GROUNDING` and `STALE_GROUNDING` can never resolve.
- `GroundingSource.extraction_date` is used as the freshness anchor, but live extractor sets it to `date.today()`, which makes year-old articles look fresh.

Combined effect: the system can pass smoke tests while silently ignoring SPEC §2.1 (time-bound grounding), §2.2 (PxQ double-entry), and §2.3 (macro feedback loop).

---

## 2. Out-of-scope (this patch)

- Replacing the entire LLM call path (Gemini → other) -> not in scope.
- Persisting collected sources between sessions / vector store -> not in scope.
- Real-time multi-quarter comparison (would require backend to fan out across quarters) -> not in scope; the quarter slider only changes which single quarter the next analysis targets.

---

## 3. Non-goals

- Do **not** add any third-party API key as a hard dependency. FX uses the no-key Frankfurter / ECB feed; DART and EDGAR integrations are best-effort and gated.
- Do **not** delete `LIVE_GROUNDING` / `LIVE_ESTIMATION` flags. They must keep working as offline kill-switches for the demo, but offline must produce **clearly-flagged** empty / synthetic data, never plausible fake numbers.

---

## 4. Architecture changes

### 4.1 New module: `backend/agents/fx.py`

- Public surface:
  - `quarter_average(base: str, quote: str, target_quarter: str) -> Optional[float]`
  - `convert(amount: float, from_ccy: str, to_ccy: str, target_quarter: str) -> Optional[float]`
- Implementation:
  - Resolves quarter to `[start_date, end_date]`.
  - Calls `https://api.frankfurter.dev/v2/rates?from={base}&to={quote}&start_date={start}&end_date={end}` (no key, ECB-backed).
  - Falls back to ECB legacy XML feed `https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml` (cross via EUR) if Frankfurter is unreachable.
  - Returns `None` (never a guessed constant) when both fail. Caller decides what to do; Evaluator must NOT fabricate a rate.
- Cache: in-process LRU keyed by `(base, quote, target_quarter)` to avoid hitting Frankfurter twice per request.
- Env flag: `LIVE_FX` (default `true`). When `false`, returns `None` from every call so unit tests stay offline-safe.

### 4.2 Extend `GroundingSource` (models.py)

- Add `article_date: Optional[date] = None` - the publication date of the underlying article / filing. Used for freshness checks. `extraction_date` keeps its current meaning (when *we* fetched the page).
- Add `tier: Literal["OFFICIAL_DISCLOSURE", "OFFICIAL_IR", "NEWS", "FALLBACK"] = "NEWS"` so the UI and Evaluator can prefer authoritative sources and so we can flag fallback rows clearly.
- Add new ConflictType `PXQ_INCONSISTENT`.

### 4.3 Rework `DataCollectorAgent` (data_collector.py)

Flow becomes a strict cascade per node:

1. **Official disclosures (best-effort, gated by `LIVE_DISCLOSURE`, default `true`)**
   - KR companies: query DART OpenAPI list endpoint with `pblntf_detail_ty=A003` for the target quarter when `DART_API_KEY` is present. If the key is absent, log a warning and skip (do not invent data).
   - US companies: use `edgartools` if installed (`get_filings(year, quarter, form=("10-Q","10-K"))`). If not installed, skip.
2. **Official IR / company homepage**
   - Resolve homepage by LLM ("What is the canonical investor-relations URL for X?"); fetch via Jina; tier=`OFFICIAL_IR`.
   - This step replaces the old `_fallback_network` SK-Hynix/TSMC special-cases.
3. **Generic news (existing DDGS + Jina + LLM extractor)** - unchanged but tier=`NEWS`.
4. **Fallback** - returns an **empty** list of `GroundingSource` and a single `tier="FALLBACK"` placeholder if nothing else worked. **No fabricated numbers.**

`discover_network`:
- Replace `_fallback_network`'s SK-Hynix/TSMC if-branches with a pure LLM call. If the LLM fails, return `{"suppliers": [], "customers": []}`. Downstream code must handle empty lists.

`collect_quarterly_data`:
- Threads `target_quarter` into every prompt and forces the extractor to also output `article_date` (ISO 8601). Drop sources whose `article_date` is outside the quarter window unless the source is REVENUE/COGS for the same quarter (filings are published a few weeks after the quarter ends).

New helper:
- `recollect_for_edges(edges: List[Edge], target_quarter: str) -> List[GroundingSource]` - used by the feedback loop. Re-runs collection only for the company pairs flagged in `MISSING_GROUNDING` or `STALE_GROUNDING` conflicts.

### 4.4 Rework `EstimatorAgent` (estimator.py)

- **Delete** the SK-Hynix/TSMC/Apple/NVIDIA branch in `_deterministic_graph`. Replace with a generic "skeleton" graph builder that takes `(target_node, suppliers, customers)` from the discovery step and emits empty `estimated_revenue_krw=0` edges so the evaluator can flag `MISSING_GROUNDING` honestly.
- LLM prompt is updated to require, for each edge, the FX-implied check: edges that include `p_as_usd` and `q_units` must include `expected_revenue_local_currency` and the `currency` they used.
- `regenerate_graph`: when the conflict list contains `PXQ_INCONSISTENT`, rebalance toward the FX-converted value rather than the LLM number.

### 4.5 Rework `EvaluatorAgent` (evaluator.py)

- `_check_grounding_freshness` uses `article_date or extraction_date` and reads the threshold from `MAX_GROUNDING_AGE_DAYS` (unchanged) but anchored to the **quarter end**, not "today".
- Add `_check_pxq_consistency`:
  - For every edge with `p_as_usd` and `q_units` set, compute `expected_krw = p_as_usd * q_units * fx.quarter_average("USD","KRW",graph.target_quarter)`.
  - If `fx.quarter_average` returns `None`, **skip** the check and emit a single info-level log line - no conflict raised.
  - If `abs(estimated_revenue_krw - expected_krw) / max(estimated_revenue_krw, expected_krw) > 0.25`, raise `PXQ_INCONSISTENT`.
- COGS check stays KRW-only; that part is already self-consistent.

### 4.6 Rework `main.py` feedback loop

- After `validation = evaluator.evaluate_graph(graph)`:
  - If conflicts contain `MISSING_GROUNDING` or `STALE_GROUNDING`, call `data_collector.recollect_for_edges(...)` and merge the new sources into the pool **before** calling `estimator.regenerate_graph`.
  - Emit a new SSE substep on the `FEEDBACK` event with `recollected_sources_count`. The frontend already accepts unknown extra fields, so no breaking change.

### 4.7 Frontend type sync (`frontend/types/index.ts`)

- `GroundingSource` gets `article_date?: string` and `tier?: "OFFICIAL_DISCLOSURE"|"OFFICIAL_IR"|"NEWS"|"FALLBACK"`.
- `ConflictType` union adds `"PXQ_INCONSISTENT"`.
- `FeedbackEventData` gets optional `recollected_sources_count?: number`.

These are additive - existing UI code keeps compiling.

### 4.8 P2 Frontend UI (`SPEC.md` §4)

- New component `frontend/components/SourceCitation.tsx`: renders an inline `[n]` chip; on hover/focus, shows a tooltip with `source_name`, `tier` badge, `article_date`, and a click-through link to `url`. Uses the existing zinc/emerald palette.
- New component `frontend/components/EdgeDetailPanel.tsx`: slides in from the right when an edge is selected. Shows `source → target`, the P × Q = revenue formula (rendered as `$P × Q = revenue` with proper units), conflict badges, and the list of grounding sources with tier-colored chips and `SourceCitation` references. When an edge has no `p_as_usd`/`q_units`, it falls back to "estimated_revenue_krw only" and explains the missing PxQ via an info banner.
- `frontend/components/SupplyChainGraph.tsx` updates:
  - Add `onEdgeClick` -> set selected edge id in parent state.
  - Compute `strokeWidth` in `computeLayout` proportional to `estimated_revenue_krw`. Use a clamped log scale so a 100x revenue gap renders as roughly 4x stroke. Conflict edges keep the dashed amber style on top.
  - Selected edge gets a brighter stroke + raised z-order; other edges fade slightly.
- `frontend/components/ControlBar.tsx`: keep the four quarter buttons but rename the section to "Quarter (analysis target)" and add a small caption ("선택한 분기로 다음 분석 실행"). Stays as buttons - a real range slider is out of scope because the backend analyses one quarter at a time.
- `frontend/app/page.tsx`: keeps `selectedQuarter` state (already exists), adds `selectedEdgeId` state, plumbs it into `SupplyChainGraph` and `EdgeDetailPanel`. Layout becomes a 3-pane grid (`graph | thought log` on top of an absolute-positioned `EdgeDetailPanel` that can be dismissed).
- A11y: the detail panel is keyboard-dismissable (Esc) and gets `role="dialog"` + `aria-labelledby`; the citation chip is a `button` with `aria-describedby` for the tooltip.
- Animation budget: re-use Framer Motion that's already imported in `ControlBar.tsx` and `ThoughtLog.tsx`. No new heavy deps.

Per `frontend/AGENTS.md` ("This is NOT the Next.js you know"), all new components are client components (`"use client"`) and avoid server-only imports.

---

## 5. File-by-file diff plan

| File | Change | Lines (current) |
|---|---|---|
| `backend/agents/models.py` | Add `article_date`, `tier` to `GroundingSource`; add `PXQ_INCONSISTENT` to `ConflictType` | 5-12, 38-49 |
| `backend/agents/fx.py` | New file. ~120 lines. | n/a |
| `backend/agents/data_collector.py` | Replace `_fallback_network` body (67-79); replace `_deterministic_fallback` body with empty list (82-128); rewrite `discover_network` (138-171) and `collect_quarterly_data` (209-255); add `recollect_for_edges`; update extractor prompt for `article_date` and `tier` (335-389) | 67-128, 138-255, 335-389 |
| `backend/agents/estimator.py` | Delete SK-Hynix/TSMC/Apple/NVIDIA branch in `_deterministic_graph` (57-99); replace with skeleton graph from inputs; update LLM prompt to require currency tag (170-188); regenerate_graph handles `PXQ_INCONSISTENT` (257-329) | 50-107, 160-251, 257-329 |
| `backend/agents/evaluator.py` | Use `article_date or extraction_date` (210-223); add `_check_pxq_consistency` and wire it after COGS check (60-69) | 60-69, 200-234 |
| `backend/main.py` | Feedback loop calls re-collection on grounding conflicts; SSE payload extended | 145-204 |
| `backend/requirements.txt` | Add `tenacity` (FX retry); make `dart-fss` and `edgartools` optional/extra | 1-9 |
| `backend/test_run.py` | Add Scenario 3 (PxQ via FX), Scenario 4 (re-collection unblocks `MISSING_GROUNDING`); Scenario 1 must continue to pass with empty fallback sources | full |
| `frontend/types/index.ts` | Additive type extensions (no logic changes) | 5-14, 45-50, 83-88 |
| `frontend/components/SourceCitation.tsx` | New file. Inline `[n]` chip + hover tooltip with grounding metadata. | n/a |
| `frontend/components/EdgeDetailPanel.tsx` | New file. Slide-in panel with P×Q formula, conflicts, grounding list. | n/a |
| `frontend/components/SupplyChainGraph.tsx` | Add `onEdgeClick`; dynamic strokeWidth (log scale) on `estimated_revenue_krw`; highlight selected edge. | 90-154, 186-232 |
| `frontend/components/ControlBar.tsx` | Reword quarter caption; no logic change. | 47-107 |
| `frontend/app/page.tsx` | Add `selectedEdgeId` state; render `EdgeDetailPanel`; pass click handler. | 11-52 |

---

## 6. Test strategy

1. `python backend/test_run.py` with `LIVE_GROUNDING=false`, `LIVE_FX=false`:
   - Scenario 1: empty sources, the resulting graph is a skeleton with `MISSING_GROUNDING` on every edge, evaluator emits exactly that conflict. **No fabricated revenue numbers anywhere in the output.**
   - Scenario 2: existing four-conflict-types coverage stays green (`COGS_EXCEEDED`, `MISSING_GROUNDING`, `DOUBLE_ENTRY_MISMATCH`, `STALE_GROUNDING`).
   - Scenario 3 (new): edge with `p_as_usd=2`, `q_units=10`, `estimated_revenue_krw=10` and a stubbed `fx.quarter_average` returning 1300 → `PXQ_INCONSISTENT` raised. `fx.quarter_average` returning `None` → conflict suppressed, info log only.
   - Scenario 4 (new): missing-grounding conflict triggers recollection; injectable mock collector returns one source for the missing edge; on retry, `MISSING_GROUNDING` is gone.
2. `npm run build` and `npm run lint` in `frontend/` stay green after the additive type changes **and** the P2 components.
2a. Manual smoke (documented in PR notes): clicking an edge opens the detail panel with the P×Q formula and at least one citation chip; pressing Esc closes it; toggling quarters changes only the next-analysis target, not the rendered graph.
3. Manual: `LIVE_GROUNDING=true LIVE_FX=true` end-to-end run is documented, but is **not** part of CI because it requires GEMINI_API_KEY + network egress.

---

## 7. Risk + rollback

- **Risk**: Frankfurter outage breaks PxQ check. **Mitigation**: skip the check, never invent FX. Evaluator must keep producing the other three conflict types unchanged.
- **Risk**: LLM discover_network returns nonsense supplier list. **Mitigation**: results are clamped to ≤5 entries each, all downstream code handles empty lists, every emitted source carries `tier` so the UI can dim non-authoritative entries.
- **Rollback**: revert by setting `LIVE_GROUNDING=false`, `LIVE_FX=false`, `LIVE_DISCLOSURE=false`. The system then runs in pure-skeleton mode and only the four existing conflict checks fire. No demo will silently fabricate numbers - that is intentional.

---

## 8. Open questions for Momus

1. Should `_deterministic_fallback` be deleted entirely (preferred) or kept as a `tier="FALLBACK"` no-op stub for backward compatibility with the smoke test? Current plan keeps the function but empties it; please confirm.
2. Is "skip the PxQ check when FX is unavailable" (vs. raise an `INFO`-level conflict) the right policy? Spec is silent.
3. Re-collection budget: current plan calls DataCollector at most once per feedback round, which combined with `MAX_RETRIES=2` means at most 2 extra collection passes. Should there be a hard wall-clock cap as well?
4. Frontend types are touched even though scope says "backend only". The alternative is shipping a backend that emits fields the frontend silently drops. Please confirm the additive type sync is OK.

---

## 9. Done criteria

- [ ] `data_collector.py` no longer contains `"SK Hynix"`, `"TSMC"`, `"NVIDIA"`, `"Apple"`, `"Other Suppliers"`, `175731`, `30000`, `150.0`, or any literal IR URL outside string templates.
- [ ] `estimator.py` no longer contains those names or literal revenue/ASP/Q numbers.
- [ ] `grep -n "1300\|0.78\|fx.*=.*[0-9]" backend/` returns only references inside `fx.py` tests.
- [ ] `python backend/test_run.py` passes all four scenarios.
- [ ] `npm run build` and `npm run lint` are green.
- [ ] No new `as any`, `@ts-ignore`, `@ts-expect-error` introduced.
- [ ] Selecting an edge in the dashboard opens the detail panel with the P×Q formula and source citations.
- [ ] Edge stroke width is visibly proportional to `estimated_revenue_krw`; conflict edges still render as dashed amber.
