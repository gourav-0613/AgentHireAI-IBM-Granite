"""
pages/2_Analyzer.py

Streamlit Page 2 — Resume Analyzer

The full end-to-end pipeline runs on this single page.

Fix #5: Upload area is now a single integrated glass card (.ah-upload-panel)
         containing the branded upload-resume.svg icon, title, file uploader,
         and supported-formats line — all as one cohesive block.

All section_title() calls now use branded SVG icon names.
All pipeline logic (agents, validators, session state) is unchanged.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Optional

import streamlit as st

from components.keyword_badges import render as render_keywords
from components.resume_preview import render as render_resume
from components.resume_preview import render_tailored
from components.score_gauge import render as render_score
from components.skill_gap_chart import render as render_skill_gap
from components.theme import (
    badge,
    brand_header,
    branded_icon,
    empty_state,
    favicon_path,
    icon,
    load_css,
    section_title,
    stage_indicator,
)
from core.pipeline import run_analysis, run_resume_parsing, run_tailoring
from core.session_state import (
    STAGE_COMPLETE,
    STAGE_IDLE,
    STAGE_PARSED,
    initialise,
    reset_downstream,
)
from utils.validators import validate_jd_text, validate_pdf_upload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config + session initialisation
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AgentHire AI — Analyzer",
    page_icon=favicon_path(),
    layout="wide",
    initial_sidebar_state="expanded",
)

initialise()

# ---------------------------------------------------------------------------
# Global design system
# ---------------------------------------------------------------------------

load_css()
brand_header("Resume Analyzer")

_FIT_COLORS = {
    "Strong Match": "#00E676",
    "Good Match": "#8BC34A",
    "Partial Match": "#FFC107",
    "Low Match": "#FF5C8A",
}

# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.markdown(
    f"""
    <div class="ah-hero-wrap ah-animate" style="padding:34px 36px;">
        <div class="ah-eyebrow">{branded_icon("pipeline", 14)} 5-Agent Pipeline</div>
        <div class="ah-hero-title" style="font-size:2.2rem;">Resume Analyzer</div>
        <div class="ah-hero-sub" style="font-size:1rem;">
            Upload your resume, paste the job description, and let AgentHire AI
            analyse your fit, optimise for ATS systems, and generate a tailored resume.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Persistent overall stage indicator
# ---------------------------------------------------------------------------

_stage_now = st.session_state.get("pipeline_stage", STAGE_IDLE)
_completed_by_stage = {
    STAGE_IDLE: -1,
    STAGE_PARSED: 0,
    "ANALYZED": 3,
    STAGE_COMPLETE: 5,
}
stage_indicator(completed_index=_completed_by_stage.get(_stage_now, -1))

st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helper: file hash (to detect new uploads)
# ---------------------------------------------------------------------------


def _file_hash(uploaded_file) -> str:
    """Return SHA-256 hex digest of uploaded file bytes for change detection."""
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Step 1 — Upload Resume
# Fix #5: Single integrated glass card containing icon + uploader + formats
# ---------------------------------------------------------------------------

section_title(
    "Step 1 — Upload Resume PDF",
    "upload-resume",
    "PDF only · Max 5 MB · Parsed by IBM Granite (Agent 1)",
)

