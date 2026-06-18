"""=== LandscapeAgent ===========================================================

ROLE:
  Generate a competitive landscape analysis for 3-5 companies operating in the
  same industry. Produces: market overview, positioning map, strengths/
  weaknesses, strategic gaps, and per-company strategic recommendations.

SYSTEM PROMPT (module identity):
  "I am the LandscapeAgent. I take 3-5 company names, build individual reports
   (via ReportAgent with cache reuse), aggregate their research sources, then
   call the LLMAgent with a SYSTEM prompt defining a strategy-consultant persona
   and a LANDSCAPE_SCHEMA that enforces specific output structure."

CONTEXT:
  Inputs:  List of 3-5 company names, optional LLM provider, force flag
  Outputs: CompetitiveLandscape dataclass
  Owns:   SYSTEM prompt (senior strategy consultant), LANDSCAPE_SCHEMA,
          _cache_key (separate from CacheAgent's report keys)

BOUNDARIES:
  I do NOT:
  - Generate individual reports (delegates to ReportAgent)
  - Generate simple comparison matrices (see CompareAgent)
  - Export or format output (see ExportAgent)
  - Present data to users (see UIAgent)
  - Reuse cache keys from ReportAgent (uses own _cache_key)
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field

from . import cache as cache_mod
from . import config, llm, report


SYSTEM = (
    "You are an experienced industry analyst with a genuine feel for the "
    "companies you study. You see the market not as a matrix but as a living "
    "ecosystem — each player with their own story, their own struggles, their "
    "own quiet advantages. You write clearly and humanly, like a thoughtful "
    "colleague sharing what they've noticed over coffee. No filler, no "
    "corporate speak. Output STRICT JSON matching the requested schema."
)

LANDSCAPE_SCHEMA = """Return JSON with EXACTLY these keys:
{
  "market_overview": "string — 3-5 sentences that paint the big picture. What's happening in this industry, where the energy is, who's feeling the pressure and who's thriving. Make it feel like real market color, not a textbook.",
  "positioning": [
    {
      "company": "name",
      "scale": "relative size (Small/Medium/Large/Enterprise) with a human-scale justification",
      "price_tier": "Budget/Mid-market/Premium with real-world context",
      "geographic_reach": "Local/Regional/National/Global with specifics, not labels",
      "key_strength": "one-sentence differentiator — what this company does better than anyone",
      "key_weakness": "one-sentence vulnerability — the thing that keeps their leadership up at night"
    }
  ],
  "strengths_weaknesses": [
    {
      "company": "name",
      "strengths": ["3-5 specific strengths — things their people genuinely do well"],
      "weaknesses": ["3-5 real weaknesses — not strategic gaps, but human realities"],
      "ai_readiness": "Low|Medium|High with honest 3-4 word justification"
    }
  ],
  "strategic_gaps": [
    {
      "gap": "short name of the unaddressed opportunity",
      "description": "what's missing in this market and why it matters to real people — customers, employees, communities",
      "opportunity_size": "estimated real-world impact ('15-20% cost reduction', 'a whole new revenue stream', 'happier customers who stay longer')",
      "best_positioned": "which company is closest to capturing this, and why"
    }
  ],
  "recommendations": {
    "COMPANY_NAME": "a specific, human recommendation based on where they sit. Not a strategy deck slide — genuine advice you'd give a friend who runs the place. 2-4 sentences."
  }
}
Provide at least 3 strategic_gaps and a recommendation for every company."""


@dataclass
class CompetitiveLandscape:
    industry: str
    companies: list[str]
    market_overview: str
    positioning: list[dict]
    strengths_weaknesses: list[dict]
    strategic_gaps: list[dict]
    recommendations: dict
    sources: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    reports: list = field(default_factory=list)  # Report objects (not cached)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("reports", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> CompetitiveLandscape:
        return cls(
            industry=d.get("industry", ""),
            companies=d.get("companies", []),
            market_overview=d.get("market_overview", ""),
            positioning=d.get("positioning", []),
            strengths_weaknesses=d.get("strengths_weaknesses", []),
            strategic_gaps=d.get("strategic_gaps", []),
            recommendations=d.get("recommendations", {}),
            sources=d.get("sources", []),
            meta=d.get("meta", {}),
        )


# ── helpers ────────────────────────────────────────────────────────────

def _cache_key(companies: list[str], provider: str) -> str:
    raw = "_".join(sorted(c.lower().strip() for c in companies))
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"landscape_{h}__{provider}"


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        first, last = text.find("{"), text.rfind("}")
        if first != -1 and last != -1:
            text = text[first:last + 1]
    return json.loads(text)


def _build_prompt(reports: list[report.Report]) -> str:
    profiles = []
    all_sources: list[dict] = []
    for r in reports:
        ch = "; ".join(c.title for c in r.challenges[:3])
        op = "; ".join(o.title for o in r.ai_opportunities[:3])
        profiles.append(
            f"### {r.company}\n"
            f"Overview: {r.overview}\n"
            f"Business: {r.business}\n"
            f"Top challenges: {ch}\n"
            f"AI opportunities: {op}\n"
            f"Pitch angle: {r.pitch[:300]}"
        )
        all_sources.extend(r.sources)

    sources_block = "\n\n".join(
        f"[{i}] {s.get('title', 'source')}\n{s.get('url', '')}\n{(s.get('text') or '')[:800]}"
        for i, s in enumerate(all_sources, 1)
    ) if all_sources else "(no live web sources — rely on your own knowledge)"

    companies = ", ".join(r.company for r in reports)
    return (
        f"COMPANIES: {companies}\n\n"
        f"INDIVIDUAL REPORTS:\n\n{chr(10).join(profiles)}\n\n"
        f"RESEARCH SOURCES:\n{sources_block}\n\n"
        f"TASK: Produce a competitive landscape analysis for these companies.\n"
        f"{LANDSCAPE_SCHEMA}"
    )


# ── public API ─────────────────────────────────────────────────────────

def build(companies: list[str], provider: str | None = None,
          force: bool = False,
          urls: list[str] | None = None,
          progress_callback: Callable[[str, str], None] | None = None) -> CompetitiveLandscape:
    companies = [c.strip() for c in companies if c.strip()]
    if len(companies) < 3:
        raise ValueError("provide at least 3 companies for competitive landscape")
    if len(companies) > 5:
        raise ValueError("max 5 companies for competitive landscape")

    prov = provider or config.default_llm()
    if not prov:
        raise llm.LLMError("No LLM provider configured.")

    ckey = _cache_key(companies, prov)
    if not force:
        cached = cache_mod.get(ckey)
        if cached:
            if progress_callback:
                progress_callback("cache_hit", companies[0])
            return CompetitiveLandscape.from_dict(cached)

    reports = []
    with ThreadPoolExecutor(max_workers=len(companies)) as pool:
        futures = {pool.submit(report.build, c, provider=provider,
                               force=force, urls=urls): c
                   for c in companies}
        for f in as_completed(futures):
            reports.append(f.result())
    if progress_callback:
        progress_callback("analyzing", "")
    used = reports[0].meta.get("llm_provider", prov)

    prompt = _build_prompt(reports)
    raw, used = llm.generate(SYSTEM, prompt, provider=provider or used)

    try:
        data = _extract_json(raw)
    except Exception:
        repair = prompt + ("\n\nYour previous answer was not valid JSON. "
                           "Return ONLY the JSON object, nothing else.")
        raw, used = llm.generate(SYSTEM, repair, provider=provider or used)
        data = _extract_json(raw)

    all_sources: list[dict] = []
    for r in reports:
        all_sources.extend(r.sources)

    landscape = CompetitiveLandscape(
        industry="",
        companies=[r.company for r in reports],
        market_overview=data.get("market_overview", ""),
        positioning=data.get("positioning", []),
        strengths_weaknesses=data.get("strengths_weaknesses", []),
        strategic_gaps=data.get("strategic_gaps", []),
        recommendations=data.get("recommendations", {}),
        sources=all_sources,
        meta={"llm_provider": used, "companies": companies},
        reports=reports,
    )

    cache_mod.set(ckey, landscape.to_dict())
    return landscape


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Competitive landscape analysis.")
    ap.add_argument("companies", nargs="+")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    from . import export
    l = build(args.companies, provider=args.provider, force=args.force)
    print(export.landscape_to_markdown(l))
    print(f"\n--- generated by: {l.meta.get('llm_provider')} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
