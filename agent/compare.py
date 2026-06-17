"""=== CompareAgent =============================================================

ROLE:
  Generate a side-by-side comparison matrix for 2+ companies.
  Reuses individual reports from ReportAgent (with cache), then makes one
  extra LLM call to produce a relative comparison across 5 dimensions.

SYSTEM PROMPT (module identity):
  "I am the CompareAgent. I take 2+ company names, build individual reports
   (via ReportAgent), then call the LLMAgent with a _MATRIX_PROMPT that asks
   for a structured comparison matrix. The matrix covers: scale, geographic
   reach, top challenge, AI readiness, and recommended first AI win."

CONTEXT:
  Inputs:  List of company names, optional LLM provider, force flag
  Outputs: CompareResult(reports, matrix, meta)
  Owns:   _MATRIX_PROMPT template, _profile helper

BOUNDARIES:
  I do NOT:
  - Generate individual reports (delegates to ReportAgent)
  - Do competitive landscape analysis (see LandscapeAgent)
  - Export or format output (see ExportAgent)
  - Present data to users (see UIAgent)
  - Modify the SYSTEM prompt owned by ReportAgent
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import llm
from .report import Report, build, SYSTEM


@dataclass
class CompareResult:
    reports: list[Report]
    matrix: list[dict] = field(default_factory=list)  # one row per company
    meta: dict = field(default_factory=dict)


_COLUMNS = ["scale", "geographic_reach", "top_challenge",
            "ai_readiness", "recommended_first_ai_win"]

_MATRIX_PROMPT = """You are comparing companies as a thoughtful industry insider would —
not a spreadsheet, but a conversation. Here are short profiles of each:

{profiles}

For each company, paint a quick portrait: size and feel, where they operate,
their toughest human challenge right now, how ready they honestly are for AI,
and one small win that would make a real difference to their people.

Return STRICT JSON: {{"matrix": [ROWS]}} where each ROW is:
{{"company": "name",
  "scale": "relative size, 1 short phrase with human texture",
  "geographic_reach": "where and how they operate, 1 short phrase",
  "top_challenge": "their single biggest human challenge right now, 1 phrase",
  "ai_readiness": "Low|Medium|High + 3-4 word honest justification",
  "recommended_first_ai_win": "one AI project that would tangibly improve people's work, 1 phrase"}}
One row per company, same order as given. Be specific and human."""


def _profile(r: Report) -> str:
    ch = "; ".join(c.title for c in r.challenges[:3])
    op = "; ".join(o.title for o in r.ai_opportunities[:3])
    return (f"### {r.company}\nOverview: {r.overview}\n"
            f"Top challenges: {ch}\nAI opportunities: {op}")


def compare(companies: list[str], provider: str | None = None,
            force: bool = False,
            urls: list[str] | None = None) -> CompareResult:
    companies = [c.strip() for c in companies if c.strip()]
    if len(companies) < 2:
        raise ValueError("provide at least two companies to compare")

    reports = [build(c, provider=provider, force=force, urls=urls) for c in companies]
    used = reports[0].meta.get("llm_provider")

    prompt = _MATRIX_PROMPT.format(
        profiles="\n\n".join(_profile(r) for r in reports))
    raw, used = llm.generate(SYSTEM, prompt, provider=provider or used)

    matrix: list[dict] = []
    try:
        from .report import _extract_json

        matrix = _extract_json(raw).get("matrix", [])
    except Exception:  # noqa: BLE001 — matrix is a nicety; reports still stand
        matrix = []

    return CompareResult(reports=reports, matrix=matrix,
                         meta={"llm_provider": used, "columns": _COLUMNS})
