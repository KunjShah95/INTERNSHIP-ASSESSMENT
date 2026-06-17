"""Competitive landscape — JSON parsing, coercion, and fake-LLM end-to-end build."""
from __future__ import annotations

import json

import agent.export as export
import agent.landscape as landscape
import agent.report as report
import agent.research as research

FAKE_LANDSCAPE = {
    "market_overview": "The Indian real estate market is growing at 9-11% CAGR "
                       "driven by urbanization and affordable housing demand.",
    "positioning": [
        {
            "company": "Sobha",
            "scale": "Large — 40+ projects across 10 cities",
            "price_tier": "Premium — luxury residential focus",
            "geographic_reach": "National — strong in South India",
            "key_strength": "Vertically integrated build quality",
            "key_weakness": "Limited presence in affordable segment",
        },
    ],
    "strengths_weaknesses": [
        {
            "company": "Sobha",
            "strengths": [
                "Vertical integration (owns construction arm)",
                "Strong brand in luxury residential",
                "Consistent delivery track record",
            ],
            "weaknesses": [
                "High geographic concentration in South India",
                "Limited exposure to commercial real estate",
                "Premium positioning limits addressable market",
            ],
            "ai_readiness": "Medium — some digital but no visible AI strategy",
        },
    ],
    "strategic_gaps": [
        {
            "gap": "AI-driven customer segmentation",
            "description": "No company uses predictive analytics for buyer targeting",
            "opportunity_size": "15-20% improvement in sales conversion",
            "best_positioned": "Sobha — has the largest customer database",
        },
    ],
    "recommendations": {
        "Sobha": "Invest in AI-powered buyer analytics to improve "
                 "conversion in the premium segment.",
    },
}

FAKE_REPORT = {
    "overview": "Sobha is a luxury real estate developer.",
    "business": "Operates in 10 cities across India.",
    "challenges": [
        {"category": "Sales", "title": "Long sales cycles",
         "reasoning": "Premium pricing extends decision timelines."},
    ],
    "ai_opportunities": [
        {"function": "Analytics", "title": "Buyer predictions",
         "description": "Predict which prospects convert.",
         "impact": "20% higher close rate."},
    ],
    "pitch": "Dear Sobha CEO, AI can shorten your sales cycle.",
}


def test_extract_plain_json():
    d = landscape._extract_json(json.dumps(FAKE_LANDSCAPE))
    assert d["market_overview"].startswith("The Indian")


def test_extract_json_with_code_fence():
    text = "Here:\n```json\n" + json.dumps(FAKE_LANDSCAPE) + "\n```"
    d = landscape._extract_json(text)
    assert "strategic_gaps" in d


def test_cache_key_is_filesystem_safe():
    k = landscape._cache_key(["Sobha Ltd.", "Prestige Group"], "groq")
    assert "/" not in k and " " not in k


def test_roundtrip():
    l = landscape.CompetitiveLandscape(
        industry="real estate",
        companies=["Sobha"],
        market_overview="Growing market.",
        positioning=[{"company": "Sobha", "scale": "Large"}],
        strengths_weaknesses=[{"company": "Sobha", "strengths": [], "weaknesses": [],
                               "ai_readiness": "Medium"}],
        strategic_gaps=[{"gap": "AI gap", "description": "No AI",
                         "opportunity_size": "Big", "best_positioned": "Sobha"}],
        recommendations={"Sobha": "Invest in AI."},
        sources=[{"title": "Source"}],
        meta={"llm_provider": "groq", "companies": ["Sobha"]},
    )
    d = l.to_dict()
    assert d["industry"] == "real estate"
    l2 = landscape.CompetitiveLandscape.from_dict(d)
    assert l2.market_overview == "Growing market."
    assert l2.recommendations["Sobha"] == "Invest in AI."
    assert l2.meta["llm_provider"] == "groq"


def test_markdown_has_all_sections():
    l = landscape.CompetitiveLandscape(
        industry="",
        companies=["Sobha", "Prestige"],
        market_overview="Test market.",
        positioning=[{"company": "Sobha", "scale": "Large"}],
        strengths_weaknesses=[{"company": "Sobha", "strengths": ["Quality"],
                               "weaknesses": ["Cost"], "ai_readiness": "Medium"}],
        strategic_gaps=[{"gap": "AI", "description": "desc",
                         "opportunity_size": "X", "best_positioned": "Sobha"}],
        recommendations={"Sobha": "Do AI.", "Prestige": "Also AI."},
    )
    md = export.landscape_to_markdown(l)
    for heading in ["Market Overview", "Competitive Positioning",
                    "Strengths & Weaknesses", "Strategic Gaps",
                    "Strategic Recommendations"]:
        assert heading in md


def test_pdf_returns_bytes():
    l = landscape.CompetitiveLandscape(
        industry="", companies=["Sobha"], market_overview="Test.",
        positioning=[], strengths_weaknesses=[], strategic_gaps=[],
        recommendations={},
    )
    pdf = export.landscape_to_pdf(l)
    assert isinstance(pdf, (bytes, bytearray))
    assert pdf[:4] == b"%PDF"


def test_build_with_fake_llm(monkeypatch):
    monkeypatch.setattr(research, "gather", lambda *a, **k: ([], None))
    monkeypatch.setattr(report.cache, "get", lambda k: None)
    monkeypatch.setattr(report.cache, "set", lambda k, d: None)
    monkeypatch.setattr(report.config, "default_llm", lambda: "groq")
    monkeypatch.setattr(report.llm, "generate",
                        lambda s, p, provider=None: (json.dumps(FAKE_REPORT), "groq"))

    landscape_calls = {"n": 0}

    def fake_landscape_llm(s, p, provider=None):
        landscape_calls["n"] += 1
        return json.dumps(FAKE_LANDSCAPE), "groq"

    monkeypatch.setattr(landscape.cache_mod, "get", lambda k: None)
    monkeypatch.setattr(landscape.cache_mod, "set", lambda k, d: None)
    monkeypatch.setattr(landscape.llm, "generate", fake_landscape_llm)

    l = landscape.build(["Sobha", "Prestige", "Brigade"], force=True)
    assert l.market_overview.startswith("The Indian")
    assert "Sobha" in l.recommendations
    assert len(l.companies) == 3
    assert landscape_calls["n"] == 4  # 3 reports + 1 landscape


def test_requires_at_least_3_companies():
    import pytest
    with pytest.raises(ValueError, match="at least 3"):
        landscape.build(["Sobha", "Prestige"], force=True)
