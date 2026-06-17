"""AI-Powered Research & Recommendation Agent.

=== AGENT SYSTEM =============================================================

This package contains a system of specialized agents, each with a defined role,
system prompt, and strict context boundaries. No agent performs tasks belonging
to another agent — they communicate through well-defined function interfaces.

AGENT REGISTRY:
  ConfigAgent     (config.py)     — Detect environment, enumerate LLM/search providers
  CacheAgent      (cache.py)      — Persistent disk cache keyed by company+model
  ResearchAgent   (research.py)   — Gather live web data from Exa/Tavily/Firecrawl
  LLMAgent        (llm.py)        — Route LLM calls across providers with fallback chain
  ReportAgent     (report.py)     — Orchestrate single-company intelligence reports
  CompareAgent    (compare.py)    — Multi-company side-by-side comparison matrix
  LandscapeAgent  (landscape.py)  — 3-5 company competitive landscape analysis
  ExportAgent     (export.py)     — Format reports as Markdown and PDF
  UIAgent         (app.py)        — Streamlit interface (presentation only)

AGENT COMMUNICATION CONTRACT:
  Agents communicate ONLY through function calls and return values.
  No agent calls another agent's LLM prompts directly.
  No agent modifies another agent's cache keys or data format.
  Each agent owns its prompt templates exclusively.

DEPENDENCY GRAPH (→ means "depends on"):
  UIAgent → ReportAgent → ConfigAgent + ResearchAgent + LLMAgent + CacheAgent
  UIAgent → CompareAgent → ReportAgent + LLMAgent
  UIAgent → LandscapeAgent → ReportAgent + LLMAgent + CacheAgent
  UIAgent → ExportAgent
  ReportAgent → ExportAgent (CLI mode only)
  LandscapeAgent → ExportAgent (CLI mode only)
"""

__version__ = "1.1.0"
