"""Cache round-trip and export shape."""
import agent.cache as cache
import agent.export as export
from agent.report import Challenge, Opportunity, Report


def _sample() -> Report:
    return Report(
        company="Acme",
        overview="Builds widgets.",
        business="Sells globally.",
        challenges=[Challenge("operational", "Scaling", "Demand spikes.")],
        ai_opportunities=[Opportunity("analytics", "Forecaster",
                                      "Predict demand.", "Less waste.")],
        pitch="Dear CEO...",
        sources=[{"title": "About", "url": "http://x"}],
        meta={"llm_provider": "groq", "search_provider": None,
              "live_research": False},
    )


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    k = cache.key("Acme Corp", "groq")
    assert cache.get(k) is None
    cache.set(k, _sample().to_dict())
    got = cache.get(k)
    assert got["company"] == "Acme"
    # report reconstructs from cache dict
    r = Report.from_dict(got)
    assert r.challenges[0].category == "operational"


def test_slug_keys_are_filesystem_safe():
    k = cache.key("Adani Realty / Ltd.", "groq")
    assert "/" not in k and " " not in k


def test_markdown_has_all_sections():
    md = export.to_markdown(_sample())
    for heading in ["1. Company Overview", "2. Key Business Information",
                    "3. Potential Business Challenges", "4. AI Opportunities",
                    "5. Personalized Pitch"]:
        assert heading in md


def test_pdf_returns_bytes():
    pdf = export.to_pdf(_sample())
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:4] == b"%PDF"
