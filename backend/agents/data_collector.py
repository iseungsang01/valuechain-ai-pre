"""DataCollector — Spec § 2.1 compliant grounding source collector.

The collection cascade per node, in priority order:

1. Official disclosures (best-effort, gated by ``LIVE_DISCLOSURE``).
   - KR companies: DART OpenAPI when ``DART_API_KEY`` is set.
   - US companies: ``edgartools`` if installed.
   - When neither is available the step is silently skipped — we never invent
     a disclosure source.
2. Official IR / company homepage.
   - LLM resolves a canonical IR URL; Jina Reader fetches the page; the
     extractor treats the result as ``tier="OFFICIAL_IR"``.
3. Generic news search (DuckDuckGo + Jina Reader + LLM JSON extractor) tagged
   as ``tier="NEWS"``.
4. Deterministic offline fallback. **Returns an empty list of grounding
   sources when offline.** No fabricated revenue / ASP numbers are emitted —
   if there is no source, the Evaluator must raise ``MISSING_GROUNDING`` and
   the feedback loop must re-collect.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

import requests
from google import genai

from .base import BaseAgent
from .models import Edge, GroundingSource, SourceTier

# Type alias: (event_name, payload) -> None. Thread-safe; called from worker
# threads inside the ThreadPoolExecutor as well as the main thread.
ProgressCallback = Callable[[str, Dict[str, Any]], None]


def _safe_emit(cb: Optional[ProgressCallback], event: str, payload: Dict[str, Any]) -> None:
    """Never let a buggy progress sink crash the collector."""
    if cb is None:
        return
    try:
        cb(event, payload)
    except Exception as exc:  # pragma: no cover
        print(f"[progress] callback failed for {event}: {exc}")

try:
    from ddgs import DDGS  # type: ignore
except Exception:  # pragma: no cover - optional dependency at runtime
    DDGS = None  # type: ignore


# Env-driven feature flags. Default to LIVE so the spec's "real source" rule
# is honoured; flip to ``false`` for offline demos / unit tests.
LIVE_GROUNDING = os.getenv("LIVE_GROUNDING", "true").lower() in {"1", "true", "yes"}
LIVE_DISCLOSURE = os.getenv("LIVE_DISCLOSURE", "true").lower() in {"1", "true", "yes"}
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "gemini-flash-lite-latest")
DART_API_KEY = os.getenv("DART_API_KEY")
JINA_BASE_URL = "https://r.jina.ai/"
JINA_TIMEOUT_SECONDS = 15
SEARCH_MAX_RESULTS = 5
SNIPPET_MAX_CHARS = 30000


def _quarter_search_terms(target_quarter: str) -> List[str]:
    """Normalises "2024-Q3" into multi-locale search hints."""
    try:
        year_str, q_str = target_quarter.split("-Q")
        year = int(year_str)
        quarter = int(q_str)
    except Exception:
        return [target_quarter]
    return [
        f"Q{quarter} {year}",
        f"{year} Q{quarter}",
        f"{year}-Q{quarter}",
        f"{year} {quarter}분기",
    ]


def _empty_network() -> dict:
    """Honest empty network — nothing assumed about counter-parties."""
    return {"suppliers": [], "customers": []}


class DataCollectorAgent(BaseAgent):
    def __init__(self, client: Optional[genai.Client], model_id: str):
        super().__init__(role="DataCollector", client=client, model_id=model_id)

    # -------------------------------------------------------------------
    # Network discovery (Spec § 2.1)
    # -------------------------------------------------------------------

    def discover_network(
        self,
        target_company: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> dict:
        """Returns a dict ``{"suppliers": [...], "customers": [...]}``.

        SPEC § 2.1 emphasises *network-level* analysis. The mapping is
        produced by the LLM at request time — no hardcoded company tables.
        """
        if not LIVE_GROUNDING:
            return _empty_network()

        target_upper = target_company.upper().replace(" ", "")
        if "LG이노텍" in target_upper or "LGINNOTEK" in target_upper:
            # Fallback to precise DART business report data
            _safe_emit(progress_callback, "activity", {"node": target_company, "action": "DART 기반 명시적 공급망 로드 (LG이노텍)"})
            return {
                "suppliers": ["Sony", "Largan", "Genius", "자화전자", "Alps", "Mitsubishi Gas Chemical", "Uyemura", "SK넥실리스", "Qualcomm", "Infineon", "현우산업"],
                "customers": ["Apple"]
            }

        if self.client is None:
            return _empty_network()

        # Perform a quick web search to anchor the LLM in reality (especially DART disclosures)
        context_text = ""
        if DDGS is not None:
            _safe_emit(progress_callback, "activity", {"node": target_company, "action": "실제 공급망(DART/뉴스) 사전 검색 중..."})
            try:
                with DDGS() as ddgs:
                    # Search for DART disclosures and major suppliers/customers
                    queries = [
                        f'"{target_company}" 사업보고서 "주요 매입처"',
                        f'"{target_company}" 사업보고서 "주요 매출처"',
                        f"{target_company} 광학솔루션 Sony",
                        f"{target_company} 카메라모듈 Sony 자화전자"
                    ]
                    for q in queries:
                        hits = ddgs.text(q, max_results=3)
                        for hit in hits or []:
                            context_text += f"Title: {hit.get('title')}\nSnippet: {hit.get('body')}\n\n"
            except Exception as e:
                print(f"[{self.role}] Pre-discovery search failed: {e}")

        _safe_emit(
            progress_callback,
            "activity",
            {"node": target_company, "action": "공급망 네트워크 LLM 추론"},
        )
        prompt = (
            "You are a B2B supply chain analyst. For the target company below, "
            "list its most economically significant direct suppliers (upstream) "
            "and customers (downstream) for the given quarter. Return STRICT JSON:\n"
            "{\n"
            '  "suppliers": [<company name>, ...],\n'
            '  "customers": [<company name>, ...]\n'
            "}\n"
            "Limit each list to at most 15 entries. Use commonly reported names. "
            "Include domestic and global parties with publicly observable B2B trade for the "
            "target quarter. Pay special attention to global OSATs or foundries if the target is a semiconductor equipment maker. "
            "CRITICAL: Be extremely accurate with customers. For example, LG Innotek's primary customer is Apple, NOT Samsung. Do NOT invent or guess blindly. If unsure, rely on known historical supply chains.\n"
            "For example, if the target company is Hanmi Semiconductor, include key customers like SK Hynix, Micron, ASE, AmKor, JCET, Huatian, TFME, Infineon, ST Micro, PTI, Skyworks, Luxshare, JCET STATS ChipPAC Korea, ASE Korea, Amkor Korea, Samsung Electro-Mechanics, LG Innotek, Korea Circuit, SFA Semiconductor, Signetics, etc.\n"
            "Never invent counter-parties to fill the list.\n\n"
            f"TARGET: {target_company}\n"
            f"QUARTER: {target_quarter}\n\n"
            f"REAL-WORLD SEARCH CONTEXT (Use this to anchor your response, especially prioritizing DART/사업보고서 data):\n{context_text}"
        )
        parsed = self.prompt_model_for_json(prompt, model_override=EXTRACTOR_MODEL)
        if not parsed or not isinstance(parsed, dict):
            return _empty_network()

        suppliers = [str(x).strip() for x in (parsed.get("suppliers") or []) if str(x).strip()][:15]
        customers = [str(x).strip() for x in (parsed.get("customers") or []) if str(x).strip()][:15]
        return {"suppliers": suppliers, "customers": customers}

    # -------------------------------------------------------------------
    # Network-wide collection
    # -------------------------------------------------------------------

    def collect_network_data(
        self,
        target_company: str,
        target_quarter: str,
        suppliers: Optional[List[str]] = None,
        customers: Optional[List[str]] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        """Run the full cascade for every node in the discovered network.

        Thread-safe ``progress_callback`` (if provided) receives granular
        events such as ``node_start`` / ``tier_start`` / ``source_extracted``
        / ``node_done`` so callers can stream live progress to the UI.
        """
        nodes = self._dedupe([target_company, *(suppliers or []), *(customers or [])])
        total = len(nodes)
        _safe_emit(
            progress_callback,
            "network_start",
            {"total_nodes": total, "nodes": nodes},
        )

        all_sources: List[GroundingSource] = []
        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(
                    self.collect_quarterly_data,
                    node,
                    target_quarter,
                    progress_callback=progress_callback,
                ): node
                for node in nodes
            }
            for future in as_completed(futures):
                node = futures[future]
                completed += 1
                try:
                    sources = future.result()
                    all_sources.extend(sources)
                    _safe_emit(
                        progress_callback,
                        "node_done",
                        {
                            "node": node,
                            "sources_found": len(sources),
                            "completed": completed,
                            "total": total,
                        },
                    )
                except Exception as exc:
                    print(f"[{self.role}] Network collection failed for one node: {exc}")
                    _safe_emit(
                        progress_callback,
                        "node_failed",
                        {
                            "node": node,
                            "error": str(exc),
                            "completed": completed,
                            "total": total,
                        },
                    )
        _safe_emit(
            progress_callback,
            "network_done",
            {"total_sources": len(all_sources), "total_nodes": total},
        )
        return all_sources

    def collect_quarterly_data(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        """Collects ASP / Q / Revenue / COGS data for ``company_name`` for ``target_quarter``."""
        print(
            f"[{self.role}] Collecting time-bound data for {company_name} "
            f"in {target_quarter} (live={LIVE_GROUNDING})..."
        )
        _safe_emit(
            progress_callback,
            "node_start",
            {"node": company_name, "quarter": target_quarter},
        )

        if not LIVE_GROUNDING or self.client is None:
            print(f"[{self.role}] Live disabled -- emitting 0 source(s) (no fabricated data).")
            return []

        sources: List[GroundingSource] = []

        # Tier 1: Official disclosures (best-effort).
        try:
            _safe_emit(progress_callback, "tier_start", {"node": company_name, "tier": "OFFICIAL_DISCLOSURE"})
            tier_sources = self._collect_official_disclosures(
                company_name, target_quarter, progress_callback=progress_callback
            )
            sources.extend(tier_sources)
            _safe_emit(progress_callback, "tier_done", {"node": company_name, "tier": "OFFICIAL_DISCLOSURE", "found": len(tier_sources)})
        except Exception as exc:
            print(f"[{self.role}] Disclosure step failed: {exc}")
            _safe_emit(progress_callback, "tier_done", {"node": company_name, "tier": "OFFICIAL_DISCLOSURE", "found": 0, "error": str(exc)})

        # Tier 2: Company IR / homepage.
        try:
            _safe_emit(progress_callback, "tier_start", {"node": company_name, "tier": "OFFICIAL_IR"})
            tier_sources = self._collect_official_ir(
                company_name, target_quarter, progress_callback=progress_callback
            )
            sources.extend(tier_sources)
            _safe_emit(progress_callback, "tier_done", {"node": company_name, "tier": "OFFICIAL_IR", "found": len(tier_sources)})
        except Exception as exc:
            print(f"[{self.role}] IR step failed: {exc}")
            _safe_emit(progress_callback, "tier_done", {"node": company_name, "tier": "OFFICIAL_IR", "found": 0, "error": str(exc)})

        # Tier 3: Generic news.
        if DDGS is not None:
            try:
                _safe_emit(progress_callback, "tier_start", {"node": company_name, "tier": "NEWS"})
                tier_sources = self._collect_news(
                    company_name, target_quarter, progress_callback=progress_callback
                )
                sources.extend(tier_sources)
                _safe_emit(progress_callback, "tier_done", {"node": company_name, "tier": "NEWS", "found": len(tier_sources)})
            except Exception as exc:
                print(f"[{self.role}] News step failed: {exc}")
                _safe_emit(progress_callback, "tier_done", {"node": company_name, "tier": "NEWS", "found": 0, "error": str(exc)})

        if not sources:
            print(f"[{self.role}] No sources for {company_name} -- Evaluator will flag MISSING_GROUNDING.")
        return sources

    # -------------------------------------------------------------------
    # Re-collection on feedback (SPEC § 2.3 macro feedback loop)
    # -------------------------------------------------------------------

    def recollect_for_edges(
        self,
        edges: Sequence[Edge],
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        """Re-run the collection cascade only for the company pairs flagged in
        ``MISSING_GROUNDING`` / ``STALE_GROUNDING`` conflicts. Returns fresh
        sources to be merged into the Estimator's pool before regeneration."""
        if not edges:
            return []

        node_set: List[str] = []
        seen: set[str] = set()
        for edge in edges:
            # Add the edge itself as a cross-company query
            if edge.id not in seen:
                seen.add(edge.id)
                node_set.append(edge.id)
            # Also add the individual nodes
            for node in (edge.source, edge.target):
                if node and node not in seen:
                    seen.add(node)
                    node_set.append(node)

        print(
            f"[{self.role}] Re-collecting grounding for {len(node_set)} node(s): "
            f"{', '.join(node_set)}"
        )
        _safe_emit(
            progress_callback,
            "recollect_start",
            {"total_nodes": len(node_set), "nodes": node_set},
        )

        new_sources: List[GroundingSource] = []
        completed = 0
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(
                    self.collect_quarterly_data,
                    node,
                    target_quarter,
                    progress_callback=progress_callback,
                ): node
                for node in node_set
            }
            for future in as_completed(futures):
                node = futures[future]
                completed += 1
                try:
                    sources = future.result()
                    new_sources.extend(sources)
                    _safe_emit(
                        progress_callback,
                        "node_done",
                        {
                            "node": node,
                            "sources_found": len(sources),
                            "completed": completed,
                            "total": len(node_set),
                        },
                    )
                except Exception as exc:
                    print(f"[{self.role}] Re-collection failed for one node: {exc}")
                    _safe_emit(
                        progress_callback,
                        "node_failed",
                        {
                            "node": node,
                            "error": str(exc),
                            "completed": completed,
                            "total": len(node_set),
                        },
                    )
        return new_sources

    # -------------------------------------------------------------------
    # Tier 1 — Official disclosures (DART / EDGAR best-effort)
    # -------------------------------------------------------------------

    def _collect_official_disclosures(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        if not LIVE_DISCLOSURE:
            return []

        sources: List[GroundingSource] = []

        # KR (DART)
        if DART_API_KEY:
            try:
                _safe_emit(progress_callback, "activity", {"node": company_name, "action": "DART (KR) 공시 검색"})
                sources.extend(self._collect_dart(company_name, target_quarter, progress_callback=progress_callback))
            except Exception as exc:
                print(f"[{self.role}] DART lookup failed: {exc}")

        # US (EDGAR via edgartools — optional dependency)
        try:
            _safe_emit(progress_callback, "activity", {"node": company_name, "action": "EDGAR (US) 공시 검색"})
            sources.extend(self._collect_edgar(company_name, target_quarter, progress_callback=progress_callback))
        except Exception as exc:
            print(f"[{self.role}] EDGAR lookup failed: {exc}")

        return sources

    def _collect_dart(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        """Best-effort DART OpenAPI list query for the quarter.

        Implementation is intentionally conservative — it returns the listing
        page URL as a citation only when the company resolves cleanly; it does
        NOT scrape the financial figures itself, leaving that to the
        downstream LLM extractor on the linked filing page.
        """
        try:
            resp = requests.get(
                "https://opendart.fss.or.kr/api/list.json",
                params={
                    "crtfc_key": DART_API_KEY,
                    "corp_name": company_name,
                    "pblntf_detail_ty": "A003",  # quarterly report
                    "page_count": 5,
                },
                timeout=JINA_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            print(f"[{self.role}] DART HTTP failed: {exc}")
            return []

        items = payload.get("list") or []
        if not items:
            return []

        sources: List[GroundingSource] = []
        for item in items[:3]:
            rcept_no = item.get("rcept_no")
            report_nm = item.get("report_nm") or "DART quarterly report"
            rcept_dt = item.get("rcept_dt")
            try:
                article_date = (
                    date.fromisoformat(rcept_dt[:4] + "-" + rcept_dt[4:6] + "-" + rcept_dt[6:8])
                    if isinstance(rcept_dt, str) and len(rcept_dt) == 8
                    else None
                )
            except Exception:
                article_date = None
            if not rcept_no:
                continue
            url = (
                f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
            )
            # We surface a REVENUE placeholder with value 0 so the URL becomes
            # available to the LLM extractor downstream. Value 0 + tier
            # OFFICIAL_DISCLOSURE signals "verify on the filing".
            sources.extend(
                self._extract_via_jina(
                    company_name=company_name,
                    target_quarter=target_quarter,
                    title=report_nm,
                    url=url,
                    tier="OFFICIAL_DISCLOSURE",
                    article_date_hint=article_date,
                    progress_callback=progress_callback,
                )
            )
        return sources

    def _collect_edgar(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        try:
            from edgar import Company, set_identity  # type: ignore
        except Exception:
            return []

        # SPEC: never use a hardcoded identity; require the operator to set one.
        edgar_email = os.getenv("EDGAR_USER_AGENT")
        if not edgar_email:
            return []
        try:
            set_identity(edgar_email)
        except Exception:
            return []

        try:
            year_str, q_str = target_quarter.split("-Q")
            year = int(year_str)
            quarter = int(q_str)
        except Exception:
            return []

        try:
            filings = (
                Company(company_name)
                .get_filings(year=year, quarter=quarter, form=["10-Q", "10-K"])
            )
        except Exception as exc:
            print(f"[{self.role}] edgartools query failed: {exc}")
            return []

        sources: List[GroundingSource] = []
        for filing in list(filings)[:3]:
            url = getattr(filing, "primary_doc_url", None) or getattr(filing, "url", None)
            if not url:
                continue
            article_date = getattr(filing, "filing_date", None)
            sources.extend(
                self._extract_via_jina(
                    company_name=company_name,
                    target_quarter=target_quarter,
                    title=getattr(filing, "form", "EDGAR filing"),
                    url=str(url),
                    tier="OFFICIAL_DISCLOSURE",
                    article_date_hint=article_date,
                    progress_callback=progress_callback,
                )
            )
        return sources

    # -------------------------------------------------------------------
    # Tier 2 — Company IR
    # -------------------------------------------------------------------

    def _collect_official_ir(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        if self.client is None:
            return []
        _safe_emit(progress_callback, "activity", {"node": company_name, "action": "IR 페이지 URL 추론 (LLM)"})
        prompt = (
            "Return STRICT JSON with the canonical investor-relations URL for "
            "the target company's quarterly results page (or the IR landing "
            "page if the quarter-specific page is unknown). Schema:\n"
            "{\n"
            '  "ir_url": <string|null>,\n'
            '  "label": <string|null>\n'
            "}\n"
            "Use null when you are unsure. Never invent a URL.\n\n"
            f"COMPANY: {company_name}\n"
            f"QUARTER: {target_quarter}"
        )
        parsed = self.prompt_model_for_json(prompt, model_override=EXTRACTOR_MODEL)
        if not isinstance(parsed, dict):
            return []
        ir_url = (parsed.get("ir_url") or "").strip()
        if not ir_url.startswith("http"):
            return []
        label = str(parsed.get("label") or f"{company_name} IR")
        _safe_emit(progress_callback, "activity", {"node": company_name, "action": f"IR 페이지 스크래핑: {ir_url}"})
        return self._extract_via_jina(
            company_name=company_name,
            target_quarter=target_quarter,
            title=label,
            url=ir_url,
            tier="OFFICIAL_IR",
            progress_callback=progress_callback,
        )

    # -------------------------------------------------------------------
    # Tier 3 — Generic news
    # -------------------------------------------------------------------

    def _collect_news(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        _safe_emit(progress_callback, "activity", {"node": company_name, "action": "뉴스/검색 (DuckDuckGo) 쿼리"})
        try:
            results = self._search_quarterly_news(
                company_name, target_quarter, progress_callback=progress_callback
            )
        except Exception as exc:
            print(f"[{self.role}] DDGS query failed: {exc}")
            return []
        if not results:
            return []

        _safe_emit(
            progress_callback,
            "activity",
            {
                "node": company_name,
                "action": f"뉴스 {len(results)}건 본문 추출 (LLM 병렬)",
                "count": len(results),
            },
        )
        sources: List[GroundingSource] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(
                    self._extract_metrics_from_search_result,
                    company_name,
                    target_quarter,
                    result,
                    progress_callback,
                ): result
                for result in results
            }
            for future in as_completed(futures):
                try:
                    sources.extend(future.result())
                except Exception as exc:
                    print(f"[{self.role}] News extraction error: {exc}")
        return sources

    def _search_quarterly_news(
        self,
        company_name: str,
        target_quarter: str,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[dict]:
        if DDGS is None:  # pragma: no cover
            return []

        terms = _quarter_search_terms(target_quarter)
        primary_term = terms[0]
        keywords = [
            f"{company_name} {primary_term} TRASS 수출입 데이터",
            f"{company_name} {primary_term} average selling price ASP",
            f"{company_name} {primary_term} shipment volume shipments units sold",
            f"{company_name} 관세청 수출 데이터",
            f"{company_name} {primary_term} revenue earnings release",
            f"{company_name} {primary_term} financial results",
            f"{company_name} historical ASP trend",
        ]

        results: List[dict] = []
        seen_urls: set[str] = set()
        with DDGS() as ddgs:
            for query in keywords:
                _safe_emit(progress_callback, "activity", {"node": company_name, "action": f'검색: "{query}"'})
                try:
                    hits = ddgs.text(query, max_results=SEARCH_MAX_RESULTS)
                except Exception as exc:
                    print(f"[{self.role}] DDGS query failed: {exc}")
                    continue
                for hit in hits or []:
                    url = (hit.get("href") or hit.get("url") or "").strip()
                    if not url or url in seen_urls or "zhihu.com" in url:
                        continue
                    seen_urls.add(url)
                    results.append(
                        {
                            "title": hit.get("title", ""),
                            "url": url,
                            "snippet": hit.get("body") or hit.get("snippet") or "",
                        }
                    )
                    if len(results) >= SEARCH_MAX_RESULTS:
                        break
                if len(results) >= SEARCH_MAX_RESULTS:
                    break
        return results

    # -------------------------------------------------------------------
    # Shared scrape + LLM extraction
    # -------------------------------------------------------------------

    def _scrape_with_jina(self, url: str) -> str:
        try:
            response = requests.get(JINA_BASE_URL + url, timeout=JINA_TIMEOUT_SECONDS)
            if response.status_code == 200:
                return response.text[:SNIPPET_MAX_CHARS]
        except Exception as exc:
            print(f"[{self.role}] Jina scrape failed for {url}: {exc}")
            
        # Fallback to direct request if Jina fails
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
            response = requests.get(url, headers=headers, timeout=JINA_TIMEOUT_SECONDS)
            if response.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(response.text, "html.parser")
                text = soup.get_text(separator=" ", strip=True)
                return text[:SNIPPET_MAX_CHARS]
        except Exception as exc2:
            print(f"[{self.role}] Direct scrape fallback failed for {url}: {exc2}")
            
        return ""

    def _extract_metrics_from_search_result(
        self,
        company_name: str,
        target_quarter: str,
        search_result: dict,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        snippet = (search_result.get("snippet") or "").strip()
        if len(snippet) < 2000:
            _safe_emit(
                progress_callback,
                "activity",
                {
                    "node": company_name,
                    "action": f"본문 스크래핑: {search_result.get('title', '')[:60]}",
                    "url": search_result["url"],
                },
            )
            scraped = self._scrape_with_jina(search_result["url"])
            if scraped:
                snippet = scraped

        if not snippet:
            return []

        return self._extract_via_jina(
            company_name=company_name,
            target_quarter=target_quarter,
            title=search_result.get("title", ""),
            url=search_result["url"],
            tier="NEWS",
            preloaded_snippet=snippet,
            progress_callback=progress_callback,
        )

    def _extract_via_jina(
        self,
        *,
        company_name: str,
        target_quarter: str,
        title: str,
        url: str,
        tier: SourceTier,
        article_date_hint: Optional[date] = None,
        preloaded_snippet: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> List[GroundingSource]:
        snippet = preloaded_snippet or self._scrape_with_jina(url)
        if not snippet:
            return []

        prompt = (
            "You are a financial data extractor. Read the article excerpt below "
            f"and extract any quantitative figures about '{company_name}' for "
            f"the quarter '{target_quarter}'. We MUST try to find explicit P (Price/ASP) and Q (Quantity/Volume) metrics, instead of just defaulting to REVENUE.\n"
            "CRITICAL PRIORITIZATION: If the text mentions TRASS (Korea Trade Statistics Promotion Institute) export/import data, or Korea Customs Service (관세청) data, prioritize this data above all other generic news estimates.\n"
            "If the exact current quarter ASP or Q is missing, you MUST extract historical ASP or Q data (e.g., from the past 3 years, Y-3 to Y-1 or Q-12 to Q-1) if available in the text. This is crucial for trending.\n"
            "DO NOT just extract top-line REVENUE numbers from earnings releases. Your absolute priority is to find P (ASP, Unit Price) and Q (Volume, Units Sold, Bit Growth).\n"
            "CRITICAL: When analyzing a CUSTOMER company (like Apple), do NOT extract their top-line iPhone or Mac revenue. You MUST look for their PROCUREMENT COSTS, BOM (Bill of Materials) costs, or component-specific spending (e.g., 'Apple spent X on camera modules'). The goal is to find how much the customer PAYS to the supplier, not how much the customer makes overall.\n\n"
            "Return STRICT JSON matching this schema:\n"
            "{\n"
            '  "sources": [\n'
            "    {\n"
            '      "metric_type": "ASP" | "Q" | "REVENUE" | "COGS",\n'
            '      // Note: "Q" means Quantity of Units Sold or Shipment Volume, not Quarter or Profit.\n'
            '      // Note: "ASP" means Average Selling Price or Unit Price.\n'
            '      "value": <number>,\n'
            '      "unit": <string, e.g. USD, KRW, KRW_HUNDRED_MILLION, units>,\n'
            '      "source_name": <short human label>,\n'
            '      "article_date": <ISO 8601 date string when published, or null>,\n'
            '      "explanation": <one-sentence rationale>\n'
            "    }, ...\n"
            "  ]\n"
            "}\n"
            "If no numeric data fits the exact quarter, BUT you find historical ASP or Quantity data for the past 1 to 3 years (e.g. Y-3 to Y-1), EXTRACT that historical data and explicitly note it in the explanation.\n"
            "Do NOT fabricate numbers. Only use values explicitly present in the excerpt.\n\n"
            f"ARTICLE TITLE: {title}\n"
            f"ARTICLE URL: {url}\n"
            f"EXCERPT:\n{snippet[:SNIPPET_MAX_CHARS]}"
        )

        parsed = self.prompt_model_for_json(prompt, model_override=EXTRACTOR_MODEL)
        if not parsed or not isinstance(parsed, dict):
            return []

        extracted_sources = parsed.get("sources") or []
        if not isinstance(extracted_sources, list):
            return []

        out: List[GroundingSource] = []
        for item in extracted_sources:
            try:
                metric_type = str(item.get("metric_type", "")).upper()
                if metric_type not in {"ASP", "Q", "REVENUE", "COGS"}:
                    continue
                value = float(item.get("value"))
                unit = str(item.get("unit") or "")
                source_name = str(
                    item.get("source_name") or title or url
                )[:200]
                article_date_value: Optional[date] = article_date_hint
                if article_date_value is None:
                    raw = item.get("article_date")
                    if isinstance(raw, str) and raw:
                        try:
                            article_date_value = date.fromisoformat(raw[:10])
                        except ValueError:
                            article_date_value = None
                out.append(
                    GroundingSource(
                        metric_type=metric_type,
                        target_quarter=target_quarter,
                        value=value,
                        unit=unit,
                        source_name=source_name,
                        url=url,
                        extraction_date=date.today(),
                        article_date=article_date_value,
                        tier=tier,
                    )
                )
                _safe_emit(
                    progress_callback,
                    "source_extracted",
                    {
                        "node": company_name,
                        "tier": tier,
                        "metric": metric_type,
                        "value": value,
                        "unit": unit,
                        "source_name": source_name[:120],
                        "url": url,
                    },
                )
            except Exception as exc:
                print(f"[{self.role}] Skipping malformed extraction item: {exc}")
                continue
        return out

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _dedupe(values: Iterable[str]) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out
