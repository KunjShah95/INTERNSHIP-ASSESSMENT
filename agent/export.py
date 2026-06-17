"""=== ExportAgent ==============================================================

ROLE:
  Format Report and CompetitiveLandscape dataclasses into downloadable formats:
  Markdown (.md) and PDF (using fpdf2, pure-python, no system dependencies).

SYSTEM PROMPT (module identity):
  "I am the ExportAgent. I take a Report or CompetitiveLandscape dataclass and
   produce formatted Markdown or PDF bytes. I own formatting logic, label maps,
   and PDF layout — I do not generate or modify content."

CONTEXT:
  Inputs:  Report dataclass or CompetitiveLandscape dataclass
  Outputs: str (Markdown) or bytes (PDF)
  Deps:   fpdf2 (pure Python, no system libs)

BOUNDARIES:
  I do NOT:
  - Generate or analyze any content
  - Make LLM calls
  - Do web research
  - Cache data
  - Present to users (that's UIAgent's job)
"""
from __future__ import annotations

from .report import Report

_CAT_LABEL = {
    "operational": "Operational",
    "sales": "Sales",
    "customer_experience": "Customer Experience",
}
_FN_LABEL = {
    "automation": "Automation",
    "customer_engagement": "Customer Engagement",
    "sales": "Sales",
    "operations": "Operations",
    "analytics": "Analytics",
    "document_processing": "Document Processing",
}


def to_markdown(r: Report) -> str:
    lines: list[str] = [f"# Intelligence Report — {r.company}", ""]

    lines += ["## 1. Company Overview", "", r.overview, ""]
    lines += ["## 2. Key Business Information", "", r.business, ""]

    lines += ["## 3. Potential Business Challenges", ""]
    for c in r.challenges:
        label = _CAT_LABEL.get(c.category, c.category.title())
        lines += [f"### [{label}] {c.title}", "", c.reasoning, ""]

    lines += ["## 4. AI Opportunities", ""]
    for o in r.ai_opportunities:
        label = _FN_LABEL.get(o.function, o.function.title())
        lines += [f"### [{label}] {o.title}", "",
                  o.description, "", f"**Impact:** {o.impact}", ""]

    lines += ["## 5. Personalized Pitch", "", r.pitch, ""]

    if r.sources:
        lines += ["## Sources", ""]
        for i, s in enumerate(r.sources, 1):
            lines.append(f"{i}. [{s.get('title','source')}]({s.get('url','')})")
        lines.append("")

    meta = r.meta
    lines += ["---",
              f"_LLM: {meta.get('llm_provider')} · "
              f"Research: {meta.get('search_provider') or 'LLM-knowledge mode'}_"]
    return "\n".join(lines)


def to_pdf(r: Report) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def _txt(s: str) -> str:
        # fpdf2 core fonts are latin-1; drop unsupported glyphs safely.
        return (s or "").encode("latin-1", "replace").decode("latin-1")

    def _cell(s: str, size: int, style: str = "") -> None:
        # new_x=LMARGIN keeps the cursor at the left margin so the next
        # multi_cell always has full page width to work with.
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, size * 0.5 + 2, _txt(s),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def h1(s: str) -> None:
        _cell(s, 16, "B")

    def h2(s: str) -> None:
        pdf.ln(2)
        _cell(s, 13, "B")

    def h3(s: str) -> None:
        _cell(s, 11, "B")

    def body(s: str) -> None:
        _cell(s, 11)
        pdf.ln(1)

    h1(f"Intelligence Report - {r.company}")
    h2("1. Company Overview"); body(r.overview)
    h2("2. Key Business Information"); body(r.business)

    h2("3. Potential Business Challenges")
    for c in r.challenges:
        h3(f"[{_CAT_LABEL.get(c.category, c.category)}] {c.title}")
        body(c.reasoning)

    h2("4. AI Opportunities")
    for o in r.ai_opportunities:
        h3(f"[{_FN_LABEL.get(o.function, o.function)}] {o.title}")
        body(o.description)
        body(f"Impact: {o.impact}")

    h2("5. Personalized Pitch"); body(r.pitch)

    if r.sources:
        h2("Sources")
        for i, s in enumerate(r.sources, 1):
            body(f"{i}. {s.get('title','source')} - {s.get('url','')}")

    out = pdf.output()
    return bytes(out)


# ── Landscape exports ──────────────────────────────────────────────────

