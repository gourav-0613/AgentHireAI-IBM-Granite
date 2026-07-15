"""
app.py

AgentHire AI — Streamlit application entry point.

Responsibilities:
    - Configure the Streamlit app (page title, icon, layout, sidebar)
    - Initialise session state on every run via core.session_state.initialise()
    - Sidebar: branded SVG icon nav rows + IBM Granite attribution
    - Default landing content for the root page

Run locally:
    streamlit run app.py
"""

import logging

import streamlit as st

from components.theme import (
    brand_header,
    brand_mark,
    branded_icon,
    favicon_path,
    icon,
    load_css,
    stage_pill,
)
from core.session_state import initialise

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global page configuration  (must be first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AgentHire AI",
    page_icon=favicon_path(),
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": "https://github.com/your-org/agenthire-ai",
        "Report a bug": "https://github.com/your-org/agenthire-ai/issues",
        "About": "# AgentHire AI\nPowered by IBM Granite on Watsonx.ai",
    },
)

# ---------------------------------------------------------------------------
# Session state initialisation  (idempotent — safe on every re-run)
# ---------------------------------------------------------------------------

initialise()

# ---------------------------------------------------------------------------
# Global design system
# ---------------------------------------------------------------------------

load_css()

# ---------------------------------------------------------------------------
# Sidebar branding
# ---------------------------------------------------------------------------

with st.sidebar:
    # ── App identity — Fix #1: brand mark 35% larger (76px in sidebar) ────
    st.markdown(
        f"""
        <div style="text-align:center; padding: 10px 0 18px 0;">
            <div style="display:flex; justify-content:center; margin-bottom:12px;">
                {brand_mark(76)}
            </div>
            <span style="font-size:1.54rem; font-weight:800; color:#F8FAFC; letter-spacing:-0.01em; font-family:'IBM Plex Sans',sans-serif;">
                AgentHire<span style="color:#00D4FF;">AI</span>
            </span><br>
            <span style="font-size:0.76rem; color:#94A3B8; letter-spacing:0.05em;">
                AI RESUME TAILORING &amp; ATS OPTIMIZATION
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.divider()

    # ── Navigation — Fix #2: branded SVG icons ────────────────────────────
    st.markdown(
        f'<div style="font-size:0.78rem;font-weight:700;color:#94A3B8;'
        f'letter-spacing:0.08em;text-transform:uppercase;margin-bottom:6px;">'
        f'{icon("layers", 14, "#94A3B8")} Navigation</div>',
        unsafe_allow_html=True,
    )

    # nav helper — branded SVG icon rendered inline before the page link
    def _nav_row(icon_name: str, label: str) -> None:
        """Render a branded-SVG nav icon above an st.page_link label."""
        st.markdown(
            f'<div style="display:inline-flex;align-items:center;gap:8px;'
            f'margin-bottom:-4px;padding-left:6px;">'
            f'<span style="opacity:0.85;">{branded_icon(icon_name, 18)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Render each nav item as icon + page link pair
    _nav_row("home", "Home")
    st.page_link("app.py", label="Home")

    _nav_row("landing", "Landing Page")
    st.page_link("pages/1_Home.py", label="Landing Page")

    _nav_row("analyzer", "Resume Analyzer")
    st.page_link("pages/2_Analyzer.py", label="Resume Analyzer")

    st.divider()

    # ── Pipeline stage status ─────────────────────────────────────────────
    st.markdown(
        f'<div style="font-size:0.78rem;font-weight:700;color:#94A3B8;'
        f'letter-spacing:0.08em;text-transform:uppercase;margin-bottom:8px;">'
        f'{icon("cpu", 14, "#94A3B8")} Pipeline Status</div>',
        unsafe_allow_html=True,
    )
    stage = st.session_state.get("pipeline_stage", "IDLE")
    stage_pill(stage)

    st.divider()

    # ── IBM Watsonx attribution ───────────────────────────────────────────
    st.markdown(
        """
        <div style="text-align:center; padding:4px 2px;">
            <div style="
                background:linear-gradient(135deg,rgba(91,95,255,0.16),rgba(0,212,255,0.10));
                border-radius:14px;
                padding:14px 10px 12px 10px;
                border:1px solid rgba(0,212,255,0.25);
            ">
                <p style="font-size:0.68rem;color:#00D4FF;margin:0 0 6px 0;
                          letter-spacing:0.08em;text-transform:uppercase;font-weight:700;">
                    Powered by
                </p>
                <p style="font-size:1.0rem;color:#F8FAFC;font-weight:800;margin:0 0 2px 0;">
                    IBM Watsonx.ai
                </p>
                <p style="font-size:0.76rem;color:#94A3B8;margin:0 0 8px 0;">
                    Granite Foundation Models
                </p>
                <hr style="border-color:rgba(148,163,184,0.15);margin:8px 0;">
                <p style="font-size:0.68rem;color:#64748B;margin:0;">
                    ibm/granite-3-8b-instruct<br>
                    ibm/granite-20b-multilingual
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='text-align:center;margin-top:14px;"
        "font-size:0.66rem;color:#475569;'>v1.0.0 · AgentHire AI</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Default landing content (shown on root page)
# ---------------------------------------------------------------------------

brand_header("Home")

st.markdown(
    f"""
    <div class="ah-hero-wrap ah-animate" style="margin-top:8px;">
        <div class="ah-eyebrow">{branded_icon("analyzer", 14)} Enterprise AI Suite</div>
        <div class="ah-hero-title">Welcome to AgentHire AI</div>
        <div class="ah-hero-sub">
            Use the sidebar to get started — visit the <strong>Landing Page</strong>
            to explore the platform, or jump straight into the
            <strong>Resume Analyzer</strong> to run the full AI pipeline.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("")
col1, col2 = st.columns(2)
with col1:
    st.markdown(
        f'<div class="ah-card ah-animate">'
        f'<div class="ah-card-icon">{branded_icon("landing", 26)}</div>'
        f'<div class="ah-card-title" style="margin-top:10px;">Landing Page</div>'
        f'<div class="ah-card-desc">Learn how the 5-agent pipeline works and what '
        f'AgentHire AI can do for your job search.</div></div>',
        unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        f'<div class="ah-card ah-animate">'
        f'<div class="ah-card-icon">{branded_icon("analyzer", 26)}</div>'
        f'<div class="ah-card-title" style="margin-top:10px;">Resume Analyzer</div>'
        f'<div class="ah-card-desc">Upload your resume, paste a job description, and '
        f'get a full ATS analysis in under 60 seconds.</div></div>',
        unsafe_allow_html=True,
    )

logger.info("app.py | session initialised | stage=%s", stage)
