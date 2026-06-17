"""=== LLMAgent =================================================================

ROLE:
  Route a (system prompt, user prompt) pair to an available LLM provider and
  return the generated text. Wraps 6 providers behind one `generate()` call
  with automatic fallback — if Groq fails, try Gemini, then OpenRouter, etc.

SYSTEM PROMPT (module identity):
  "I am the LLMAgent. I accept a system prompt and a user prompt and route them
   to the best available LLM provider. I try the requested provider first, then
   fall through the remaining configured providers in priority order. I do not
   write prompts — I only execute them. I do not research. I do not cache."

CONTEXT:
  Inputs:  system (str), prompt (str), optional provider name
  Outputs: (response_text: str, provider_used: str)
  Providers: groq, gemini, openrouter, ollama, anthropic, openai
  All SDKs imported LAZILY inside adapter functions

BOUNDARIES:
  I do NOT:
  - Write or modify prompts (that is the calling agent's job)
  - Do web research
  - Cache results
  - Parse or validate JSON output
  - Export or format content
"""
from __future__ import annotations

import os

from . import config


class LLMError(RuntimeError):
    pass


# ── individual adapters ────────────────────────────────────────────────

def _groq(system: str, prompt: str) -> str:
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _gemini(system: str, prompt: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        system_instruction=system,
        generation_config={"response_mime_type": "application/json",
                           "temperature": 0.4},
    )
    return model.generate_content(prompt).text


def _openrouter(system: str, prompt: str) -> str:
    # OpenRouter is OpenAI-compatible → reuse the official OpenAI SDK, only the
    # base_url changes. One SDK, two providers.
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"],
                    base_url="https://openrouter.ai/api/v1")
    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _ollama(system: str, prompt: str) -> str:
    # Official Ollama Python SDK.
    import ollama

    host = os.getenv("OLLAMA_HOST")
    client = ollama.Client(host=host) if host else ollama.Client()
    model = os.getenv("OLLAMA_MODEL", "llama3.2")
    resp = client.chat(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0.4},
    )
    return resp["message"]["content"]


def _anthropic(system: str, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    msg = client.messages.create(
        model=model,
        max_tokens=4096,
        temperature=0.4,
        system=system + "\nReturn ONLY valid JSON, no prose, no code fences.",
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def _openai(system: str, prompt: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": prompt}],
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


_ADAPTERS = {
    "groq": _groq,
    "gemini": _gemini,
    "openrouter": _openrouter,
    "ollama": _ollama,
    "anthropic": _anthropic,
    "openai": _openai,
}


# ── public API ─────────────────────────────────────────────────────────

def generate(system: str, prompt: str, provider: str | None = None) -> tuple[str, str]:
    """Return (text, provider_used).

    Resolves the provider (explicit arg → config default), then walks the
    remaining available providers as a fallback chain if a call fails.
    """
    avail = config.available_llms()
    if not avail:
        raise LLMError(
            "No LLM provider configured. Set one key in .env "
            "(GROQ_API_KEY / GEMINI_API_KEY / ...) or run Ollama locally."
        )

    if provider and provider in avail:
        chain = [provider] + [p for p in avail if p != provider]
    else:
        chain = avail

    errors: list[str] = []
    for name in chain:
        try:
            return _ADAPTERS[name](system, prompt), name
        except Exception as e:  # noqa: BLE001 — record and try the next provider
            errors.append(f"{name}: {e}")
    raise LLMError("All LLM providers failed:\n" + "\n".join(errors))
