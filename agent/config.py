"""=== ConfigAgent ============================================================

ROLE:
  Read the environment and report which LLM and search providers are usable.
  Pure functions with no side effects — kept free of SDK imports.

SYSTEM PROMPT (module identity):
  "I am the ConfigAgent. I read environment variables, .env files, and detect
   available LLM and search providers. I maintain priority ordering (free/open
   first, paid last). I do nothing else."

CONTEXT:
  Inputs:  OS environment variables, .env file, local Ollama process
  Outputs: ProviderStatus dataclass, lists of available providers, defaults
  State:   Module-level constants (LLM_PRIORITY, _LLM_ENV, etc.)

BOUNDARIES:
  I do NOT:
  - Make LLM API calls
  - Cache data to disk
  - Generate reports or prompts
  - Import any SDK package at module level
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Priority order: free/open-source first (cheap demos), paid last.
LLM_PRIORITY = ["groq", "gemini", "openrouter", "ollama", "anthropic", "openai"]
SEARCH_PRIORITY = ["exa", "tavily", "firecrawl"]

# env var that gates each provider (Ollama is special-cased below).
_LLM_ENV = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}
_SEARCH_ENV = {
    "exa": "EXA_API_KEY",
    "tavily": "TAVILY_API_KEY",
    "firecrawl": "FIRECRAWL_API_KEY",
}

LLM_LABELS = {
    "groq": "Groq · Llama 3.3 70B (free)",
    "gemini": "Google Gemini 2.0 Flash (free)",
    "openrouter": "OpenRouter (free open models)",
    "ollama": "Ollama (local, open-source)",
    "anthropic": "Anthropic Claude (paid)",
    "openai": "OpenAI GPT-4o (paid)",
}


@dataclass
class ProviderStatus:
    llms: list[str]          # available LLM providers, priority order
    searches: list[str]      # available search providers, priority order
    default_llm: str | None
    default_search: str | None
    live_research: bool      # True if any search provider is usable


def _key(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _ollama_up() -> bool:
    """Detect a local Ollama server. Best-effort, never raises."""
    host = _key("OLLAMA_HOST") or "http://localhost:11434"
    try:
        import requests

        requests.get(f"{host}/api/tags", timeout=0.75)
        return True
    except Exception:
        return False


def available_llms() -> list[str]:
    out = [p for p in LLM_PRIORITY if p in _LLM_ENV and _key(_LLM_ENV[p])]
    if "ollama" not in out and _ollama_up():
        # keep ollama in its priority slot
        idx = LLM_PRIORITY.index("ollama")
        out = [p for p in LLM_PRIORITY[:idx] if p in out] + ["ollama"] + \
              [p for p in LLM_PRIORITY[idx + 1:] if p in out]
    return out


def available_search() -> list[str]:
    return [p for p in SEARCH_PRIORITY if _key(_SEARCH_ENV[p])]


def default_llm() -> str | None:
    forced = _key("LLM_PROVIDER")
    avail = available_llms()
    if forced and forced in avail:
        return forced
    return avail[0] if avail else None


def default_search() -> str | None:
    forced = _key("SEARCH_PROVIDER")
    avail = available_search()
    if forced and forced in avail:
        return forced
    return avail[0] if avail else None


def status() -> ProviderStatus:
    llms = available_llms()
    searches = available_search()
    return ProviderStatus(
        llms=llms,
        searches=searches,
        default_llm=default_llm(),
        default_search=default_search(),
        live_research=bool(searches),
    )
