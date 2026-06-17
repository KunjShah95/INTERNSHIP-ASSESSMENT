# System Architecture

AI-Powered Research & Recommendation Agent — detailed design.

> Companion to `README.md`. README = how to run. This = how it's built and why.

---

## 1. System overview

A layered pipeline. A user names a company; the system researches it, reasons
about it with an LLM, and returns a structured report rendered in a UI and
exportable to file. Every external dependency (LLM, web search) is pluggable and
optional — the system degrades gracefully instead of failing.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                             │
│  app.py  (Streamlit)                                                   │
│   ├─ Sidebar: provider picker, research-mode indicator, force-refresh  │
│   ├─ Tab "Single Report"   → render 5 sections + .md/.pdf download     │
│   └─ Tab "Compare"         → side-by-side + comparison matrix          │
│  CLI: python -m agent.report "<company>"   (same core, no UI)          │
└───────────────┬──────────────────────────────────────────────────────┘
                │ company name, provider choice, force flag
┌───────────────▼──────────────────────────────────────────────────────┐
│                        ORCHESTRATION LAYER                             │
│  agent/report.py   build(company, provider, force) → Report           │
│  agent/compare.py  compare([companies]) → CompareResult               │
│   • cache lookup → research → prompt → LLM → parse → cache write       │
└───┬───────────────┬───────────────┬───────────────┬──────────────────┘
    │               │               │               │
┌───▼────┐    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼──────┐
│ cache  │    │ research  │   │   llm     │   │  export    │
│  .py   │    │   .py     │   │   .py     │   │   .py      │
│ disk   │    │ 3 search  │   │ 6 LLM     │   │ md + pdf   │
│ JSON   │    │ adapters  │   │ adapters  │   │ (fpdf2)    │
└────────┘    └─────┬─────┘   └─────┬─────┘   └────────────┘
                    │               │
┌───────────────────▼───────────────▼──────────────────────────────────┐
│                         PROVIDER LAYER (external)                      │
│  Search: Exa · Tavily · Firecrawl    LLM: Groq · Gemini · OpenRouter · │
│                                            Ollama · Anthropic · OpenAI │
└───────────────────────────────────────────────────────────────────────┘
        ▲
        │ agent/config.py — detects which providers are usable from .env,
        │ sets priority + fallback order. Read by every layer above.
```

---

## 2. Component responsibilities

| Component | Input | Output | Owns | Depends on |
|---|---|---|---|---|
| `config.py` | env vars | provider lists, defaults | "what is usable + in what order" | dotenv, requests (ollama ping) |
| `research.py` | company name | `list[Source]` + provider used | querying web, normalizing results, token budget | config, search SDKs (lazy) |
| `llm.py` | system + user prompt | `(text, provider_used)` | provider adapters, fallback chain | config, LLM SDKs (lazy) |
| `report.py` | company name | `Report` dataclass | **the prompt**, orchestration, JSON parsing | config, research, llm, cache |
| `cache.py` | company + provider | cached `Report` dict | disk persistence, key slugging | stdlib only |
| `export.py` | `Report` | markdown str / pdf bytes | rendering | report (types), fpdf2 |
| `compare.py` | `list[company]` | `CompareResult` | multi-report + matrix call | report, llm |
| `app.py` | user UI events | rendered page | UX, download wiring | all of the above |

Each module is independently testable: `config`, `report` parsing, `cache`, and
`export` are covered by 15 unit tests with no network calls (LLM is faked).

---

## 3. Primary data flow — single report

```
 USER
  │  "Sobha"
  ▼
app.single_tab ──► report.build("Sobha", provider, force)
                        │
              ┌─────────▼─────────┐
              │ 1. cache.key()    │  slug("sobha") + "__" + slug(provider)
              │    cache.get()    │──── HIT ──► return cached Report ──► render
              └─────────┬─────────┘
                        │ MISS
              ┌─────────▼─────────┐
              │ 2. research.gather│  pick first live search provider
              │    (company)      │  run 3 queries → Source[]   (or [] if no key)
              └─────────┬─────────┘
                        │ sources + provider_used
              ┌─────────▼─────────┐
              │ 3. _build_prompt()│  embed sources + strict JSON schema hint
              └─────────┬─────────┘
                        │ system + user prompt
              ┌─────────▼─────────┐
              │ 4. llm.generate() │  resolve provider → fallback chain
              │                   │  one structured JSON call
              └─────────┬─────────┘
                        │ raw text
              ┌─────────▼─────────┐
              │ 5. _extract_json()│  strip fences / outer braces → json.loads
              │    bad? ──► repair│  one retry: "return ONLY valid JSON"
              └─────────┬─────────┘
                        │ dict
              ┌─────────▼─────────┐
              │ 6. _coerce()      │  normalize categories/functions,
              │                   │  attach sources + meta
              └─────────┬─────────┘
                        │ Report
              ┌─────────▼─────────┐
              │ 7. cache.set()    │  persist JSON
              └─────────┬─────────┘
                        ▼
                 render + export
