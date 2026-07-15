"""
components/skill_gap_chart.py

Renders the Skill Gap analysis visualisation in the Streamlit UI.

Displays:
    1. A Plotly horizontal bar chart showing:
         - Matched skills     (green)
         - Missing critical   (red)
         - Missing preferred  (amber)
         - Transferable skills (blue)
    2. Three expandable lists below the chart:
         - Matched skills
         - Missing skills (critical + preferred)
         - Transferable skills + recommendations

Public API:
    render(skill_gap: SkillGapAnalysis) -> None
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import plotly.graph_objects as go
import streamlit as st

if TYPE_CHECKING:
    from models.analysis import SkillGapAnalysis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_COLOR_MATCHED = "#00E676"       # success
_COLOR_CRITICAL = "#FF5C8A"      # danger
_COLOR_PREFERRED = "#FFC107"     # warning
_COLOR_TRANSFERABLE = "#00D4FF"  # accent


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(skill_gap: "SkillGapAnalysis") -> None:
    """
    Render the full skill gap analysis panel.

    Shows a horizontal bar chart of skill counts by category, followed by
    expandable detail lists for each category and AI recommendations.

    Parameters
    ----------
    skill_gap : SkillGapAnalysis
        Output of Agent 3 (Skill Gap Analyzer), aliased as SkillGapReport.
    """
    # ── Summary metrics ──────────────────────────────────────────────────────
    with st.container(border=True):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric(
                "✅ Matched",
                len(skill_gap.matched_skills),
                help="Skills present in both your resume and the job description.",
            )
        with col2:
            st.metric(
                "🚨 Missing Critical",
                len(skill_gap.missing_critical),
                delta=f"-{len(skill_gap.missing_critical)}" if skill_gap.missing_critical else None,
                delta_color="inverse",
                help="Required skills from the JD that are absent from your resume.",
            )
        with col3:
            st.metric(
                "⚠️ Missing Preferred",
                len(skill_gap.missing_preferred),
                help="Nice-to-have skills from the JD you do not yet have.",
            )
        with col4:
            st.metric(
                "🔄 Transferable",
                len(skill_gap.transferable_skills),
                help="Skills you have that partially satisfy the JD requirements.",
            )

        if skill_gap.match_percentage is not None:
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
            st.progress(
                int(skill_gap.match_percentage) / 100,
                text=f"Skill Match: **{skill_gap.match_percentage:.0f}%**",
            )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── Bar chart ────────────────────────────────────────────────────────────
    with st.container(border=True):
        fig = _build_bar_chart(skill_gap)
        # Fix #7: use_container_width=True ensures the chart fills its container
        # on all viewports including mobile (avoids blank render on narrow screens)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── Detail expanders ─────────────────────────────────────────────────────
    if skill_gap.matched_skills:
        with st.expander(
            f"✅ Matched Skills ({len(skill_gap.matched_skills)})",
            expanded=False,
        ):
            st.markdown(
                '<div class="ah-chip-row">'
                + "".join(
                    f'<span class="ah-badge" style="background:rgba(0,230,118,0.14);'
                    f'color:#A8FFCF;border-color:rgba(0,230,118,0.5);">✔ {skill}</span>'
                    for skill in sorted(skill_gap.matched_skills)
                )
                + "</div>",
                unsafe_allow_html=True,
            )

    if skill_gap.missing_critical or skill_gap.missing_preferred:
        with st.expander(
            "🚨 Missing Skills "
            f"(Critical: {len(skill_gap.missing_critical)}  |  "
            f"Preferred: {len(skill_gap.missing_preferred)})",
            expanded=True,
        ):
            if skill_gap.missing_critical:
                st.markdown("**Critical (must-have):**")
                st.markdown(
                    '<div class="ah-chip-row">'
                    + "".join(
                        f'<span class="ah-badge" style="background:rgba(255,92,138,0.14);'
                        f'color:#FFD6E3;border-color:rgba(255,92,138,0.5);">🔴 {skill}</span>'
                        for skill in skill_gap.missing_critical
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
            if skill_gap.missing_preferred:
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                st.markdown("**Preferred (nice-to-have):**")
                st.markdown(
                    '<div class="ah-chip-row">'
                    + "".join(
                        f'<span class="ah-badge" style="background:rgba(255,193,7,0.14);'
                        f'color:#FFE9B3;border-color:rgba(255,193,7,0.5);">🟡 {skill}</span>'
                        for skill in skill_gap.missing_preferred
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )

    if skill_gap.transferable_skills:
        with st.expander(
            f"🔄 Transferable Skills ({len(skill_gap.transferable_skills)})",
            expanded=False,
        ):
            st.markdown(
                '<div class="ah-chip-row">'
                + "".join(
                    f'<span class="ah-badge ah-badge-accent">🔵 {skill}</span>'
                    for skill in skill_gap.transferable_skills
                )
                + "</div>",
                unsafe_allow_html=True,
            )

    if skill_gap.recommendations:
        st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
        st.markdown("#### 💡 Recommendations")
        for rec in skill_gap.recommendations:
            st.info(f"💡 {rec}")

    logger.debug(
        "skill_gap_chart.render | matched=%d | critical=%d | preferred=%d | transferable=%d",
        len(skill_gap.matched_skills),
        len(skill_gap.missing_critical),
        len(skill_gap.missing_preferred),
        len(skill_gap.transferable_skills),
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_bar_chart(skill_gap: "SkillGapAnalysis") -> go.Figure:
    """
    Build a Plotly horizontal bar chart with four colour-coded categories.

    Parameters
    ----------
    skill_gap : SkillGapAnalysis
        Source data for bar counts.

    Returns
    -------
    go.Figure
        Ready-to-render Plotly figure.
    """
    categories = [
        "Matched Skills",
        "Missing Critical",
        "Missing Preferred",
        "Transferable",
    ]
    counts = [
        len(skill_gap.matched_skills),
        len(skill_gap.missing_critical),
        len(skill_gap.missing_preferred),
        len(skill_gap.transferable_skills),
    ]
    colors = [_COLOR_MATCHED, _COLOR_CRITICAL, _COLOR_PREFERRED, _COLOR_TRANSFERABLE]

    fig = go.Figure(
        go.Bar(
            x=counts,
            y=categories,
            orientation="h",
            marker=dict(
                color=colors,
                line=dict(width=0),
                cornerradius=6,
            ),
            text=counts,
            textposition="outside",
            textfont=dict(family="IBM Plex Mono, monospace", size=13, color="#F8FAFC"),
            hovertemplate="%{y}: <b>%{x}</b> skills<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(
            text="Skill Gap Overview",
            font=dict(size=16, color="#F8FAFC", family="IBM Plex Sans, sans-serif"),
        ),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=True,
            color="#94A3B8",
        ),
        yaxis=dict(
            showgrid=False,
            color="#94A3B8",
            tickfont=dict(size=13, family="Inter, sans-serif"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#F8FAFC", family="Inter, sans-serif"),
        # Fix #7: Use autosize=True and no fixed height so chart adapts to container width
        # Tighter left margin (l=10) prevents y-axis labels clipping on narrow screens
        margin=dict(l=10, r=60, t=50, b=20, pad=4),
        autosize=True,
        bargap=0.35,
    )

    return fig