# Render the branded upload icon + title inside a glass panel
st.markdown(
    f"""
    <div class="ah-upload-panel ah-animate">
        <div class="ah-upload-panel-icon">
            {branded_icon("upload-resume", 32)}
        </div>
        <div class="ah-upload-panel-title">Drop your resume here</div>
        <div class="ah-upload-panel-sub">Supported format: PDF · Maximum size: 5 MB</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# The native file uploader sits seamlessly below the panel (CSS removes its border
# so it flows visually as part of the same card)
uploaded_file = st.file_uploader(
    "Choose your resume PDF",
    type=["pdf"],
    help="Maximum file size: 5 MB. Only PDF format is supported.",
    label_visibility="collapsed",
)

if uploaded_file is not None:
    # Validate upload
    try:
        validate_pdf_upload(uploaded_file)
    except ValueError as exc:
        st.error(f"{exc}")
        uploaded_file = None

if uploaded_file is not None:
    # Detect new file upload via hash comparison
    current_hash = _file_hash(uploaded_file)
    stored_hash = st.session_state.get("_resume_file_hash")

    if current_hash != stored_hash:
        # New resume uploaded — reset everything downstream of IDLE
        reset_downstream(STAGE_IDLE)
        st.session_state["_resume_file_hash"] = current_hash
        st.session_state["_jd_text_raw"] = ""

        st.info("⏳ Parsing your resume with IBM Granite…")

        with st.status("🤖 Running Agent 1: Resume Parser…", expanded=True) as status:
            stage_indicator(active_index=0)
            st.write("📄 Extracting text from PDF…")
            uploaded_file.seek(0)
            pdf_bytes: bytes = uploaded_file.read()

            result = run_resume_parsing(
                pdf_bytes=pdf_bytes,
                jd_text="__placeholder__",
            )

            if result.success:
                stage_indicator(completed_index=0)
                status.update(
                    label="✅ Resume parsed successfully!",
                    state="complete",
                    expanded=False,
                )
                st.success(
                    f"✅ Resume parsed in {result.elapsed_seconds:.1f}s — "
                    f"**{result.outputs['resume_profile'].personal_info.full_name}** detected."
                )
                logger.info(
                    "2_Analyzer | resume parsed | elapsed=%.1fs",
                    result.elapsed_seconds,
                )
            else:
                status.update(label="❌ Parsing failed", state="error")
                st.error(f"❌ Resume parsing failed: {result.error}")
                logger.error("2_Analyzer | resume parsing failed | %s", result.error)

    else:
        # Same file; show brief confirmation
        profile = st.session_state.get("resume_profile")
        if profile:
            st.success(
                f"✅ **{profile.personal_info.full_name}** — resume already parsed."
            )

else:
    empty_state(
        "No resume uploaded yet",
        "Drag and drop your resume PDF above, or click Browse files "
        "to select one from your computer.",
        "upload",
        compact=True,
    )

st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Step 2 — Resume Preview  (gated on STAGE_PARSED)
# ---------------------------------------------------------------------------

stage: str = st.session_state.get("pipeline_stage", STAGE_IDLE)

if stage in (STAGE_PARSED, "ANALYZED", STAGE_COMPLETE):
    profile = st.session_state.get("resume_profile")
    if profile:
        section_title(
            "Step 2 — Resume Preview",
            "upload-resume",
            "Confirm the AI extracted your details correctly before continuing",
        )

        with st.container(border=True):
            st.markdown(
                "👇 Review your parsed resume below. "
                "If anything looks off, re-upload a cleaner PDF."
            )
            raw_text: Optional[str] = st.session_state.get("resume_raw_text")
            render_resume(profile, is_tailored=False, raw_text=raw_text)

        st.success(
            "✅ Resume verified. Proceed to **Step 3** to paste the job description."
        )
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Step 3 — Paste Job Description  (gated on STAGE_PARSED)
# ---------------------------------------------------------------------------

stage = st.session_state.get("pipeline_stage", STAGE_IDLE)

if stage in (STAGE_PARSED, "ANALYZED", STAGE_COMPLETE):
    section_title(
        "Step 3 — Paste Job Description",
        "job-description",
        "Paste the full target job posting — minimum 100 characters",
    )

    with st.container(border=True):
        existing_jd: str = st.session_state.get("_jd_text_raw", "")

        jd_text: str = st.text_area(
            "Paste the full job description",
            value=existing_jd,
            height=250,
            max_chars=10_000,
            placeholder=(
                "Paste the complete job posting here…\n\n"
                "Include: role title, responsibilities, required skills, "
                "preferred skills, and experience requirements."
            ),
            label_visibility="collapsed",
            key="jd_textarea",
        )

        # Character counter
        char_count = len(jd_text.strip())
        MIN_CHARS = 100
        counter_color = "#00E676" if char_count >= MIN_CHARS else "#FF5C8A"
        st.markdown(
            f"<div style='text-align:right;font-size:0.75rem;color:{counter_color};'>"
            f"{char_count:,} / 10,000 characters "
            f"{'✓' if char_count >= MIN_CHARS else f'(min {MIN_CHARS})'}"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Detect JD text change — reset downstream analysis if changed
        if jd_text != existing_jd and existing_jd != "":
            reset_downstream(STAGE_PARSED)
            st.info("ℹ️ Job description updated — previous analysis cleared.")

        # Persist raw JD text in session
        st.session_state["_jd_text_raw"] = jd_text

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Step 4 — Run Analysis Button  (gated on JD text present + STAGE_PARSED)
# ---------------------------------------------------------------------------

stage = st.session_state.get("pipeline_stage", STAGE_IDLE)
jd_text_raw: str = st.session_state.get("_jd_text_raw", "")

if stage in (STAGE_PARSED, "ANALYZED", STAGE_COMPLETE) and jd_text_raw.strip():
    section_title(
        "Step 4 — Run Full Analysis",
        "pipeline",
        "Runs Agents 2–5 in sequence: JD Analysis → Skill Gap → ATS → Tailoring",
    )

    with st.container(border=True):
        col_btn, col_info = st.columns([2, 5], gap="medium")
        with col_btn:
            run_clicked = st.button(
                "🚀 Run Analysis",
                type="primary",
                width="stretch",
                disabled=(stage == STAGE_COMPLETE),
                help="Runs all 4 remaining AI agents: JD Analyzer, Skill Gap, ATS Optimizer, Resume Tailor",
            )
        with col_info:
            if stage == STAGE_COMPLETE:
                st.success(
                    "✅ Analysis complete! Scroll down to view results. "
                    "Re-upload a resume or change the JD to run again."
                )
            else:
                st.markdown(
                    "<div style='font-size:0.85rem;color:#94A3B8;margin-bottom:8px;'>"
                    "Clicking <b>Run Analysis</b> will execute:</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    badge("📋 JD Analyzer")
                    + badge("🧠 Skill Gap")
                    + badge("🔑 ATS Optimizer")
                    + badge("✨ Resume Tailor", accent=True)
                    + badge("📄 PDF Generation", accent=True),
                    unsafe_allow_html=True,
                )

    if run_clicked and stage not in (STAGE_COMPLETE, "ANALYZED"):
        # Validate JD before running
        try:
            validate_jd_text(jd_text_raw)
        except ValueError as exc:
            st.error(f"❌ {exc}")
            st.stop()

        st.session_state["_jd_text_pending"] = jd_text_raw

        with st.status(
            "🤖 Running AI Analysis Pipeline…", expanded=True
        ) as pipeline_status:

            stage_indicator(active_index=1, completed_index=0)
            st.write("📋 Agent 2: Analyzing job description…")
            analysis_result = run_analysis(jd_text=jd_text_raw)

            if not analysis_result.success:
                pipeline_status.update(label="❌ Analysis failed", state="error")
                st.error(f"❌ Analysis failed: {analysis_result.error}")
                logger.error("2_Analyzer | run_analysis failed | %s", analysis_result.error)
                st.stop()

            stage_indicator(active_index=4, completed_index=3)
            st.write("🧠 Agent 3: Skill gap analysis complete ✓")
            st.write("🔑 Agent 4: ATS keyword optimisation complete ✓")

            st.write("✨ Agent 5: Tailoring your resume…")
            tailor_result = run_tailoring()

            if not tailor_result.success:
                pipeline_status.update(label="❌ Tailoring failed", state="error")
                st.error(f"❌ Resume tailoring failed: {tailor_result.error}")
                logger.error("2_Analyzer | run_tailoring failed | %s", tailor_result.error)
                st.stop()

            stage_indicator(completed_index=5)
            st.write("📊 Calculating ATS match score…")
            st.write("📄 Generating tailored PDF…")

            total_elapsed = analysis_result.elapsed_seconds + tailor_result.elapsed_seconds
            pipeline_status.update(
                label=f"✅ Analysis complete in {total_elapsed:.1f}s!",
                state="complete",
                expanded=False,
            )

        st.success(
            f"🎉 Analysis complete! "
            f"ATS Match Score: **{tailor_result.outputs.get('total_score', 'N/A')}** — "
            f"**{tailor_result.outputs.get('fit_label', '')}**"
        )
        st.balloons()
        st.rerun()

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Step 5 — Results Tabs  (gated on STAGE_COMPLETE)
# ---------------------------------------------------------------------------

stage = st.session_state.get("pipeline_stage", STAGE_IDLE)

if stage == STAGE_COMPLETE:
    skill_gap_report = st.session_state.get("skill_gap_report")
    ats_report = st.session_state.get("ats_report")
    match_score_raw = st.session_state.get("match_score")
    tailored_resume = st.session_state.get("tailored_resume")
    pdf_bytes_data: Optional[bytes] = st.session_state.get("pdf_bytes")
    resume_profile = st.session_state.get("resume_profile")
    job_description = st.session_state.get("job_description")

    section_title(
        "Step 5 — Analysis Results",
        "analytics",
        "Skill gap, ATS keywords, match score, and your tailored PDF",
    )

    # Quick summary metrics row
    if job_description and resume_profile:
        score_val = match_score_raw if match_score_raw is not None else 0.0
        if score_val >= 75:
            fit = "Strong Match"
        elif score_val >= 55:
            fit = "Good Match"
        elif score_val >= 35:
            fit = "Partial Match"
        else:
            fit = "Low Match"
        fit_color = _FIT_COLORS.get(fit, "#94A3B8")

        summary_cols = st.columns(4)
        with summary_cols[0]:
            st.metric("🎯 Role", job_description.role_title or "—")
        with summary_cols[1]:
            st.metric("👤 Candidate", resume_profile.personal_info.full_name)
        with summary_cols[2]:
            st.metric("📊 ATS Score", f"{score_val:.1f}")
        with summary_cols[3]:
            st.markdown(
                f'<div style="padding-top:6px;">'
                f'<div style="font-size:0.82rem;color:#94A3B8;font-weight:600;margin-bottom:6px;">Fit</div>'
                f'<div class="ah-fit-pill" style="background:{fit_color}22;color:{fit_color};'
                f'border:2px solid {fit_color};">{fit}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    tab_gap, tab_ats, tab_score, tab_resume = st.tabs(
        ["🧠 Skill Gap", "🔑 ATS Keywords", "📊 Match Score", "✨ Tailored Resume"]
    )

    # ── Tab 1: Skill Gap ──────────────────────────────────────────────────
    with tab_gap:
        if skill_gap_report:
            render_skill_gap(skill_gap_report)
        else:
            st.warning("Skill gap report not available.")

    # ── Tab 2: ATS Keywords ───────────────────────────────────────────────
    with tab_ats:
        if ats_report:
            render_keywords(ats_report)
        else:
            st.warning("ATS report not available.")

    # ── Tab 3: Match Score ────────────────────────────────────────────────
    with tab_score:
        if match_score_raw is not None and skill_gap_report and ats_report and resume_profile and job_description:
            from core.scorer import calculate_score  # noqa: PLC0415

            score_result = calculate_score(
                skill_gap=skill_gap_report,
                ats_report=ats_report,
                profile=resume_profile,
                jd=job_description,
            )
            render_score(score_result)
        elif match_score_raw is not None:
            st.metric("ATS Match Score", f"{match_score_raw:.1f} / 100")
            st.info("Detailed breakdown requires complete analysis data.")
        else:
            st.warning("Match score not available.")

    # ── Tab 4: Tailored Resume ────────────────────────────────────────────
    with tab_resume:
        if tailored_resume and resume_profile:
            render_tailored(tailored_resume, resume_profile)

            st.divider()

            # PDF download
            if pdf_bytes_data:
                candidate_name = (
                    resume_profile.personal_info.full_name.replace(" ", "_")
                    if resume_profile
                    else "candidate"
                )
                role_slug = (
                    (job_description.role_title or "role").replace(" ", "_")
                    if job_description
                    else "role"
                )
                filename = f"tailored_resume_{candidate_name}_{role_slug}.pdf"

                dl_col, _ = st.columns([2, 5])
                with dl_col:
                    st.download_button(
                        label=f"📥 Download Tailored Resume (PDF)",
                        data=pdf_bytes_data,
                        file_name=filename,
                        mime="application/pdf",
                        type="primary",
                        width="stretch",
                        help="Download your AI-optimised resume as a PDF ready for submission.",
                    )
                st.caption(
                    "Your tailored resume has been formatted as an ATS-friendly PDF. "
                    "Review it before submitting."
                )
            else:
                st.warning("PDF generation was not completed. Please re-run the analysis.")
        else:
            st.warning("Tailored resume not available.")

# ---------------------------------------------------------------------------
# Footer hint when analysis is not yet complete
# ---------------------------------------------------------------------------

if stage == STAGE_IDLE:
    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
    empty_state(
        "No analysis yet",
        "Start by uploading your resume PDF in Step 1 above, then paste a "
        "job description and run the full AI pipeline to see your skill gap, "
        "ATS keyword match, and tailored resume here.",
        "search",
    )
