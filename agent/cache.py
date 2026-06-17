"""=== CacheAgent ==============================================================

ROLE:
  Persist and retrieve JSON-serialized data to/from the local filesystem.
  Keeps demos snappy and avoids burning free-tier quota on repeat requests.

SYSTEM PROMPT (module identity):
  "I am the CacheAgent. I write JSON to disk under cache/ and read it back.
   I use slugs derived from company+model as filenames. Corrupt data returns
   None (cache miss). I am stateless — every call reads or writes directly."

CONTEXT:
  Inputs:  String key (company+model slug), dict data to store
  Outputs: dict from cache, or None on miss/corruption
  State:   cache/ directory on disk
  Key format: "{slug(company)}__{slug(provider)}.json"

BOUNDARIES:
  I do NOT:
  - Generate or modify content
  - Make any network calls
  - Know about report structure, LLM providers, or business logic
  - Import any SDK package
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parent.parent / "cache"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def key(company: str, provider: str) -> str:
    return f"{_slug(company)}__{_slug(provider)}"


def _path(k: str) -> Path:
    return CACHE_DIR / f"{k}.json"


def get(k: str) -> dict | None:
    p = _path(k)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt cache = cache miss
        return None


def set(k: str, data: dict) -> None:  # noqa: A001 — small, local API
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _path(k).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                        encoding="utf-8")
