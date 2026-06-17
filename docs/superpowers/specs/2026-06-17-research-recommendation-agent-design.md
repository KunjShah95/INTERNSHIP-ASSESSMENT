# AI-Powered Research & Recommendation Agent — Design

**Date:** 2026-06-17
**Status:** Approved (pending spec review)

## 1. Purpose

Take a company name (e.g. "Sobha", "Prestige Group") and generate a structured
intelligence report with five sections:

1. Company Overview — what it does, industry, scale, geographic presence
2. Key Business Information — offerings, recent developments, expansion plans, public info
3. Potential Business Challenges — operational / sales / customer-experience, **with reasoning**
4. AI Opportunities — **company-specific**, tied to real offerings (not generic)
5. Personalized Pitch — one page, CEO-facing

Built for an AI/ML intern assessment. Graded on reasoning (30%), research quality (20%),
practicality (20%), AI-tool usage (15%), product quality (10%), docs (5%).

## 2. Approach

Thin **provider abstraction** + **single structured LLM call** per company.

- One structured JSON call (not 5 per-section calls): cheaper/faster on free models,
  coherent report, fewer failure points.
- **Hybrid research**: use a live web-search provider when a key is present; gracefully
  fall back to LLM-knowledge-only mode (with a visible banner) when none is.
- **Hybrid LLM**: pluggable across open-source (Groq, OpenRouter, Ollama, Gemini free tier)
  and paid (Anthropic, OpenAI). Auto-detect available providers from env; user can also
  pick one in the UI. Fallback chain on call failure.

## 3. Architecture

```
Streamlit UI (app.py)  ── tabs: [Single Report] [Compare]
     │  company name(s), provider choice, force-refresh
     ▼
Orchestrator (agent/report.py)
     ├─ cache hit? (agent/cache.py) → return cached
     ├─► Research (agent/research.py) ── search adapter (exa|tavily|firecrawl, first live)
     │        no key → skip, LLM-only mode                → sources[]
     ▼
Prompt builder (in report.py) ◄── company + sources
     ▼
LLM client (agent/llm.py) ── adapters: groq|openrouter|ollama|gemini|anthropic|openai
     ▼  one structured JSON call (+ retry/fallback chain)
Report dataclass {overview, business, challenges[], ai_opportunities[], pitch, sources[], meta}
     ├─ cache write
     ▼
Render 5 sections  +  Export (agent/export.py → .md / .pdf)

Compare path (agent/compare.py): run report.py per company (reuses cache),
then one extra LLM call → comparison matrix (relative scale, AI-readiness, key risk).
```

## 4. Components

Each is isolated, single-purpose, testable in isolation.

### `agent/config.py`
- Reads env (`.env` via python-dotenv).
- `available_llms() -> list[str]`, `available_search() -> list[str]` by key presence
  (Ollama detected via localhost ping, no key).
- `default_llm()`, `default_search()` by priority order.
- Pure functions → unit-testable with monkeypatched env.

### `agent/llm.py`
- `generate(system: str, prompt: str, provider: str | None) -> str`.
- One adapter per provider behind a common signature.
  - Open-source/free: `groq` (llama-3.3-70b / mixtral / gemma), `openrouter` (free models),
    `ollama` (local http), `gemini` (gemini-2.0-flash, free tier).
  - Paid: `anthropic` (claude-sonnet), `openai` (gpt-4o).
- Provider resolution: explicit arg → else `config.default_llm()`.
- Fallback chain: on exception, try next available provider; raise if all fail.
- JSON-mode / response-format used where the SDK supports it; otherwise instruct + parse.

### `agent/research.py`
- `gather(company: str) -> list[Source]` where `Source = {title, url, text}`.
- Runs ~3 targeted queries: `"{company} company overview"`,
  `"{company} recent news 2025 2026"`, `"{company} expansion projects financials"`.
- Adapter per provider: `exa` (search_and_contents), `tavily` (search),
  `firecrawl` (search). Uses first live provider.
