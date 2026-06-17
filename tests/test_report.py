"""Report JSON parsing, coercion, and a fake-LLM end-to-end build."""
import json

import agent.report as report
import agent.research as research


FAKE = {
    "overview": "Acme builds widgets.",
    "business": "Sells widgets globally.",
    "challenges": [
        {"category": "Sales", "title": "Long cycles",
         "reasoning": "Enterprise deals take months."}
    ],
    "ai_opportunities": [
        {"function": "Document Processing", "title": "Contract parser",
         "description": "Parse vendor contracts.", "impact": "Saves 20h/week."}
    ],
    "pitch": "Dear CEO, ...",
}


def test_extract_plain_json():
    d = report._extract_json(json.dumps(FAKE))
    assert d["overview"].startswith("Acme")


def test_extract_json_with_code_fence():
    text = "Here you go:\n```json\n" + json.dumps(FAKE) + "\n```\nThanks!"
    d = report._extract_json(text)
    assert d["pitch"].startswith("Dear CEO")


def test_extract_json_with_surrounding_prose():
    text = "Sure! {" + json.dumps(FAKE)[1:-1] + "} end"
    d = report._extract_json(text)
    assert "challenges" in d


def test_coerce_normalizes_categories_and_functions():
    r = report._coerce("Acme", FAKE, sources=[], provider="groq",
                       search_provider=None)
    assert r.challenges[0].category == "sales"          # "Sales" -> "sales"
    assert r.ai_opportunities[0].function == "document_processing"  # spaces -> _
    assert r.meta["live_research"] is False


def test_build_with_fake_llm(monkeypatch):
    # no live research
    monkeypatch.setattr(research, "gather", lambda *a, **k: ([], None))
    # deterministic provider + llm output
    monkeypatch.setattr(report.config, "default_llm", lambda: "groq")
    monkeypatch.setattr(report.llm, "generate",
                        lambda system, prompt, provider=None: (json.dumps(FAKE), "groq"))
    # don't touch disk
    monkeypatch.setattr(report.cache, "get", lambda k: None)
    monkeypatch.setattr(report.cache, "set", lambda k, d: None)

    r = report.build("Acme", force=True)
    assert r.company == "Acme"
    assert r.meta["llm_provider"] == "groq"
    assert r.challenges[0].category == "sales"


def test_build_repairs_bad_json(monkeypatch):
    calls = {"n": 0}

    def flaky(system, prompt, provider=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "not json at all", "groq"
        return json.dumps(FAKE), "groq"

    monkeypatch.setattr(research, "gather", lambda *a, **k: ([], None))
    monkeypatch.setattr(report.config, "default_llm", lambda: "groq")
    monkeypatch.setattr(report.llm, "generate", flaky)
    monkeypatch.setattr(report.cache, "get", lambda k: None)
    monkeypatch.setattr(report.cache, "set", lambda k, d: None)

    r = report.build("Acme", force=True)
    assert calls["n"] == 2          # repaired on second try
    assert r.overview.startswith("Acme")
