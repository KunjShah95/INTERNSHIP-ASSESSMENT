"""Provider detection should follow env keys and priority order."""
import importlib

import agent.config as config


def reload_with(monkeypatch, **env):
    # clear everything the module cares about, then set what the test wants
    for k in list(config._LLM_ENV.values()) + list(config._SEARCH_ENV.values()) + \
            ["LLM_PROVIDER", "SEARCH_PROVIDER"]:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # ollama off unless a test opts in
    monkeypatch.setattr(config, "_ollama_up", lambda: env.get("_ollama", False))
    return config


def test_no_keys_means_no_providers(monkeypatch):
    c = reload_with(monkeypatch)
    assert c.available_llms() == []
    assert c.available_search() == []
    assert c.default_llm() is None
    assert c.status().live_research is False


def test_priority_order(monkeypatch):
    c = reload_with(monkeypatch, OPENAI_API_KEY="x", GROQ_API_KEY="y")
    # groq is higher priority than openai
    assert c.default_llm() == "groq"
    assert c.available_llms() == ["groq", "openai"]


def test_forced_provider_overrides_default(monkeypatch):
    c = reload_with(monkeypatch, GROQ_API_KEY="y", OPENAI_API_KEY="x",
                    LLM_PROVIDER="openai")
    assert c.default_llm() == "openai"


def test_forced_provider_ignored_if_unavailable(monkeypatch):
    c = reload_with(monkeypatch, GROQ_API_KEY="y", LLM_PROVIDER="openai")
    assert c.default_llm() == "groq"


def test_search_detection(monkeypatch):
    c = reload_with(monkeypatch, TAVILY_API_KEY="t")
    assert c.available_search() == ["tavily"]
    assert c.status().live_research is True