- No search key → returns `[]` (signals LLM-only mode upstream).
- Truncates total source text to a token budget so free-model context isn't blown.

### `agent/report.py`
- `build(company, provider=None, force=False) -> Report`.
- Flow: cache check → `research.gather` → prompt build → `llm.generate` → parse JSON → cache.
- **Owns the prompt** (core IP). System: senior analyst pitching AI services. Instructions
  force specificity:
  - Challenges each tagged `category ∈ {operational, sales, customer_experience}`
    and must state *why* (tie to segment/scale/geography/segment economics).
  - AI opportunities must reference the company's actual offerings from `sources`,
    name the function (automation/customer-engagement/sales/operations/analytics/
    document-processing), and the concrete win — no generic "add a chatbot".
  - Pitch: ~1 page, CEO-to-reader voice, structured to hit all three beats —
    (a) why I reached out, (b) what opportunities I identified, (c) what AI solutions
    I'd recommend.
- Strict JSON schema returned; defensive parse (strip code fences, json.loads, validate keys).

### `agent/cache.py`
- Key = `slug(company)_{llm_provider}`. Store JSON under `cache/`.
- `get(key)`, `set(key, report)`. `force=True` bypasses read.

### `agent/export.py`
- `to_markdown(report) -> str`, `to_pdf(report) -> bytes` via `fpdf2` (pure-python,
  Windows-friendly, no system libs). Sections + sources list.

### `agent/compare.py`
- `compare(companies: list[str], provider=None) -> CompareResult`.
- Build each report (cache-reused), then one LLM call → matrix rows:
  scale, geographic reach, top challenge, AI-readiness, recommended first AI win.

### `app.py` (Streamlit)
- Sidebar: provider dropdown (auto + available list), search-mode/provider indicator,
  force-refresh toggle, active-key status.
- Tab **Single Report**: text input → Generate → spinner → 5 rendered sections,
  sources expander, download `.md` / `.pdf`.
- Tab **Compare**: comma-separated companies → side-by-side columns + comparison matrix.
- Banner when running LLM-only (no live search).

### CLI
- `python -m agent.report "Sobha"` prints markdown report. Doubles as debug/smoke entry.

## 5. Data Flow

```
name → cache? → gather() sources → prompt(sources) → 1 LLM JSON call
     → Report → cache write → render + export(.md/.pdf)
compare: [Report per company] + 1 matrix LLM call → side-by-side view
```

## 6. Error Handling

- No LLM key and no Ollama → app halts with setup instructions (`.env.example` shown).
- No search key → yellow banner "LLM-knowledge mode (no live data)"; still generates.
- Search call fails → try next live search provider; if all fail → LLM-only, banner.
- LLM call fails → next provider in fallback chain; all fail → friendly error in UI.
- Malformed JSON from model → one repair retry (re-ask "return valid JSON only"); else error.

## 7. Testing

- Unit: `config` provider detection (monkeypatched env), `report.parse` JSON parsing
  (fence stripping, missing-key handling) with a fake LLM, `cache` get/set round-trip,
  `export.to_markdown` shape.
- Smoke: CLI `python -m agent.report "Sobha"` end-to-end with a real free key (manual,
  in demo).

## 8. Deliverables

- Working Streamlit app (single + compare, md/pdf export, caching).
- `README.md`: approach, architecture, AI tools used, challenges faced + how solved.
- `.env.example`, `requirements.txt`.
- Demo video (recorded by candidate; not in scope of code).

## 9. Out of Scope (YAGNI)

Auth, databases, hosted deployment, user accounts, scheduled refresh, vector store.

## 10. Tech Stack

Python 3.11+, Streamlit, python-dotenv, fpdf2, provider SDKs
(`anthropic`, `openai`, `google-generativeai`, `groq`, `requests` for OpenRouter/Ollama,
`exa-py`, `tavily-python`, `firecrawl-py`). Adapters import lazily so a missing SDK for an
unused provider never breaks startup.
