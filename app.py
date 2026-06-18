"""=== UIAgent ==================================================================

ROLE:
  Present the system to end users via a polished Streamlit web interface.
  Handles user input, orchestrates backend agents, renders results.
  Contains NO business logic — strictly presentation and orchestration.

SYSTEM PROMPT (module identity):
  "I am the UIAgent. I provide a Streamlit UI with three tabs:
   (1) Single Report — user enters a company name, I call ReportAgent and render
   (2) Compare — user enters 2+ companies, I call CompareAgent and render
   (3) Competitive Landscape — user enters 3-5 companies, I call LandscapeAgent
   I handle user input validation, loading spinners, error display, and download
   buttons. I never generate content — I only call other agents and render."

CONTEXT:
  Inputs:  User-provided company names via Streamlit widgets
  Outputs: Rendered Streamlit UI with reports, downloads
  Depends on: ConfigAgent, ReportAgent, CompareAgent, LandscapeAgent, ExportAgent

BOUNDARIES:
  I do NOT:
  - Generate any reports, comparisons, or analyses
  - Write prompts for LLMs (that's ReportAgent/CompareAgent/LandscapeAgent)
  - Cache data (that's CacheAgent)
  - Export to files (that's ExportAgent — I just call it and present results)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import streamlit as st

from agent import __version__ as agent_version
from agent import compare as compare_mod
from agent import config, export, landscape, report

st.set_page_config(
    page_title="AI Research & Recommendation Agent",
    page_icon="🔎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── constants ──────────────────────────────────────────────────────────────

_DEMO_COMPANIES = ["Sobha", "Prestige Group", "Brigade Group", "Adani Realty"]
_SAMPLE_COMPANIES = ["Puravankara", "Godrej Properties", "DLF", "Lodha Group"]

_CAT_EMOJI = {"operational": "🛠️", "sales": "💼", "customer_experience": "🙋"}
_CAT = {"operational": "Operational", "sales": "Sales",
        "customer_experience": "Customer Experience"}
_FN_EMOJI = {"automation": "⚙️", "customer_engagement": "💬", "sales": "📈",
             "operations": "🏭", "analytics": "📊", "document_processing": "📄"}
_FN = {"automation": "Automation", "customer_engagement": "Customer Engagement",
       "sales": "Sales", "operations": "Operations",
       "analytics": "Analytics", "document_processing": "Document Processing"}

_PROVIDER_MODELS = {
    "groq": ["llama-3.3-70b-versatile", "deepseek-r1-distill-llama-70b",
             "mixtral-8x7b-32768", "gemma2-9b-it"],
    "gemini": ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
    "openrouter": ["meta-llama/llama-3.3-70b-instruct:free",
                   "qwen/qwen-2.5-72b-instruct:free"],
    "ollama": ["llama3.2", "qwen3.5:9b", "gemma4:12b-it-qat"],
    "anthropic": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
    "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
}

_CSS = """
<style>
    .main > div { padding-bottom: 2rem; }
    .stApp { background: #0f172a; }
    .block-container { padding-top: 1.5rem !important; max-width: 1200px; }
    h1, h2, h3, h4, h5, h6 { font-weight: 600; letter-spacing: -0.01em; color: #f1f5f9; }
    p, li, .stMarkdown, .stText { color: #cbd5e1; }
    .st-cx, .st-bb, .st-c8, .st-bw { color: #cbd5e1; }
    input, textarea { background: #1e293b !important; color: #f1f5f9 !important;
        border: 1px solid #334155 !important; border-radius: 8px !important; }
    input::placeholder, textarea::placeholder { color: #64748b !important; }
    .stSelectbox div[data-baseweb="select"] > div {
        background: #1e293b !important; border: 1px solid #334155 !important;
        color: #f1f5f9 !important; border-radius: 8px !important; }
    .stSelectbox ul { background: #1e293b !important; }
    .stSelectbox li:hover { background: #334155 !important; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] { gap: 0; background: #1e293b; padding: 4px;
        border-radius: 10px; border: 1px solid #334155; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px; padding: 8px 20px;
        font-weight: 500; font-size: 0.9rem; transition: all 0.15s; color: #94a3b8; }
    .stTabs [aria-selected="true"] { background: #3b82f6; color: white !important; }
    .stTabs [data-baseweb="tab"]:hover { color: #f1f5f9; }

    /* Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border: 1px solid #334155; border-radius: 10px;
        background: #1e293b; padding: 0.25rem 1rem; margin-bottom: 0.75rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: 0 4px 12px rgba(0,0,0,0.3); }

    /* Buttons */
    .stButton button { font-weight: 500; border-radius: 8px; transition: all 0.15s; }
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white; border: none; box-shadow: 0 1px 3px rgba(59,130,246,0.3); }
    .stButton button[kind="primary"]:hover {
        box-shadow: 0 2px 8px rgba(59,130,246,0.5); transform: translateY(-1px); }
    div.stDownloadButton button {
        border-radius: 8px; font-weight: 500;
        border: 1px solid #334155; background: #1e293b; color: #cbd5e1; }
    div.stDownloadButton button:hover { border-color: #3b82f6; color: #60a5fa; }

    /* Checkbox */
    .stCheckbox label { color: #cbd5e1 !important; }
    .stCheckbox div[data-baseweb="checkbox"] > div {
        background: #334155 !important; border-color: #475569 !important; }

    /* Alerts */
    .stAlert { border-radius: 10px; border: none !important; padding: 0.75rem 1rem; }
    .stInfo { background: #1e3a5f; border-left: 4px solid #3b82f6; color: #bfdbfe; }
    .stWarning { background: #3b2f1a; border-left: 4px solid #f59e0b; color: #fde68a; }
    .stError { background: #3b1a1a; border-left: 4px solid #ef4444; color: #fecaca; }
    .stSuccess { background: #1a3b1a; border-left: 4px solid #22c55e; color: #bbf7d0; }
    .stAlert p { color: inherit; }

    /* DataFrames */
    div[data-testid="stDataFrame"] {
        border: 1px solid #334155; border-radius: 10px; overflow: hidden; }
    .stDataFrame [data-testid="StyledDataFrameColHeader"] {
        background: #1e293b !important; color: #f1f5f9 !important; }
    .stDataFrame td { background: #0f172a !important; color: #cbd5e1 !important; }

    /* Expanders */
    .st-emotion-cache-1jicfl2, .st-emotion-cache-1it4cgn { color: #cbd5e1; }
    div[data-testid="stExpander"] { border: 1px solid #334155; border-radius: 8px;
        background: #1e293b; }
    div[data-testid="stExpander"] summary { color: #f1f5f9; font-weight: 500; }

    /* Sidebar */
    section[data-testid="stSidebar"] { background: #0f172a; border-right: 1px solid #1e293b; }
    section[data-testid="stSidebar"] .stMarkdown { color: #cbd5e1; }
    section[data-testid="stSidebar"] h2 { color: #f1f5f9; }

    /* Dividers */
    hr { border-color: #334155 !important; }

    /* Section headers */
    .section-header {
        margin-top: 1.5rem; margin-bottom: 0.5rem; padding-bottom: 0.25rem;
        border-bottom: 2px solid #3b82f6; display: inline-block; color: #f1f5f9; }

    /* Footer */
    footer { font-size: 0.75rem; color: #475569; text-align: center;
        padding-top: 2rem; border-top: 1px solid #1e293b; margin-top: 3rem; }

    /* Spinner */
    .stSpinner > div { border-color: #3b82f6 !important; }
    .stSpinner p { color: #94a3b8; }

    /* Metric labels */
    [data-testid="stMetricLabel"] p { color: #94a3b8; }
    [data-testid="stMetricValue"] { color: #f1f5f9; }

    /* Captions */
    .stCaption, .st-caption { color: #64748b; }

    /* Dataframe sort & filter buttons */
    button[kind="tertiary"] { color: #94a3b8 !important; }
</style>
"""


def _inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


# ── status dashboard ──────────────────────────────────────────────────────

def _dot(ok: bool) -> str:
    return "🟢" if ok else "🔴"


def _render_dashboard() -> None:
    stat = config.status()
    cache_dir = Path(__file__).resolve().parent / "cache"
    cache_count = len(list(cache_dir.glob("*.json"))) if cache_dir.exists() else 0

    st.sidebar.markdown("---")
    with st.sidebar.expander("📊 System Status", expanded=True):
        st.markdown(f"**v{agent_version}**")
        st.caption("9 specialized agents · 6 LLM providers · 3 search providers")

        st.markdown("**LLM Providers**")
        for p in config.LLM_PRIORITY:
            ok = p in stat.llms
            label = config.LLM_LABELS.get(p, p)
            st.markdown(f"{_dot(ok)} {label}")

        st.markdown("**Search Providers**")
        for p in config.SEARCH_PRIORITY:
            ok = p in stat.searches
            st.markdown(f"{_dot(ok)} {p.title()}")

        st.markdown(f"**Cache** {_dot(cache_count > 0)} {cache_count} reports")

    if not stat.llms:
        st.sidebar.error(
            "No LLM configured.\n\n"
            "Copy `.env.example` → `.env`, add one key "
            "(GROQ_API_KEY is free at console.groq.com), or run Ollama locally."
        )


# ── sidebar ───────────────────────────────────────────────────────────────

_API_KEY_ENTRIES = [
    ("GROQ_API_KEY", "Groq (free LLM)", "gsk_..."),
    ("GEMINI_API_KEY", "Gemini (free LLM)", "AIza..."),
    ("OPENROUTER_API_KEY", "OpenRouter (free LLM)", "sk-or-..."),
    ("ANTHROPIC_API_KEY", "Anthropic Claude (paid)", "sk-ant-..."),
    ("OPENAI_API_KEY", "OpenAI GPT (paid)", "sk-..."),
    ("EXA_API_KEY", "Exa (web search)", "your_exa_key"),
    ("TAVILY_API_KEY", "Tavily (web search)", "tvly-..."),
    ("FIRECRAWL_API_KEY", "Firecrawl (web search)", "fc-..."),
]


def _render_api_keys() -> None:
    with st.sidebar.expander("🔑 API Keys", expanded=False):
        any_filled = False
        for env_key, label, ph in _API_KEY_ENTRIES:
            is_set = bool(os.environ.get(env_key, "").strip())
            prev = os.environ.get(env_key, "")
            label_disp = f"{'🟢' if is_set else '⚪'} {label}"
            val = st.text_input(
                label_disp, placeholder="Configured ✓" if is_set else ph,
                type="password", key=f"apikey_{env_key}",
                label_visibility="collapsed",
            )
            if val and val != prev:
                os.environ[env_key] = val
                any_filled = True
        if any_filled:
            st.rerun()


def _render_sidebar() -> tuple[str | None, bool]:
    st.sidebar.markdown(
        "<h2 style='margin-bottom:0'>🔎 Research Agent</h2>"
        "<p style='color:#64748b;font-size:0.85rem;margin-top:-0.25rem'>"
        f"v{agent_version} — Intelligence reports & AI opportunity analysis</p>",
        unsafe_allow_html=True,
    )

    _render_api_keys()
    _render_dashboard()

    st.sidebar.markdown("---")
    st.sidebar.markdown("#### ⚙️ Settings")

    stat = config.status()
    if not stat.llms:
        return None, False

    choices = ["auto"] + stat.llms
    labels = {"auto": f"Auto ({config.LLM_LABELS.get(stat.default_llm, stat.default_llm)})"}
    labels.update({p: config.LLM_LABELS.get(p, p) for p in stat.llms})
    pick = st.sidebar.selectbox(
        "LLM provider", choices, format_func=lambda x: labels[x],
        label_visibility="collapsed",
    )
    provider = None if pick == "auto" else pick

    st.sidebar.markdown("#### 🌐 Research")
    if stat.live_research:
        st.sidebar.success(f"Live web — {', '.join(stat.searches)}")
    else:
        st.sidebar.warning("LLM-knowledge mode (no search key)")

    force = st.sidebar.checkbox("🔄 Force refresh", value=False,
                                help="Ignore cached reports and regenerate")

    st.sidebar.markdown("#### 🧠 Model")
    if provider and provider in _PROVIDER_MODELS:
        model_key = f"{provider.upper()}_MODEL"
        current = os.getenv(model_key) or _PROVIDER_MODELS[provider][0]
        models = _PROVIDER_MODELS[provider]
        idx = models.index(current) if current in models else 0
        pick = st.sidebar.selectbox("Model", models, index=idx,
                                    label_visibility="collapsed",
                                    key="sidebar_model_sel")
        os.environ[model_key] = pick
    else:
        st.sidebar.caption("Auto (default model)")

    st.sidebar.markdown("---")
    with st.sidebar.expander("🏗️ Architecture", expanded=False):
        st.markdown("**9 specialized agents:**")
        agents = [
            ("Config", "Env & provider detection"),
            ("Cache", "Disk-backed report caching"),
            ("Research", "Web search (Exa/Tavily/Firecrawl)"),
            ("LLM", "Multi-provider LLM dispatch"),
            ("Report", "Core report generation pipeline"),
            ("Compare", "Multi-company comparison matrix"),
            ("Landscape", "Competitive landscape analysis"),
            ("Export", "PDF export"),
            ("UI", "Streamlit presentation layer"),
        ]
        for name, role in agents:
            st.markdown(f"**{name}** — {role}")

    return provider, force


# ── onboarding hero ───────────────────────────────────────────────────────

def _render_hero(provider: str | None) -> None:
    cache_dir = Path(__file__).resolve().parent / "cache"
    is_first_run = not any(cache_dir.glob("*.json")) if cache_dir.exists() else True

    st.markdown(
        "<h1 style='margin-bottom:0.25rem'>🔎 AI-Powered Research &"
        " Recommendation Agent</h1>"
        "<p style='color:#64748b;font-size:1.05rem;margin-top:0'>"
        "Company name → structured intelligence report → AI-opportunity pitch.</p>",
        unsafe_allow_html=True,
    )

    if is_first_run:
        stat = config.status()
        has_llm = bool(stat.llms)
        with st.container(border=True):
            st.markdown("#### 👋 Welcome!")
            if has_llm:
                st.markdown(f"✅ **{stat.llms[0].title()}** is ready — type a company name and generate.")
            else:
                st.markdown("""
                Add an API key in the **sidebar → 🔑 API Keys** to get started.
                """)
            st.markdown("Pick a demo company below or type your own company name.")


# ── quick-select chips ────────────────────────────────────────────────────

def _demo_chips(key: str = "company") -> str | None:
    """Render clickable demo-company chips. Returns selected company or None."""
    st.markdown("##### Try these companies")
    cols = st.columns(len(_DEMO_COMPANIES))
    for i, (col, name) in enumerate(zip(cols, _DEMO_COMPANIES)):
        with col:
            if st.button(name, key=f"chip_{key}_{i}", width="stretch"):
                return name
    return None


# ── meta banner ───────────────────────────────────────────────────────────

def _meta_banner(meta: dict) -> None:
    cols = st.columns([2, 2, 5])
    with cols[0]:
        llm = meta.get("llm_provider", "?")
        st.markdown(f"**LLM:** `{llm}`")
    with cols[1]:
        search = meta.get("search_provider") or "none"
        st.markdown(f"**Search:** `{search}`")
    if not meta.get("live_research"):
        with cols[2]:
            st.info("ℹ️ LLM-knowledge mode — add EXA/TAVILY/FIRECRAWL key for live web data")


# ── section helper ────────────────────────────────────────────────────────

def _header(text: str, emoji: str = "📋") -> None:
    st.markdown(
        f"<h3 class='section-header'>{emoji} {text}</h3>",
        unsafe_allow_html=True,
    )


# ── render report ─────────────────────────────────────────────────────────

def render_report(r: report.Report) -> None:
    _meta_banner(r.meta)

    _header("Company Overview", "🏢")
    st.write(r.overview)

    _header("Key Business Information", "📊")
    st.write(r.business)

    _header("Potential Business Challenges", "⚠️")
    for c in r.challenges:
        emoji = _CAT_EMOJI.get(c.category, "📌")
        with st.container(border=True):
            st.markdown(f"**{emoji} {_CAT.get(c.category, c.category)} — {c.title}**")
            st.write(c.reasoning)

    _header("AI Opportunities", "💡")
    for o in r.ai_opportunities:
        emoji = _FN_EMOJI.get(o.function, "✨")
        with st.container(border=True):
            st.markdown(f"**{emoji} {_FN.get(o.function, o.function)} — {o.title}**")
            st.write(o.description)
            st.caption(f"**Impact:** {o.impact}")

    _header("Personalized Pitch", "🎯")
    st.info(r.pitch)

    if r.sources:
        with st.expander(f"🔗 Sources ({len(r.sources)})"):
            for i, s in enumerate(r.sources, 1):
                st.markdown(f"{i}. [{s.get('title', 'source')}]({s.get('url', '')})")

    st.markdown("---")
    try:
        pdf = export.to_pdf(r)
        st.download_button("⬇️ Download PDF Report", pdf,
                           file_name=f"{r.company}_report.pdf",
                           mime="application/pdf", width="stretch")
    except Exception as e:
        st.caption(f"PDF export unavailable: {e}")


# ── single report tab ─────────────────────────────────────────────────────

def single_tab(provider: str | None, force: bool) -> None:
    st.markdown("<p style='color:#64748b'>Generate a structured report with "
                "company overview, challenges, AI opportunities, and a CEO pitch.</p>",
                unsafe_allow_html=True)

    selected = _demo_chips("single")

    col1, col2 = st.columns([3, 1])
    with col1:
        company = st.text_input(
            "Company name",
            placeholder="e.g. Sobha, Adani Realty, Brigade Group",
            label_visibility="collapsed",
        )
    with col2:
        run = st.button("🚀 Generate", type="primary", disabled=not (company or selected),
                        width="stretch")

    ref_urls = st.text_area(
        "Reference URLs (one per line, optional)",
        placeholder="https://example.com/company-page\nhttps://example.com/news",
        label_visibility="collapsed",
        height=60, key="urls_single",
    )
    urls = [u.strip() for u in ref_urls.split("\n") if u.strip()] if ref_urls else None

    actual = selected or company
    if run and actual:
        status = st.status("", expanded=False)
        try:
            def _on_single_progress(stage: str, _: str):
                if stage == "researching":
                    status.update(label=f"🔍 Researching {actual}…", state="running")
                elif stage == "generating":
                    status.update(label=f"🤖 Generating report…", state="running")
                elif stage == "cache_hit":
                    status.update(label=f"✅ Using cached report for {actual}", state="complete")
            r = report.build(actual, provider=provider, force=force, urls=urls,
                             progress_callback=_on_single_progress)
        except Exception as e:
            status.update(label="❌ Failed", state="error")
            st.error(f"Failed: {e}")
            return
        status.update(label=f"✅ Report ready for {actual}", state="complete")
        status.expanded = False
        render_report(r)
    elif not actual:
        st.markdown("<br><p style='color:#94a3b8;text-align:center'>"
                    "Pick a company above or type one in to begin.</p>",
                    unsafe_allow_html=True)
        st.markdown(
            "<p style='color:#94a3b8;text-align:center;font-size:0.85rem'>"
            "Examples: " + ", ".join(_SAMPLE_COMPANIES) + "</p>",
            unsafe_allow_html=True,
        )


# ── compare tab ───────────────────────────────────────────────────────────

def compare_tab(provider: str | None, force: bool) -> None:
    st.markdown("<p style='color:#64748b'>Compare 2+ companies side by side "
                "across scale, challenges, AI readiness, and more.</p>",
                unsafe_allow_html=True)

    raw = st.text_input("Company names (comma-separated)",
                        placeholder="Sobha, Prestige Group, Brigade Group",
                        label_visibility="collapsed")
    companies = [c.strip() for c in raw.split(",") if c.strip()]
    valid = len(companies) >= 2

    ref_urls = st.text_area(
        "Reference URLs (one per line, optional)",
        placeholder="https://example.com/company-page",
        label_visibility="collapsed", height=60, key="urls_compare",
    )
    urls = [u.strip() for u in ref_urls.split("\n") if u.strip()] if ref_urls else None

    if st.button("⚖️ Compare", type="primary", disabled=not valid,
                 width="stretch"):
        status = st.status("", expanded=False)
        try:
            n = len(companies)

            def _on_cmp_progress(stage: str, company_name: str):
                if stage == "researching":
                    status.update(label=f"🔍 [{company_name}] Researching…", state="running")
                elif stage == "generating":
                    status.update(label=f"🤖 [{company_name}] Generating report…", state="running")
                elif stage == "cache_hit":
                    status.update(label=f"✅ [{company_name}] Using cached report", state="running")
                elif stage == "comparing":
                    status.update(label=f"⚖️ Building comparison matrix ({n} companies)…", state="running")

            res = compare_mod.compare(companies, provider=provider, force=force,
                                      urls=urls, progress_callback=_on_cmp_progress)
        except Exception as e:
            status.update(label="❌ Failed", state="error")
            st.error(f"Failed: {e}")
            return
        status.update(label="✅ Comparison ready", state="complete")
        status.expanded = False

        if res.matrix:
            _header("Comparison Matrix", "📊")
            st.dataframe(res.matrix, width="stretch")

        _header("Individual Reports", "📄")
        cols = st.columns(min(len(res.reports), 3))
        for col, rep in zip(cols, res.reports):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{rep.company}**")
                    st.caption("Overview")
                    st.write(rep.overview[:150] + "…" if len(rep.overview) > 150 else rep.overview)
                    st.caption("Top challenge")
                    st.write(rep.challenges[0].title if rep.challenges else "—")
                    st.caption("First AI win")
                    st.write(rep.ai_opportunities[0].title if rep.ai_opportunities else "—")
                    try:
                        pdf = export.to_pdf(rep)
                        st.download_button("⬇️ .pdf", pdf,
                                           file_name=f"{rep.company}_report.pdf",
                                           key=f"dl_{rep.company}",
                                           width="stretch")
                    except Exception:
                        st.caption("PDF unavailable")


# ── landscape tab ─────────────────────────────────────────────────────────

def _render_landscape(l: landscape.CompetitiveLandscape) -> None:
    _header("Market Overview", "🏟️")
    st.write(l.market_overview)

    if l.positioning:
        _header("Competitive Positioning", "📊")
        st.dataframe(l.positioning, width="stretch")

    _header("Strengths & Weaknesses", "⚖️")
    for sw in l.strengths_weaknesses:
        with st.container(border=True):
            st.markdown(f"**{sw.get('company', '')}**")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("✅ **Strengths**")
                for s in sw.get("strengths", []):
                    st.write(f"- {s}")
            with c2:
                st.markdown("⚠️ **Weaknesses**")
                for w in sw.get("weaknesses", []):
                    st.write(f"- {w}")
            st.caption(f"AI Readiness: {sw.get('ai_readiness', 'N/A')}")

    _header("Strategic Gaps", "🔍")
    for g in l.strategic_gaps:
        with st.container(border=True):
            st.markdown(f"**{g.get('gap', '')}**")
            st.write(g.get("description", ""))
            c1, c2 = st.columns(2)
            c1.caption(f"💡 Opportunity: {g.get('opportunity_size', 'N/A')}")
            c2.caption(f"🎯 Best positioned: {g.get('best_positioned', 'None')}")

    _header("Strategic Recommendations", "🎯")
    for company, rec in l.recommendations.items():
        with st.container(border=True):
            st.markdown(f"**{company}**")
            st.info(rec)

    if l.reports:
        st.markdown("---")
        _header("Individual Company Reports", "📄")
        cols = st.columns(min(len(l.reports), 3))
        for col, rep in zip(cols, l.reports):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{rep.company}**")
                    top_ch = rep.challenges[0].title if rep.challenges else "—"
                    first_ai = rep.ai_opportunities[0].title if rep.ai_opportunities else "—"
                    st.caption("Overview")
                    st.write(rep.overview[:120] + "…" if len(rep.overview) > 120 else rep.overview)
                    st.caption(f"Top challenge: {top_ch}")
                    st.caption(f"First AI win: {first_ai}")
                    try:
                        pdf = export.to_pdf(rep)
                        st.download_button("⬇️ PDF Report", pdf,
                                           file_name=f"{rep.company}_report.pdf",
                                           key=f"lndl_{rep.company}",
                                           width="stretch")
                    except Exception:
                        st.caption("PDF unavailable")

    st.markdown("---")
    _header("Company Comparison", "📊")
    cols = st.columns([1, 2, 2, 2])
    headers = ["Company", "Scale", "Top Challenge", "AI Readiness"]
    for col, h in zip(cols, headers):
        col.markdown(f"**{h}**")
    for p in l.positioning:
        cols = st.columns([1, 2, 2, 2])
        cols[0].write(p.get("company", ""))
        cols[1].write(p.get("scale", ""))
        # match company to its strengths_weaknesses for ai_readiness
        sw = next((s for s in l.strengths_weaknesses
                   if s.get("company") == p.get("company")), {})
        cols[2].write(p.get("key_weakness", ""))
        cols[3].write(sw.get("ai_readiness", "—"))
    st.caption("Quick comparison across key dimensions.")

    st.markdown("---")
    try:
        pdf = export.landscape_to_pdf(l)
        st.download_button("⬇️ Download Full Landscape PDF", pdf,
                           file_name="competitive_landscape.pdf",
                           mime="application/pdf", width="stretch")
    except Exception as e:
        st.caption(f"PDF export unavailable: {e}")


def landscape_tab(provider: str | None, force: bool) -> None:
    st.markdown("<p style='color:#64748b'>Analyze 3–5 competitors to uncover "
                "market positioning, gaps, and strategic opportunities.</p>",
                unsafe_allow_html=True)

    selected = _demo_chips("landscape")

    raw = st.text_input("Company names (comma-separated, 3–5)",
                        placeholder="Sobha, Prestige Group, Brigade Group, Godrej Properties",
                        label_visibility="collapsed")
    companies = [c.strip() for c in raw.split(",") if c.strip()]
    valid = 3 <= len(companies) <= 5

    ref_urls = st.text_area(
        "Reference URLs (one per line, optional)",
        placeholder="https://example.com/company-page",
        label_visibility="collapsed", height=60, key="urls_landscape",
    )
    urls = [u.strip() for u in ref_urls.split("\n") if u.strip()] if ref_urls else None

    if st.button("🏟️ Generate Landscape", type="primary", disabled=not valid,
                 width="stretch"):
        status = st.status("", expanded=False)
        try:
            n = len(companies)

            def _on_landscape_progress(stage: str, company_name: str):
                if stage == "researching":
                    status.update(label=f"🔍 [{company_name}] Researching…", state="running")
                elif stage == "generating":
                    status.update(label=f"🤖 [{company_name}] Generating report…", state="running")
                elif stage == "cache_hit":
                    status.update(label=f"✅ [{company_name}] Using cached report", state="running")
                elif stage == "analyzing":
                    status.update(label=f"🏟️ Building landscape analysis ({n} companies)…", state="running")

            l = landscape.build(companies, provider=provider, force=force,
                                urls=urls, progress_callback=_on_landscape_progress)
        except Exception as e:
            status.update(label="❌ Failed", state="error")
            st.error(f"Failed: {e}")
            return
        status.update(label="✅ Landscape ready", state="complete")
        status.expanded = False
        _render_landscape(l)


# ── main ──────────────────────────────────────────────────────────────────

def _silence_proactor_errors(loop, context):
    """Suppress noisy Windows asyncio proactor errors from thread-closed sockets."""
    exc = context.get("exception")
    handle = str(context.get("handle", ""))
    if isinstance(exc, ConnectionResetError) and "_ProactorBasePipeTransport" in handle:
        return
    loop.default_exception_handler(context)


def main() -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_silence_proactor_errors)
    except RuntimeError:
        pass

    _inject_css()

    provider, force = _render_sidebar()
    _render_hero(provider)

    if provider is None and not config.status().llms:
        st.stop()

    t_single, t_compare, t_landscape = st.tabs(
        ["📄 Single Report", "⚖️ Compare Companies", "🏟️ Competitive Landscape"]
    )
    with t_single:
        single_tab(provider, force)
    with t_compare:
        compare_tab(provider, force)
    with t_landscape:
        landscape_tab(provider, force)

    st.markdown(
        f"<footer>AI Research &amp; Recommendation Agent <strong>v{agent_version}</strong>"
        " · 9-agent architecture · 6 LLM providers · 3 search providers · 23 unit tests"
        "</footer>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