```

---

## 4. Provider abstraction & fallback

The core resilience mechanism. Both `llm.py` and `research.py` follow the same
pattern: **resolve a preferred provider, then walk the remaining available ones
as a fallback chain.**

```
config.available_llms()   →  ["groq", "gemini", "ollama", "anthropic"]   (priority order, only usable ones)

llm.generate(system, prompt, provider="gemini")
        │
        ▼
   chain = ["gemini"] + [others except gemini]   # preferred first
        │
        ▼
   for name in chain:
        try:    return _ADAPTERS[name](system, prompt), name   ──► SUCCESS, stop
        except: record error, continue                          ──► try next
   all failed → raise LLMError(all errors)
```

Why this matters for a demo: a rate-limited free key, a cold Ollama, or a flaky
network never produces a dead end as long as *one* provider works.

**Lazy imports:** each adapter imports its SDK *inside the function*. Installing
only `groq` and not `openai` is fine — the OpenAI adapter is never imported
unless called. Startup never breaks on a missing optional dependency.

### Adapter contract

Every LLM adapter has the identical signature and guarantees JSON-mode where the
SDK supports it:

```python
def _provider(system: str, prompt: str) -> str:   # returns raw model text
```

Every search adapter:

```python
def _provider(queries: list[str]) -> list[Source]   # Source = {title, url, text}
```

Adding a provider = write one function + register it in the `_ADAPTERS` dict +
add its env var to `config`. No other code changes.

---

## 5. Hybrid research — live vs. knowledge mode

```
                       config.available_search()
                              │
                ┌─────────────┴─────────────┐
            non-empty                      empty
                │                            │
        LIVE WEB MODE                 LLM-KNOWLEDGE MODE
                │                            │
   3 targeted queries on            sources = []
   first live provider:             prompt says "rely on
     • overview/business             your own knowledge"
     • recent news 2025/26          UI shows yellow banner
     • expansion/financials          meta.live_research = False
                │
   per-source text clipped to 1200 chars,
   capped at 8 sources (token budget for free models)
                │
   sources embedded in prompt as [1] [2] … with URLs
   → enables citations in the report
```

The system **never requires** a search key. Live data improves grounding and
adds citations; its absence is a labeled degradation, not a failure.

---

## 6. The prompt (core IP)

Located in `report.py` (`SYSTEM` + `SCHEMA_HINT` + `_build_prompt`). This is
where report *quality* is won — it is engineered against the assessment's main
risk: generic, could-apply-to-anyone output.

```
SYSTEM  → role: senior AI-solutions consultant; blunt on challenges,
          concrete on solutions; STRICT JSON only.

USER    → COMPANY: <name>
          RESEARCH SOURCES: [1]…[n] (or "no live sources — use knowledge")
          TASK: ground claims in sources; stay specific to this company.
          SCHEMA: exact keys + constraints that force specificity:
            • challenges[]  must carry category ∈ {operational, sales,
              customer_experience} AND a "reasoning" tied to segment/
              scale/geography  → satisfies assessment §3 sub-bullets
            • ai_opportunities[] must carry function ∈ {automation,
              customer_engagement, sales, operations, analytics,
              document_processing}, reference real offerings, state impact
              → satisfies §4, bans generic "add a chatbot"
            • pitch must hit 3 beats: why reached out / what found / what AI
              → satisfies §5
          Coverage rules: 3-4 challenges ≥2 categories;
                          4-5 opportunities ≥3 functions.
```

Single structured call returns all five sections at once → coherent, cheap,
fewer failure points than five per-section calls.

---

## 7. Multi-company comparison flow

```
compare(["Sobha","Prestige Group","Brigade Group"])
   │
   ├─ build() each company  ──► reuses single-report cache (fast on repeats)
   │      → [Report, Report, Report]
   │
   ├─ _profile() each: overview + top-3 challenges + top-3 opportunities
   │
   └─ one extra LLM call → JSON {"matrix": [...]}
          one row per company × columns:
          scale · geographic_reach · top_challenge ·
          ai_readiness · recommended_first_ai_win
   │
   ▼
CompareResult{reports, matrix}
   → UI: matrix as dataframe + N side-by-side report columns
```

Matrix is a *nicety*: if its JSON fails to parse, the individual reports still
render. No single point of failure.

---

## 8. Caching strategy

```
key   = slug(company) + "__" + slug(llm_provider)
store = cache/<key>.json   (full Report dict)

