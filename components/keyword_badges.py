"""
components/keyword_badges.py

Renders ATS keyword badges in the Streamlit UI.

Displays:
    - Each keyword from ATSScore.priority_keywords as a coloured pill badge
    - Green badge  → keyword is present in the candidate's resume
    - Red badge    → keyword is missing from the candidate's resume
    - Badge opacity/border reflects the keyword weight (0.0–1.0)
    - Two callout boxes below:
         "Phrases to include" list
         "Phrases to avoid"   list
    - ATS score summary (current vs. projected)

Public API:
    render(ats_report: ATSScore) -> None
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    from models.analysis import ATSScore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS for badge styles
# ---------------------------------------------------------------------------

_BADGE_CSS = """
<style>
.badge-wrap {
    display: flex;
    flex-wrap: wrap;
    gap: 7px;
    margin: 8px 0 16px 0;
}
.kw-badge {
    display: inline-block;
    padding: 5px 13px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    cursor: default;
    transition: transform 0.14s ease, opacity 0.14s ease;
}
.kw-badge:hover { transform: translateY(-1px); }
.kw-present {
    background-color: rgba(0, 230, 118, VAR_ALPHA);
    color: #C9FFE2;
    border: 1px solid rgba(0, 230, 118, 0.8);
}
.kw-missing {
    background-color: rgba(255, 92, 138, VAR_ALPHA);
    color: #FFD6E3;
    border: 1px solid rgba(255, 92, 138, 0.8);
}
.ats-score-box {
    display: flex;
    gap: 20px;
    margin: 10px 0 18px 0;
}
.ats-box {
    background: linear-gradient(145deg, rgba(91,95,255,0.14), rgba(0,212,255,0.08));
    border-radius: 12px;
    padding: 10px 18px;
    text-align: center;
    min-width: 130px;
    border: 1px solid rgba(0,212,255,0.3);
    box-shadow: 0 4px 18px rgba(0,0,0,0.22);
    transition: transform 0.16s ease, box-shadow 0.16s ease;
}
.ats-box:hover { transform: translateY(-2px); box-shadow: 0 10px 26px rgba(0,212,255,0.14); }
.ats-label { font-size: 0.73rem; color: #94A3B8; margin-bottom: 4px; }
.ats-value { font-size: 1.5rem; font-weight: 800; color: #F8FAFC; }
</style>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(ats_report: "ATSScore") -> None:
    """
    Render the ATS keyword optimisation panel.

    Shows:
    - ATS score summary (current vs. projected after optimisation)
    - Keyword presence/absence badge grid (sorted by weight)
    - "Phrases to include" and "Phrases to avoid" callout boxes

    Parameters
    ----------
    ats_report : ATSScore
        Output of Agent 4 (ATS Keyword Optimizer), aliased as ATSReport.
    """
    st.markdown(_BADGE_CSS, unsafe_allow_html=True)

    # ── ATS score summary ─────────────────────────────────────────────────────
    current_score = ats_report.overall_ats_score
    optimised_score = ats_report.optimised_ats_score

    if current_score is not None or optimised_score is not None:
        with st.container(border=True):
            score_cols = st.columns(3)
            with score_cols[0]:
                if current_score is not None:
                    st.metric(
                        "Current ATS Score",
                        f"{current_score:.0f}",
                        help="Estimated ATS pass-through score for your current resume.",
                    )
            with score_cols[1]:
                if optimised_score is not None:
                    delta = None
                    if current_score is not None:
                        delta = f"+{optimised_score - current_score:.0f}"
                    st.metric(
                        "Projected (Optimised)",
                        f"{optimised_score:.0f}",
                        delta=delta,
                        help="Projected ATS score after applying all recommendations.",
                    )
            with score_cols[2]:
                if ats_report.priority_keywords:
                    present_count = sum(
                        1 for kw in ats_report.priority_keywords if kw.present_in_resume
                    )
                    total = len(ats_report.priority_keywords)
                    st.metric(
                        "Keywords Found",
                        f"{present_count} / {total}",
                        help="Keywords from the job description found in your resume.",
                    )

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── Keyword badges ───────────────────────────────────────────────────────
    if ats_report.priority_keywords:
        # Already sorted by weight descending (validator in model does this)
        present_kws = [kw for kw in ats_report.priority_keywords if kw.present_in_resume]
        missing_kws = [kw for kw in ats_report.priority_keywords if not kw.present_in_resume]

        with st.container(border=True):
            st.markdown(
                f"<div style='font-size:0.85rem;color:#94A3B8;margin-bottom:4px;'>"
                f"<b style='color:#F8FAFC;'>Keywords detected:</b> "
                f"<span style='color:#00E676;font-weight:700;'>{len(present_kws)} present</span>"
                f"  ·  <span style='color:#FF5C8A;font-weight:700;'>{len(missing_kws)} missing</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            badges_html = '<div class="badge-wrap">'
            for kw in ats_report.priority_keywords:
                badges_html += _badge_html(kw.keyword, kw.weight, kw.present_in_resume)
            badges_html += "</div>"
            st.markdown(badges_html, unsafe_allow_html=True)

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    else:
        st.info("No priority keywords found in the ATS report.")

    # ── Phrases to include ───────────────────────────────────────────────────
    if ats_report.phrases_to_include:
        st.markdown("#### ✅ Phrases to Include")
        st.success(
            "Add these exact phrases or acronyms to your resume to improve ATS matching:\n\n"
            + "\n".join(f"- **{phrase}**" for phrase in ats_report.phrases_to_include)
        )
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # ── Phrases to avoid ─────────────────────────────────────────────────────
    if ats_report.phrases_to_avoid:
        st.markdown("#### ⚠️ Phrases to Avoid")
        st.warning(
            "Remove or replace these overused or penalised buzzwords:\n\n"
            + "\n".join(f"- {phrase}" for phrase in ats_report.phrases_to_avoid)
        )

    logger.debug(
        "keyword_badges.render | keywords=%d | present=%d",
        len(ats_report.priority_keywords),
        sum(1 for kw in ats_report.priority_keywords if kw.present_in_resume),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _badge_html(keyword: str, weight: float, present: bool) -> str:
    """
    Return an HTML ``<span>`` badge string for a single ATS keyword.

    Colour: green for present, red for missing.
    Alpha channel scales with keyword weight (0.3–1.0 range).

    Parameters
    ----------
    keyword : str
        The keyword text to display.
    weight : float
        Relevance weight in [0.0, 1.0].  Controls badge opacity.
    present : bool
        ``True`` if the keyword appears in the resume.

    Returns
    -------
    str
        HTML ``<span>`` element ready for ``st.markdown(..., unsafe_allow_html=True)``.
    """
    # Alpha: map weight [0.0, 1.0] → opacity [0.35, 1.0]
    alpha = round(0.35 + weight * 0.65, 2)
    css_class = "kw-badge kw-present" if present else "kw-badge kw-missing"
    icon = "✓" if present else "✗"
    # title tooltip shows weight
    title = f"Weight: {weight:.2f} | {'Present' if present else 'Missing'}"
    style = f"opacity: {alpha};"
    return (
        f'<span class="{css_class}" style="{style}" title="{title}">'
        f"{icon} {keyword}</span>"
    )
