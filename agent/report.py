"""=== ReportAgent ==============================================================

ROLE:
  Orchestrate an end-to-end intelligence report for a single company.
  Owns the core SYSTEM prompt + SCHEMA_HINT that forces company-specific,
  reasoned output instead of generic boilerplate.

SYSTEM PROMPT (module identity):
  "I am the ReportAgent. I take a company name, gather research (via
   ResearchAgent), build a structured prompt with source context, call the
   LLMAgent for a single JSON response, parse it defensively, coerce it into
   a Report dataclass, cache it (via CacheAgent), and return it. I own the
   SYSTEM prompt that defines the senior-consultant persona."

PIPELINE (this agent owns):
  1. Validate company name
  2. Check cache (CacheAgent) — return if hit
  3. Research (ResearchAgent) — gather web sources
  4. Build prompt embedding sources
  5. LLM call (LLMAgent) — generate JSON with SYSTEM + SCHEMA_HINT
  6. Defensive JSON parse — strip fences, repair on failure
  7. Coerce → Report dataclass
  8. Write cache (CacheAgent)
  9. Return Report

CONTEXT:
  Inputs:  Company name, optional LLM provider, force flag
  Outputs: Report dataclass
  Owns:   SYSTEM prompt, SCHEMA_HINT, _extract_json, _coerce

BOUNDARIES:
  I do NOT:
  - Compare multiple companies (see CompareAgent)
  - Generate competitive landscapes (see LandscapeAgent)
  - Format or export reports (see ExportAgent)
  - Present data to users (see UIAgent)
  - Modify cache keys or formats defined by CacheAgent
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from . import cache, config, llm, research

# ── data model ─────────────────────────────────────────────────────────

@dataclass
class Challenge:
    category: str          # operational | sales | customer_experience
    title: str
    reasoning: str


@dataclass
class Opportunity:
    function: str          # automation | customer_engagement | sales | operations | analytics | document_processing
    title: str
    description: str
    impact: str


@dataclass
class Report:
    company: str
    overview: str
    business: str
    challenges: list[Challenge]
    ai_opportunities: list[Opportunity]
    pitch: str
    sources: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Report":
        return cls(
            company=d["company"],
            overview=d.get("overview", ""),
            business=d.get("business", ""),
            challenges=[Challenge(**c) for c in d.get("challenges", [])],
            ai_opportunities=[Opportunity(**o) for o in d.get("ai_opportunities", [])],
            pitch=d.get("pitch", ""),
            sources=d.get("sources", []),
            meta=d.get("meta", {}),
        )


# ── prompt ─────────────────────────────────────────────────────────────

SYSTEM = (
    "You are a warm, perceptive business advisor who genuinely cares about the "
    "companies you study. You see beyond the balance sheet — you understand the "
    "people, the customers, the daily struggles, and the quiet wins that don't "
    "make the news. You research deeply, but you write like a thoughtful human "
    "talking to another human. No jargon. No fluff. No generic corporate-speak. "
    "Be honest but kind about challenges. Be specific about what makes this "
    "company special. Output STRICT JSON matching the requested schema."
)

SCHEMA_HINT = """Return JSON with EXACTLY these keys:
{
  "overview": "string — 3-5 sentences that capture the SOUL of the company. Not just what it does, but who it serves, what it stands for, its place in the world. Weave in industry, scale, and geography naturally, like you're describing a friend's life work.",
  "business": "string — major offerings, recent moves, expansion plans. Write it like you're telling a story: 'They started in... now they're known for... lately they've been...' Use concrete details, not bullet points.",
  "challenges": [
    {"category": "operational|sales|customer_experience",
     "title": "short human-readable challenge name",
     "reasoning": "WHY this genuinely hurts — describe the human impact. A team that's stretched thin. Customers who feel unheard. A market that's changing faster than they can adapt. Tie every challenge to THIS company's specific reality. 2-3 sentences."}
  ],
  "ai_opportunities": [
    {"function": "automation|customer_engagement|sales|operations|analytics|document_processing",
     "title": "specific AI solution name, framed as a human benefit",
     "description": "what it does and why it matters to the people involved — the engineer who gets evenings back, the customer who gets faster answers, the sales team that finally knows who to call",
     "impact": "the real-world difference this makes — time saved, revenue gained, burnout reduced, loyalty built"}
  ],
  "pitch": "string — a one-page message to the CEO written from the heart. Not a sales pitch. A genuine conversation starter. Three natural beats: (1) Here's why I'm reaching out — what I see in your company that moved me to write, (2) Here's what I noticed — opportunities that feel tailor-made for you, (3) Here's how I think AI could help — not as a magic wand, but as a practical next step. Write it like you mean it."
}
Provide 3-4 challenges spanning at least two categories, and 4-5 ai_opportunities spanning at least three functions."""


def _build_prompt(company: str, sources: list[research.Source]) -> str:
    return (
        f"COMPANY: {company}\n\n"
        f"RESEARCH SOURCES:\n{research.sources_block(sources)}\n\n"
        f"TASK: Produce an intelligence report on {company}.\n"
        "Ground every claim in the sources where possible; where sources are thin, "
        "reason from what is publicly known about this company and its industry, and "
        "stay specific to it.\n\n"
        f"{SCHEMA_HINT}"
    )


# ── JSON parsing (defensive) ───────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = text.strip()
    # strip ```json ... ``` fences if a model added them
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        first, last = text.find("{"), text.rfind("}")
        if first != -1 and last != -1:
            text = text[first:last + 1]
    return json.loads(text)


def _coerce(company: str, data: dict, sources, provider, search_provider) -> Report:
    challenges = []
    for c in data.get("challenges", []):
        challenges.append(Challenge(
            category=str(c.get("category", "operational")).lower().replace(" ", "_"),
            title=c.get("title", ""),
            reasoning=c.get("reasoning", ""),
        ))
    opps = []
    for o in data.get("ai_opportunities", []):
        opps.append(Opportunity(
            function=str(o.get("function", "operations")).lower().replace(" ", "_"),
            title=o.get("title", ""),
            description=o.get("description", ""),
            impact=o.get("impact", ""),
        ))
    return Report(
        company=company,
        overview=data.get("overview", ""),
        business=data.get("business", ""),
        challenges=challenges,
        ai_opportunities=opps,
        pitch=data.get("pitch", ""),
        sources=[s.as_dict() for s in sources],
        meta={
            "llm_provider": provider,
            "search_provider": search_provider,
            "live_research": bool(sources),
        },
    )


# ── public API ─────────────────────────────────────────────────────────

def build(company: str, provider: str | None = None, force: bool = False,
          urls: list[str] | None = None) -> Report:
    company = company.strip()
    if not company:
        raise ValueError("company name is empty")

    prov = provider or config.default_llm()
    if not prov:
        raise llm.LLMError(
            "No LLM provider configured. Add a key to .env or run Ollama locally."
        )

    ckey = cache.key(company, prov)
    if not force:
        cached = cache.get(ckey)
        if cached:
            return Report.from_dict(cached)

    sources, search_provider = research.gather(company)
    for u in (urls or []):
        u = u.strip()
        if u:
            sources.append(research.Source(title="Custom Reference", url=u, text=""))
    prompt = _build_prompt(company, sources)

    raw, used = llm.generate(SYSTEM, prompt, provider=prov)
    try:
        data = _extract_json(raw)
    except Exception:  # noqa: BLE001 — one repair attempt
        repair = prompt + "\n\nYour previous answer was not valid JSON. " \
                          "Return ONLY the JSON object, nothing else."
        raw, used = llm.generate(SYSTEM, repair, provider=prov)
        data = _extract_json(raw)

    report = _coerce(company, data, sources, used, search_provider)
    cache.set(ckey, report.to_dict())
    return report


# ── CLI / smoke-test entry ─────────────────────────────────────────────

def _to_markdown(r: Report) -> str:
    from . import export

    return export.to_markdown(r)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Generate a company intelligence report.")
    ap.add_argument("company")
    ap.add_argument("--provider", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    r = build(args.company, provider=args.provider, force=args.force)
    print(_to_markdown(r))
    print(f"\n--- generated by: {r.meta.get('llm_provider')} | "
          f"search: {r.meta.get('search_provider') or 'none (LLM-knowledge mode)'} ---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
