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
from typing import Iterable, List, Optional, Sequence

import requests
from google import genai

from .base import BaseAgent
from .models import Edge, GroundingSource, SourceTier

try:
    from duckduckgo_search import DDGS  # type: ignore
except Exception:  # pragma: no cover - optional dependency at runtime
    DDGS = None  # type: ignore


# Env-driven feature flags. Default to LIVE so the spec's "real source" rule
# is honoured; flip to ``false`` for offline demos / unit tests.
LIVE_GROUNDING = os.getenv("LIVE_GROUNDING", "true").lower() in {"1", "true", "yes"}
LIVE_DISCLOSURE = os.getenv("LIVE_DISCLOSURE", "true").lower() in {"1", "true", "yes"}
EXTRACTOR_MODEL = os.getenv("EXTRACTOR_MODEL", "gemini-flash-lite-latest")
DART_API_KEY = os.getenv("DART_API_KEY")
JINA_BASE_URL = "https://r.jina.ai/"
JINA_TIMEOUT_SECONDS = 8
SEARCH_MAX_RESULTS = 5
SNIPPET_MAX_CHARS = 4000


def _quarter_search_terms(target_quarter: str) -> List[str]:
    """Normalises "2024-Q3" into multi-locale search hints."""
    try:
        year_str, q_str = target_quarter.split("-Q")
        year = int(year_str)
        quarter = int(q_str)
    except Exception:
        return [target_quarter]
    return [
        f"{year} {quarter}분기",
        f"{year} Q{quarter}",
        f"{year}-Q{quarter}",
        f"{year}년 {quarter}분기",
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
        self, target_company: str, target_quarter: str
    ) -> dict:
        """Returns a dict ``{"suppliers": [...], "customers": [...]}``.

        SPEC § 2.1 emphasises *network-level* analysis. The mapping is
        produced by the LLM at request time — no hardcoded company tables.
        """
        if not LIVE_GROUNDING or self.client is None:
            return _empty_network()

        prompt = (
            "You are a B2B supply chain analyst. For the target company below, "
            "list its most economically significant direct suppliers (upstream) "
            "and customers (downstream) for the given quarter. Return STRICT JSON:\n"
            "{\n"
            '  "suppliers": [<company name>, ...],\n'
            '  "customers": [<company name>, ...]\n'
            "}\n"
            "Limit each list to at most 5 entries. Use commonly reported names. "
            "Only include parties with publicly observable B2B trade for the "
            "target quarter. Never invent counter-parties to fill the list.\n\n"
            f"TARGET: {target_company}\n"
            f"QUARTER: {target_quarter}"
        )
        parsed = self.prompt_model_for_json(prompt, model_override=EXTRACTOR_MODEL)
        if not parsed or not isinstance(parsed, dict):
            return _empty_network()

        suppliers = [str(x).strip() for x in (parsed.get("suppliers") or []) if str(x).strip()][:5]
        customers = [str(x).strip() for x in (parsed.get("customers") or []) if str(x).strip()][:5]
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
    ) -> List[GroundingSource]:
        """Run the full cascade for every node in the discovered network."""
        nodes = self._dedupe([target_company, *(suppliers or []), *(customers or [])])

        all_sources: List[GroundingSource] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self.collect_quarterly_data, node, target_quarter): node
                for node in nodes
            }
            for future in as_completed(futures):
                try:
                    all_sources.extend(future.result())
                except Exception as exc:
                    print(f"[{self.role}] Network collection failed for one node: {exc}")
        return all_sources

    def collect_quarterly_data(
        self, company_name: str, target_quarter: str
    ) -> List[GroundingSource]:
        """Collects ASP / Q / Revenue / COGS data for ``company_name`` for ``target_quarter``."""
        print(
            f"[{self.role}] Collecting time-bound data for {company_name} "
            f"in {target_quarter} (live={LIVE_GROUNDING})..."
        )

        if not LIVE_GROUNDING or self.client is None:
            print(f"[{self.role}] Live disabled -- emitting 0 source(s) (no fabricated data).")
            return []

        sources: List[GroundingSource] = []

        # Tier 1: Official disclosures (best-effort).
        try:
            sources.extend(
                self._collect_official_disclosures(company_name, target_quarter)
            )
        except Exception as exc:
            print(f"[{self.role}] Disclosure step failed: {exc}")

        # Tier 2: Company IR / homepage.
        try:
            sources.extend(self._collect_official_ir(company_name, target_quarter))
        except Exception as exc:
            print(f"[{self.role}] IR step failed: {exc}")

        # Tier 3: Generic news.
        if DDGS is not None:
            try:
                sources.extend(self._collect_news(company_name, target_quarter))
            except Exception as exc:
                print(f"[{self.role}] News step failed: {exc}")

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
    ) -> List[GroundingSource]:
        """Re-run the collection cascade only for the company pairs flagged in
        ``MISSING_GROUNDING`` / ``STALE_GROUNDING`` conflicts. Returns fresh
        sources to be merged into the Estimator's pool before regeneration."""
        if not edges:
            return []

        node_set: List[str] = []
        seen: set[str] = set()
        for edge in edges:
            for node in (edge.source, edge.target):
                if node and node not in seen:
                    seen.add(node)
                    node_set.append(node)

        print(
            f"[{self.role}] Re-collecting grounding for {len(node_set)} node(s): "
            f"{', '.join(node_set)}"
        )

        new_sources: List[GroundingSource] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(self.collect_quarterly_data, node, target_quarter): node
                for node in node_set
            }
            for future in as_completed(futures):
                try:
                    new_sources.extend(future.result())
                except Exception as exc:
                    print(f"[{self.role}] Re-collection failed for one node: {exc}")
        return new_sources

    # -------------------------------------------------------------------
    # Tier 1 — Official disclosures (DART / EDGAR best-effort)
    # -------------------------------------------------------------------

    def _collect_official_disclosures(
        self, company_name: str, target_quarter: str
    ) -> List[GroundingSource]:
        if not LIVE_DISCLOSURE:
            return []

        sources: List[GroundingSource] = []

        # KR (DART)
        if DART_API_KEY:
            try:
                sources.extend(self._collect_dart(company_name, target_quarter))
            except Exception as exc:
                print(f"[{self.role}] DART lookup failed: {exc}")

        # US (EDGAR via edgartools — optional dependency)
        try:
            sources.extend(self._collect_edgar(company_name, target_quarter))
        except Exception as exc:
            print(f"[{self.role}] EDGAR lookup failed: {exc}")

        return sources

    def _collect_dart(
        self, company_name: str, target_quarter: str
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
                )
            )
        return sources

    def _collect_edgar(
        self, company_name: str, target_quarter: str
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
                )
            )
        return sources

    # -------------------------------------------------------------------
    # Tier 2 — Company IR
    # -------------------------------------------------------------------

    def _collect_official_ir(
        self, company_name: str, target_quarter: str
    ) -> List[GroundingSource]:
        if self.client is None:
            return []
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
        return self._extract_via_jina(
            company_name=company_name,
            target_quarter=target_quarter,
            title=label,
            url=ir_url,
            tier="OFFICIAL_IR",
        )

    # -------------------------------------------------------------------
    # Tier 3 — Generic news
    # -------------------------------------------------------------------

    def _collect_news(
        self, company_name: str, target_quarter: str
    ) -> List[GroundingSource]:
        try:
            results = self._search_quarterly_news(company_name, target_quarter)
        except Exception as exc:
            print(f"[{self.role}] DDGS query failed: {exc}")
            return []
        if not results:
            return []

        sources: List[GroundingSource] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(
                    self._extract_metrics_from_search_result,
                    company_name,
                    target_quarter,
                    result,
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
        self, company_name: str, target_quarter: str
    ) -> List[dict]:
        if DDGS is None:  # pragma: no cover
            return []

        terms = _quarter_search_terms(target_quarter)
        primary_term = terms[0]
        keywords = [
            f"{company_name} {primary_term} 매출",
            f"{company_name} {primary_term} 실적",
            f"{company_name} {primary_term} ASP",
            f"{company_name} {target_quarter} revenue earnings",
        ]

        results: List[dict] = []
        seen_urls: set[str] = set()
        with DDGS() as ddgs:
            for query in keywords:
                try:
                    hits = ddgs.text(query, max_results=SEARCH_MAX_RESULTS)
                except Exception as exc:
                    print(f"[{self.role}] DDGS query failed: {exc}")
                    continue
                for hit in hits or []:
                    url = (hit.get("href") or hit.get("url") or "").strip()
                    if not url or url in seen_urls:
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
        return ""

    def _extract_metrics_from_search_result(
        self,
        company_name: str,
        target_quarter: str,
        search_result: dict,
    ) -> List[GroundingSource]:
        snippet = (search_result.get("snippet") or "").strip()
        if len(snippet) < 200:
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
    ) -> List[GroundingSource]:
        snippet = preloaded_snippet or self._scrape_with_jina(url)
        if not snippet:
            return []

        prompt = (
            "You are a financial data extractor. Read the article excerpt below "
            f"and extract any quantitative figures about '{company_name}' for "
            f"the quarter '{target_quarter}'. Return STRICT JSON matching this schema:\n"
            "{\n"
            '  "sources": [\n'
            "    {\n"
            '      "metric_type": "ASP" | "Q" | "REVENUE" | "COGS",\n'
            '      "value": <number>,\n'
            '      "unit": <string, e.g. USD, KRW, KRW_HUNDRED_MILLION, units>,\n'
            '      "source_name": <short human label>,\n'
            '      "article_date": <ISO 8601 date string when published, or null>,\n'
            '      "explanation": <one-sentence rationale>\n'
            "    }, ...\n"
            "  ]\n"
            "}\n"
            "If no numeric data fits the company AND quarter, return {\"sources\": []}.\n"
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
