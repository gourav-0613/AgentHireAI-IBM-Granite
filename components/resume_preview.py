"""
components/resume_preview.py

Renders a structured resume card in the Streamlit UI.

Used in two contexts:
    1. Post-parse verification (Step 2 of Analyzer):
         Displays parsed ResumeProfile so the user can verify accuracy
         before committing to the analysis pipeline.

    2. Tailored resume display (Step 5, Tab 4 of Analyzer):
         Displays the rewritten TailoredResume content with visual
         differentiation from the original.

Public API:
    render(profile: ResumeProfile, is_tailored: bool = False) -> None
    render_tailored(tailored: TailoredResume, profile: ResumeProfile) -> None
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import streamlit as st

if TYPE_CHECKING:
    from models.resume import ResumeProfile
    from models.analysis import TailoredResume

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS helper — skill chips
# ---------------------------------------------------------------------------

_CHIP_CSS = """
<style>
.chip-container { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.chip {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    background: rgba(91, 95, 255, 0.14);
    color: #C7C9FF;
    border: 1px solid rgba(91, 95, 255, 0.45);
    transition: transform 0.14s ease;
}
.chip:hover { transform: translateY(-1px); }
.chip-highlight {
    background: rgba(0, 230, 118, 0.14);
    color: #A8FFCF;
    border-color: rgba(0, 230, 118, 0.6);
}
.tailored-banner {
    background: linear-gradient(135deg, rgba(91,95,255,0.22), rgba(0,212,255,0.14));
    color: #F8FAFC;
    padding: 12px 18px;
    border-radius: 12px;
    font-size: 0.9rem;
    font-weight: 600;
    margin-bottom: 14px;
    border: 1px solid rgba(0,212,255,0.3);
    border-left: 4px solid #00D4FF;
    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
}
</style>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(
    profile: "ResumeProfile",
    is_tailored: bool = False,
    raw_text: Optional[str] = None,
) -> None:
    """
    Render a structured resume card from a ``ResumeProfile``.

    Sections rendered (in order):
    - Name and contact information
    - Seniority level badge + domain chip
    - Professional summary
    - Work experience (in an expander)
    - Education
    - Skills as inline chips
    - Certifications
    - Projects
    - Raw text expander (original resume only)

    Parameters
    ----------
    profile : ResumeProfile
        Validated resume profile output from Agent 1.
    is_tailored : bool
        When ``True``, suppress the raw-text expander and apply
        a visual "tailored" style.  Default: ``False``.
    raw_text : str, optional
        The cleaned raw PDF text.  Shown in a collapsed expander when
        ``is_tailored`` is ``False``.
    """
    st.markdown(_CHIP_CSS, unsafe_allow_html=True)

    pi = profile.personal_info

    # ── Header: name + contact ───────────────────────────────────────────────
    st.markdown(f"### 👤 {pi.full_name}")

    contact_parts: list[str] = []
    if pi.email:
        contact_parts.append(f"📧 {pi.email}")
    if pi.phone:
        contact_parts.append(f"📞 {pi.phone}")
    if pi.location:
        contact_parts.append(f"📍 {pi.location}")
    if pi.linkedin:
        contact_parts.append(f"[LinkedIn]({pi.linkedin})")
    if pi.github:
        contact_parts.append(f"[GitHub]({pi.github})")
    if pi.portfolio:
        contact_parts.append(f"[Portfolio]({pi.portfolio})")

    if contact_parts:
        st.markdown("  ·  ".join(contact_parts))

    st.divider()

    # ── Badges: seniority + domain + years ──────────────────────────────────
    badge_cols = st.columns(3)
    with badge_cols[0]:
        if profile.seniority_level:
            st.metric("Seniority", profile.seniority_level)
    with badge_cols[1]:
        if profile.dominant_domain:
            st.metric("Domain", profile.dominant_domain)
    with badge_cols[2]:
        if profile.total_years_experience is not None:
            st.metric("Experience", f"{profile.total_years_experience:.1f} yrs")

    # ── Summary ──────────────────────────────────────────────────────────────
    if profile.summary:
        st.markdown("#### 📝 Professional Summary")
        st.markdown(f"> {profile.summary}")

    # ── Work Experience ──────────────────────────────────────────────────────
    if profile.experience:
        with st.expander(
            f"💼 Work Experience ({len(profile.experience)} role(s))",
            expanded=True,
        ):
            for exp in profile.experience:
                end = exp.end_date or "Present"
                st.markdown(
                    f"**{exp.title}** — {exp.company}  \n"
                    f"_{exp.start_date} → {end}_"
                    + (f"  ·  📍 {exp.location}" if exp.location else "")
                )
                for bullet in exp.bullets:
                    st.markdown(f"- {bullet}")
                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)  # spacing

    # ── Education ────────────────────────────────────────────────────────────
    if profile.education:
        with st.expander(
            f"🎓 Education ({len(profile.education)} qualification(s))",
            expanded=False,
        ):
            for edu in profile.education:
                gpa_str = f"  ·  GPA {edu.gpa:.2f}" if edu.gpa else ""
                year_str = f" ({edu.year})" if edu.year else ""
                st.markdown(
                    f"**{edu.degree}**{year_str}  \n"
                    f"_{edu.institution}_"
                    + (f"  ·  {edu.field_of_study}" if edu.field_of_study else "")
                    + gpa_str
                )

    # ── Skills ───────────────────────────────────────────────────────────────
    if profile.skills:
        st.markdown("#### 🛠️ Skills")
        chips_html = '<div class="chip-container">' + "".join(
            f'<span class="chip">{skill}</span>' for skill in profile.skills
        ) + "</div>"
        st.markdown(chips_html, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)  # spacing below chips

    # ── Certifications ───────────────────────────────────────────────────────
    if profile.certifications:
        with st.expander(
            f"🏅 Certifications ({len(profile.certifications)})",
            expanded=False,
        ):
            for cert in profile.certifications:
                issuer_str = f" — {cert.issuer}" if cert.issuer else ""
                year_str = f" ({cert.year})" if cert.year else ""
                st.markdown(f"✔ **{cert.name}**{issuer_str}{year_str}")

    # ── Projects ─────────────────────────────────────────────────────────────
    if profile.projects:
        with st.expander(
            f"🚀 Projects ({len(profile.projects)})",
            expanded=False,
        ):
            for proj in profile.projects:
                url_str = f" · [{proj.url}]({proj.url})" if proj.url else ""
                year_str = f" ({proj.year})" if proj.year else ""
                st.markdown(f"**{proj.name}**{year_str}{url_str}")
                if proj.description:
                    st.markdown(proj.description)
                if proj.technologies:
                    tech_chips = '<div class="chip-container">' + "".join(
                        f'<span class="chip">{t}</span>' for t in proj.technologies
                    ) + "</div>"
                    st.markdown(tech_chips, unsafe_allow_html=True)
                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # ── Raw text (debug, original only) ──────────────────────────────────────
    if not is_tailored and raw_text:
        with st.expander("🔍 View raw extracted text", expanded=False):
            st.text(raw_text[:3000] + ("…" if len(raw_text) > 3000 else ""))

    logger.debug("resume_preview.render | name=%r | tailored=%s", pi.full_name, is_tailored)


