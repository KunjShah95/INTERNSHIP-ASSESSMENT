"""=== ResearchAgent ============================================================

ROLE:
  Gather live web data about a company from pluggable search providers.
  Returns normalized Source records. With no search key, returns empty list
  to signal "LLM-knowledge only" mode.

SYSTEM PROMPT (module identity):
  "I am the ResearchAgent. I run targeted web queries (company overview, recent
   news, financials) on the first available search provider (Exa → Tavily →
   Firecrawl). I clip results to fit context windows. I return structured Source
   records. I do nothing else."

CONTEXT:
  Inputs:  Company name (string), optional provider override
  Outputs: (list[Source], provider_used | None)
  Sources clipped to PER_SOURCE_CHARS = 1200, max MAX_SOURCES = 8

BOUNDARIES:
  I do NOT:
  - Generate any analysis, summaries, or reports
  - Make LLM calls
  - Cache data
  - Format or export anything
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass

from . import config

# Keep total context modest so free-tier models aren't blown past their window.
MAX_SOURCES = 6
PER_SOURCE_CHARS = 800


@dataclass
class Source:
    title: str
    url: str
    text: str

    def as_dict(self) -> dict:
        return asdict(self)


def _queries(company: str) -> list[str]:
    return [
        f"{company} company overview business",
        f"{company} recent news 2025 2026",
        f"{company} expansion projects financials revenue",
    ]


def _clip(text: str) -> str:
    text = (text or "").strip().replace("\n\n\n", "\n\n")
    return text[:PER_SOURCE_CHARS]


def _run_queries(queries: list[str], search_fn) -> list[Source]:
    """Run queries in parallel using a per-query callable."""
    out: list[Source] = []
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        futures = {pool.submit(search_fn, q): q for q in queries}
        for f in as_completed(futures):
            out.extend(f.result())
    return out


# ── provider adapters → list[Source] ──────────────────────────────────

def _exa(queries: list[str]) -> list[Source]:
    from exa_py import Exa

    client = Exa(api_key=os.environ["EXA_API_KEY"])

    def search(q: str) -> list[Source]:
        res = client.search_and_contents(q, num_results=2, text=True, type="auto")
        return [Source(r.title or q, r.url or "", _clip(r.text or "")) for r in res.results]

    return _run_queries(queries, search)


def _tavily(queries: list[str]) -> list[Source]:
    from tavily import TavilyClient

    client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    def search(q: str) -> list[Source]:
        res = client.search(q, max_results=2, search_depth="advanced")
        return [Source(r.get("title", q), r.get("url", ""),
                       _clip(r.get("content", ""))) for r in res.get("results", [])]

    return _run_queries(queries, search)


def _firecrawl(queries: list[str]) -> list[Source]:
    from firecrawl import FirecrawlApp

    client = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])

    def search(q: str) -> list[Source]:
        res = client.search(q, limit=2)
        items = res.get("data", res) if isinstance(res, dict) else res
        return [Source(r.get("title", q), r.get("url", ""),
                       _clip(r.get("markdown") or r.get("description", ""))) for r in (items or [])]

    return _run_queries(queries, search)


_ADAPTERS = {"exa": _exa, "tavily": _tavily, "firecrawl": _firecrawl}


def gather(company: str, provider: str | None = None) -> tuple[list[Source], str | None]:
    """Return (sources, provider_used). Empty list + None when no search key."""
    avail = config.available_search()
    if not avail:
        return [], None

    chain = ([provider] + [p for p in avail if p != provider]) \
        if (provider and provider in avail) else avail

    queries = _queries(company)
    for name in chain:
        try:
            sources = _ADAPTERS[name](queries)
            if sources:
                return sources[:MAX_SOURCES], name
        except Exception:  # noqa: BLE001 — fall through to next provider
            continue
    return [], None


def sources_block(sources: list[Source]) -> str:
    """Render sources as a compact text block for prompt embedding."""
    if not sources:
        return "(no live web sources — rely on your own knowledge)"
    lines = []
    for i, s in enumerate(sources, 1):
        lines.append(f"[{i}] {s.title}\n{s.url}\n{s.text}")
    return "\n\n".join(lines)
