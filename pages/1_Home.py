"""
pages/1_Home.py

Streamlit Page 1 — Home / Landing

UI sections (in order):
    1. Hero            — app name, tagline, IBM Granite badge, brand illustration
    2. Workflow        — horizontal step diagram with branded SVG icons
    3. Feature Cards   — one card per agent, all same width (5-column grid)
    4. IBM Block       — Watsonx.ai / Granite / Deterministic Scorer cards
    5. CTA             — "Start Analysis →" with proper vertical spacing

Fix #3: All 5 agent cards use equal-width 5-column grid (no centering hack).
Fix #4: 28px spacing added between CTA text block and button.
"""

import streamlit as st

from components.theme import (
    brand_header,
    brand_logo_svg,
    branded_icon,
    favicon_path,
    glass_card,
    hero_illustration,
    icon,
    load_css,
    section_title,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AgentHire AI — Home",
    page_icon=favicon_path(),
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Design system
# ---------------------------------------------------------------------------

load_css()
brand_header("Landing Page")

# ---------------------------------------------------------------------------
# 1. Hero section
# ---------------------------------------------------------------------------

hero_col, art_col = st.columns([3, 2], gap="large")

with hero_col:
    st.markdown(
        f"""
        <div class="ah-hero-wrap ah-animate">
            <div class="ah-eyebrow">{branded_icon("analyzer", 14)} IBM Watsonx.ai · Granite LLMs</div>
            <div class="ah-hero-title">Land your next role,<br>faster.</div>
            <div class="ah-hero-sub">
                AI-powered resume analysis, ATS optimisation, and tailored
                rewriting — five specialised agents working together to get
                your resume past the filters and in front of a human.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with art_col:
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    hero_illustration()

st.markdown(
    f'<div style="margin:18px 0 6px 0;">'
    f'{icon("shield", 13, "#00D4FF")} <span style="color:#94A3B8;font-size:0.82rem;">'
    f'No data is stored or shared &nbsp;·&nbsp; PDF in, tailored PDF out &nbsp;·&nbsp; '
    f'Deterministic, testable ATS scoring</span></div>',
    unsafe_allow_html=True,
)

cta_col, _ = st.columns([2, 5])
with cta_col:
    if st.button(
        "Start Analysis  →",
        type="primary",
        width="stretch",
        help="Opens the Resume Analyzer page",
    ):
        st.switch_page("pages/2_Analyzer.py")

st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 2. Workflow diagram — branded SVG icons
# ---------------------------------------------------------------------------

section_title("How It Works", "pipeline", "Five sequential stages, one continuous pipeline")

# Icon mapping: (step_num, branded_icon_name, label, desc)
steps = [
    ("01", "upload-resume",    "Upload Resume",         "PDF resume parsed by Granite LLM"),
    ("02", "job-description",  "Paste Job Description", "JD decomposed into structured skills"),
    ("03", "skill-gap",        "Skill Gap Analysis",    "AI compares your skills to the role"),
    ("04", "ats",              "ATS Optimisation",      "Keywords detected and scored"),
    ("05", "resume-tailoring", "Tailored Resume",       "Rewritten resume + PDF download"),
]

cols = st.columns(len(steps))
for col, (num, ic_name, label, desc) in zip(cols, steps):
    with col:
        st.markdown(
            f'<div class="ah-step ah-animate">'
            f'<div class="ah-step-num">{num}</div>'
            f'<div style="margin-bottom:6px;display:flex;justify-content:center;">'
            f'{branded_icon(ic_name, 22)}</div>'
            f'<div class="ah-step-label">{label}</div>'
            f'<div class="ah-step-desc">{desc}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 3. Feature cards — Fix #3: all 5 cards in a uniform 5-column grid
# ---------------------------------------------------------------------------

section_title("Specialised AI Agents", "ai-agent", "Five purpose-built agents, each responsible for one part of the pipeline")

# All 5 feature card definitions (icon_name passed to glass_card for branded mapping)
features = [
    (
        "file-text",   # maps to upload-resume via glass_card's _LUCIDE_TO_BRANDED
        "Resume Parser",
        "Agent 1 — IBM Granite extracts structured data from any PDF: "
        "personal info, experience, skills, education, certifications, and projects.",
    ),
    (
        "clipboard",   # maps to job-description
        "JD Analyzer",
        "Agent 2 — Decomposes job postings into required skills, preferred skills, "
        "experience requirements, responsibilities, and seniority signals.",
    ),
    (
        "brain",       # maps to skill-gap
        "Skill Gap Analyzer",
        "Agent 3 — Compares your resume against the JD to surface matched skills, "
        "critical gaps, transferable skills, and actionable recommendations.",
    ),
    (
        "key",         # maps to ats
        "ATS Keyword Optimizer",
        "Agent 4 — Identifies priority ATS keywords with relevance weights, "
        "detects which phrases are present or missing, and scores your resume.",
    ),
    (
        "sparkles",    # maps to resume-tailoring
        "Resume Tailor",
        "Agent 5 — Rewrites your summary and experience bullets using job-specific "
        "language, produces a highlighted skill set, and generates a ready-to-send PDF.",
    ),
]

# Fix #3: all 5 in equal-width columns — no centering hack
all_cols = st.columns(5)
for col, (ic, title, desc) in zip(all_cols, features):
    with col:
        st.markdown(glass_card(ic, title, desc), unsafe_allow_html=True)

st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 4. IBM integration block — branded icons
# ---------------------------------------------------------------------------

section_title("Powered by IBM Technology", "settings")

ibm_cols = st.columns(3)
ibm_items = [
    (
        "analytics",
        "IBM Watsonx.ai",
        "Enterprise AI platform",
        "Production-grade LLM inference via the IBM Cloud managed service. "
        "Guaranteed uptime, compliance, and scalability.",
    ),
    (
        "ai-agent",
        "IBM Granite LLMs",
        "granite-4-h-small",
        "IBM's enterprise-grade open-source foundation models. "
        "Optimised for structured extraction and generation tasks.",
    ),
    (
        "score",
        "Deterministic Scorer",
        "No hallucination risk",
        "The final ATS match score is computed with 100% deterministic Python logic "
        "— no LLM involved in scoring. Fully testable and reproducible.",
    ),
]

for col, (ic_name, title, subtitle, desc) in zip(ibm_cols, ibm_items):
    with col:
        st.markdown(
            f'<div class="ah-card ah-animate" style="text-align:center;">'
            f'<div style="display:flex;justify-content:center;margin-bottom:10px;">'
            f'<div class="ah-card-icon" style="margin-bottom:0;">{branded_icon(ic_name, 24)}</div></div>'
            f'<div class="ah-card-title">{title}</div>'
            f'<div style="font-size:0.76rem;color:#00D4FF;margin-bottom:8px;font-weight:700;">{subtitle}</div>'
            f'<div class="ah-card-desc">{desc}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )

st.markdown("<div style='height:36px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# 5. CTA — Fix #4: proper spacing between text block and button
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="ah-card ah-animate" style="text-align:center;padding:40px 24px;">
        <div class="ah-card-title" style="font-size:1.4rem;margin-bottom:8px;">
            {branded_icon("analyzer", 22)} Ready to optimise your resume?
        </div>
        <div class="ah-card-desc" style="max-width:520px;margin:0 auto 0 auto;font-size:0.9rem;">
            Upload your PDF resume, paste the job description, and let the AI
            agents do the rest — in under 60 seconds.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Fix #4: 28px vertical gap between card text and button
st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)

cta_col2, _ = st.columns([2, 5])
with cta_col2:
    if st.button(
        "Start Analysis  →",
        type="primary",
        width="stretch",
        key="cta_bottom",
        help="Opens the Resume Analyzer page",
    ):
        st.switch_page("pages/2_Analyzer.py")

st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
st.markdown(
    f"<div style='text-align:center;'><div style='display:inline-block;width:220px;'>"
    f"{brand_logo_svg()}</div></div>",
    unsafe_allow_html=True,
)
st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
st.caption(
    "AgentHire AI · v1.0 · Built with IBM Watsonx.ai and IBM Granite · "
    "No data is stored or shared."
)