def render_tailored(
    tailored: "TailoredResume",
    profile: "ResumeProfile",
) -> None:
    """
    Render the tailored resume produced by Agent 5.

    Sections rendered:
    - "Tailored for this role" banner
    - Rewritten professional summary
    - Rewritten work experience bullets
    - Highlighted skills chips
    - Suggested additions callout
    - Tailoring notes (collapsed)

    Parameters
    ----------
    tailored : TailoredResume
        Output of Agent 5 (Resume Tailor).
    profile : ResumeProfile
        Original parsed resume (used for candidate name header).
    """
    st.markdown(_CHIP_CSS, unsafe_allow_html=True)

    # Banner
    pi = profile.personal_info
    st.markdown(
        '<div class="tailored-banner">✨ AI-Tailored Resume — '
        f"Optimised for the target role for <strong>{pi.full_name}</strong></div>",
        unsafe_allow_html=True,
    )

    # ── Rewritten Summary ────────────────────────────────────────────────────
    if tailored.rewritten_summary:
        st.markdown("#### 📝 Tailored Professional Summary")
        st.info(tailored.rewritten_summary)

    # ── Rewritten Experience ─────────────────────────────────────────────────
    if tailored.rewritten_experience:
        st.markdown("#### 💼 Optimised Work Experience")
        with st.expander(
            f"View {len(tailored.rewritten_experience)} role(s)",
            expanded=True,
        ):
            for exp in tailored.rewritten_experience:
                end = exp.end_date or "Present"
                st.markdown(
                    f"**{exp.title}** — {exp.company}  \n"
                    f"_{exp.start_date} → {end}_"
                )
                for bullet in exp.bullets:
                    st.markdown(f"- {bullet}")
                st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # ── Highlighted Skills ───────────────────────────────────────────────────
    if tailored.highlighted_skills:
        st.markdown("#### 🛠️ Highlighted Skills for this Role")
        chips_html = '<div class="chip-container">' + "".join(
            f'<span class="chip chip-highlight">{skill}</span>'
            for skill in tailored.highlighted_skills
        ) + "</div>"
        st.markdown(chips_html, unsafe_allow_html=True)
        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # ── Suggested Additions ───────────────────────────────────────────────────
    if tailored.suggested_additions:
        st.markdown("#### 💡 Suggested Additions")
        st.success(
            "Consider adding the following to strengthen your application:\n\n"
            + "\n".join(f"- {item}" for item in tailored.suggested_additions)
        )

    # ── Tailoring Notes ───────────────────────────────────────────────────────
    if tailored.tailoring_notes:
        with st.expander("🗒️ AI Tailoring Notes (internal)", expanded=False):
            for note in tailored.tailoring_notes:
                st.markdown(f"- _{note}_")

    logger.debug(
        "resume_preview.render_tailored | skills=%d | additions=%d",
        len(tailored.highlighted_skills),
        len(tailored.suggested_additions),
    )