def landscape_to_markdown(l) -> str:
    lines = ["# Competitive Landscape Analysis", ""]
    lines += [f"**Companies:** {', '.join(l.companies)}", ""]
    lines += ["## 1. Market Overview", "", l.market_overview, ""]

    lines += ["## 2. Competitive Positioning", ""]
    lines += ["| Company | Scale | Price Tier | Geographic Reach | Key Strength | Key Weakness |"]
    lines += ["|---------|-------|------------|-----------------|--------------|-------------|"]
    for p in l.positioning:
        lines += [
            f"| {p.get('company', '')} | {p.get('scale', '')} | "
            f"{p.get('price_tier', '')} | {p.get('geographic_reach', '')} | "
            f"{p.get('key_strength', '')} | {p.get('key_weakness', '')} |"
        ]
    lines.append("")

    lines += ["## 3. Strengths & Weaknesses", ""]
    for sw in l.strengths_weaknesses:
        c = sw.get("company", "")
        lines += [f"### {c}", ""]
        lines += ["**Strengths:**"] + [f"- {s}" for s in sw.get("strengths", [])]
        lines += ["", "**Weaknesses:**"] + [f"- {w}" for w in sw.get("weaknesses", [])]
        lines += ["", f"**AI Readiness:** {sw.get('ai_readiness', 'N/A')}", ""]

    lines += ["## 4. Strategic Gaps", ""]
    for g in l.strategic_gaps:
        lines += [f"### {g.get('gap', '')}", "", g.get("description", ""), ""]
        lines += [f"- **Opportunity size:** {g.get('opportunity_size', 'N/A')}"]
        lines += [f"- **Best positioned:** {g.get('best_positioned', 'None')}", ""]

    lines += ["## 5. Strategic Recommendations", ""]
    for company, rec in l.recommendations.items():
        lines += [f"### {company}", "", rec, ""]

    if l.sources:
        lines += ["## Sources", ""]
        for i, s in enumerate(l.sources, 1):
            lines += [f"{i}. [{s.get('title', 'source')}]({s.get('url', '')})"]
        lines.append("")

    meta = l.meta
    lines += [
        "---",
        f"_LLM: {meta.get('llm_provider')} · "
        f"Companies: {', '.join(l.companies)}_",
    ]
    return "\n".join(lines)


def landscape_to_pdf(l) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    def _txt(s: str) -> str:
        return (s or "").encode("latin-1", "replace").decode("latin-1")

    def _cell(s: str, size: int, style: str = "") -> None:
        pdf.set_font("Helvetica", style, size)
        pdf.multi_cell(0, size * 0.5 + 2, _txt(s),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def h1(s: str) -> None:
        _cell(s, 16, "B")

    def h2(s: str) -> None:
        pdf.ln(2)
        _cell(s, 13, "B")

    def h3(s: str) -> None:
        _cell(s, 11, "B")

    def body(s: str) -> None:
        _cell(s, 11)
        pdf.ln(1)

    h1("Competitive Landscape Analysis")
    body(f"Companies: {', '.join(l.companies)}")

    h2("1. Market Overview")
    body(l.market_overview)

    h2("2. Competitive Positioning")
    pdf.set_font("Helvetica", "B", 9)
    cols = ["Company", "Scale", "Price", "Geography", "Strength", "Weakness"]
    cw = [28, 28, 24, 28, 42, 42]
    for col_name, w in zip(cols, cw):
        pdf.cell(w, 7, _txt(col_name), border=1)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for p in l.positioning:
        vals = [
            _txt(p.get("company", ""))[:16],
            _txt(p.get("scale", ""))[:16],
            _txt(p.get("price_tier", ""))[:14],
            _txt(p.get("geographic_reach", ""))[:16],
            _txt(p.get("key_strength", ""))[:28],
            _txt(p.get("key_weakness", ""))[:28],
        ]
        row_h = 6
        for v, w in zip(vals, cw):
            pdf.cell(w, row_h, v, border=1)
        pdf.ln()

    h2("3. Strengths & Weaknesses")
    for sw in l.strengths_weaknesses:
        h3(sw.get("company", ""))
        body("Strengths: " + "; ".join(sw.get("strengths", [])))
        body("Weaknesses: " + "; ".join(sw.get("weaknesses", [])))
        body(f"AI Readiness: {sw.get('ai_readiness', 'N/A')}")

    h2("4. Strategic Gaps")
    for g in l.strategic_gaps:
        h3(g.get("gap", ""))
        body(g.get("description", ""))
        body(f"Opportunity: {g.get('opportunity_size', 'N/A')}")
        body(f"Best positioned: {g.get('best_positioned', 'None')}")

    h2("5. Strategic Recommendations")
    for company, rec in l.recommendations.items():
        h3(company)
        body(rec)

    out = pdf.output()
    return bytes(out)