read  : build() unless force=True → cache.get → reconstruct via Report.from_dict
write : after successful generation
```

- Keyed by **company + model** so switching models regenerates (different model =
  different output worth seeing).
- `force=True` (UI checkbox / `--force`) bypasses read, still writes.
- Corrupt/missing file = silent cache miss (never crashes).
- Purpose: snappy demos + don't burn free-tier quota re-answering the same query.

---

## 9. Error handling matrix

| Failure | Layer | Behavior |
|---|---|---|
| No LLM key & no Ollama | config/report | Halt with setup instructions (UI) / `LLMError` (CLI) |
| No search key | research | Return `[]` → knowledge mode + banner |
| Search provider throws | research | Try next live provider; all fail → knowledge mode |
| LLM provider throws / rate-limited | llm | Try next provider in chain; all fail → `LLMError` |
| Model returns non-JSON | report | Strip fences/braces; one repair retry; else error to UI |
| PDF render error | export/app | `.md` still offered; caption shows the PDF error |
| Compare matrix bad JSON | compare | Reports still render; matrix omitted |
| Corrupt cache file | cache | Treated as miss |

Design rule: **a failure in an optional capability degrades that capability
only — never the whole request.**

---

## 10. Sequence diagram — UI request

```
User      app.py        report.py     research.py    llm.py        cache.py
 │          │              │              │            │              │
 │ click    │              │              │            │              │
 ├─Generate►│              │              │            │              │
 │          ├─build()─────►│              │            │              │
 │          │              ├─get()───────────────────────────────────►│
 │          │              │◄─────────────────────── miss ────────────┤
 │          │              ├─gather()────►│            │              │
 │          │              │              ├─search×3──►(Exa)           │
 │          │              │◄─ Source[] ──┤            │              │
 │          │              ├─generate()──────────────►│              │
 │          │              │              │            ├─adapter call─►(Groq)
 │          │              │◄────────── raw JSON ──────┤              │
 │          │              ├─parse + coerce            │              │
 │          │              ├─set()───────────────────────────────────►│
 │          │◄─ Report ─────┤              │            │              │
 │◄─render──┤              │              │            │              │
 │  +PDF/MD │              │              │            │              │
```

---

## 11. Tech stack & rationale

| Concern | Choice | Why |
|---|---|---|
| UI | Streamlit | Fastest path to a clean, demo-able web app in Python |
| LLM (free) | Groq, Gemini, OpenRouter, Ollama | Zero-cost demos; Ollama = fully offline |
| LLM (paid) | Anthropic, OpenAI | Quality ceiling when keys available |
| Search | Exa / Tavily / Firecrawl | LLM-oriented search APIs; any one suffices |
| PDF | fpdf2 | Pure-python, no system libs → works on Windows out of the box |
| Config | python-dotenv | Standard `.env` workflow |
| Tests | pytest | 15 tests, network-free (LLM faked) |

### Configurable models (set in `.env`)

Every provider uses its official SDK and reads its model from an env var, so you
swap models without touching code. OpenRouter reuses the OpenAI SDK (compatible
endpoint, different `base_url`).

| Provider | SDK | Env var | Default | Other options |
|---|---|---|---|---|
| Groq | `groq` | `GROQ_MODEL` | `llama-3.3-70b-versatile` | `mixtral-8x7b-32768`, `gemma2-9b-it` |
| Gemini | `google-generativeai` | `GEMINI_MODEL` | `gemini-2.0-flash` | `gemini-1.5-flash`, `gemini-1.5-pro` |
| OpenRouter | `openai` (base_url) | `OPENROUTER_MODEL` | `meta-llama/llama-3.3-70b-instruct:free` | `qwen/qwen-2.5-72b-instruct:free` |
| Ollama | `ollama` | `OLLAMA_MODEL` | `llama3.2` | any locally pulled model |
| Anthropic | `anthropic` | `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | `claude-opus-4-8`, `claude-haiku-4-5` |
| OpenAI | `openai` | `OPENAI_MODEL` | `gpt-4o` | `gpt-4o-mini`, `gpt-4-turbo` |

All six request JSON output (`response_format`/`format="json"`) where the SDK
supports it; the parser in `report.py` is the safety net for models that ignore it.

---

## 12. Extension points

- **New LLM/search provider** → add one adapter fn + register in `_ADAPTERS` + add
  env var to `config`. Zero changes elsewhere.
- **New report section** → extend `SCHEMA_HINT`, the `Report` dataclass, `_coerce`,
  and renderers in `export.py` / `app.py`.
- **Persistent store** → swap `cache.py` internals (same `get`/`set` interface) for
  Redis/SQLite without touching callers.
- **API server** → `report.build()` is UI-agnostic; wrap it in FastAPI for a REST
  endpoint reusing the entire core.
```
