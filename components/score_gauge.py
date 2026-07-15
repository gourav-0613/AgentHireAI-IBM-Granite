"""
components/score_gauge.py

Renders the ATS Match Score gauge and breakdown table.

Fix #6: Gauge now uses solid dark-tinted zone fills instead of transparent
rgba backgrounds. The progress arc uses solid cyan (#00D4FF). The threshold
line has been removed (redundant with the solid progress bar).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import plotly.graph_objects as go
import streamlit as st

if TYPE_CHECKING:
    from core.scorer import ScoreResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label → colour map
# ---------------------------------------------------------------------------

_LABEL_COLORS: dict[str, str] = {
    "Strong Match": "#00E676",
    "Good Match":   "#8BC34A",
    "Partial Match": "#FFC107",
    "Low Match":    "#FF5C8A",
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(score_result: "ScoreResult") -> None:
    """
    Render the match score panel.

    Shows:
    - A large Plotly gauge chart (solid arc, solid dark zones)
    - A coloured fit label
    - An expandable score breakdown table
    """
    col_gauge, col_info = st.columns([1, 1], gap="large")

    with col_gauge:
        with st.container(border=True):
            fig = _build_gauge(score_result.total_score)
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_info:
        with st.container(border=True):
            st.markdown("#### 🏷️ Match Assessment")

            label_color = _LABEL_COLORS.get(score_result.fit_label, "#9E9E9E")
            st.markdown(
                f'<div class="ah-fit-pill" style="'
                f"background:{label_color}22; color:{label_color}; "
                f'border:2px solid {label_color};">'
                f"{score_result.fit_label}</div>",
                unsafe_allow_html=True,
            )

            st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

            # Per-signal summary
            st.markdown("**Score signals**")

            signal_data = [
                ("Required Skills", score_result.required_signal, 0.50),
                ("Experience Match", score_result.experience_signal, 0.20),
                ("Preferred Skills", score_result.preferred_signal, 0.15),
                ("Keyword Coverage", score_result.keyword_signal, 0.10),
                ("Education Match", score_result.education_signal, 0.05),
            ]

            for label, raw, weight in signal_data:
                pct = raw * 100
                contribution = round(raw * weight * 100, 1)
                bar_color = "#00E676" if raw >= 0.7 else "#FFC107" if raw >= 0.4 else "#FF5C8A"
                st.markdown(
                    f"<div style='margin-bottom:10px;'>"
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:0.8rem;color:#94A3B8;margin-bottom:4px;'>"
                    f"<span>{label}</span>"
                    f"<span style='color:{bar_color};font-weight:700;'>"
                    f"{pct:.0f}% <span style='color:#64748B;font-weight:500;'>"
                    f"→ {contribution:.1f} pts</span></span></div>"
                    f"<div style='height:6px;border-radius:4px;background:rgba(148,163,184,0.14);overflow:hidden;'>"
                    f"<div style='height:100%;border-radius:4px;width:{pct:.0f}%;"
                    f"background:linear-gradient(90deg,{bar_color},{bar_color}CC);'></div>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

    # ── Breakdown table ──────────────────────────────────────────────────────
    with st.container(border=True):
        st.markdown("#### 📊 Score Breakdown")
        rows = _build_breakdown_table(score_result)

        import pandas as pd  # noqa: PLC0415

        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
        )

    logger.debug(
        "score_gauge.render | total=%.1f | label=%r",
        score_result.total_score,
        score_result.fit_label,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_gauge(total_score: float) -> go.Figure:
    """
    Build a Plotly indicator gauge for the total ATS match score.

    Fix #6: Solid dark zone fills (no transparent rgba). Solid cyan progress arc.
    Threshold line removed. Background is solid dark (#111827).

    Colour zones:
    - Dark red-tint  0–35   (Low Match)
    - Dark amber-tint 35–55  (Partial Match)
    - Dark yellow-green 55–75 (Good Match)
    - Dark green-tint 75–100 (Strong Match)
    """
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=total_score,
            number=dict(
                suffix=" / 100",
                font=dict(size=30, color="#F8FAFC", family="IBM Plex Mono, monospace"),
            ),
            title=dict(
                text="ATS Match Score",
                font=dict(size=14, color="#94A3B8", family="Inter, sans-serif"),
            ),
            gauge=dict(
                axis=dict(
                    range=[0, 100],
                    tickwidth=1,
                    tickcolor="#475569",
                    tickfont=dict(color="#94A3B8", size=10, family="Inter, sans-serif"),
                ),
                # Fix #6: Solid cyan progress arc (no transparency)
                bar=dict(color="#00D4FF", thickness=0.30),
                # Fix #6: Solid dark background for the gauge face
                bgcolor="#111827",
                borderwidth=2,
                bordercolor="rgba(148,163,184,0.25)",
                # Fix #6: Solid dark-tinted zone fills (no transparent rgba)
                steps=[
                    dict(range=[0, 35],   color="#2A1420"),   # dark red-tint
                    dict(range=[35, 55],  color="#2A2010"),   # dark amber-tint
                    dict(range=[55, 75],  color="#182A14"),   # dark yellow-green
                    dict(range=[75, 100], color="#0E2420"),   # dark green-tint
                ],
                # Fix #6: Remove redundant threshold line
            ),
        )
    )

    fig.update_layout(
        paper_bgcolor="#111827",
        font=dict(color="#F8FAFC", family="Inter, sans-serif"),
        margin=dict(l=24, r=24, t=44, b=20),
        height=270,
    )

    return fig


def _build_breakdown_table(score_result: "ScoreResult") -> list[dict]:
    """Build a list of row dictionaries for the score breakdown table."""
    rows: list[dict] = []

    signal_meta = [
        ("Required Skills Coverage", 50, score_result.required_signal),
        ("Experience Match", 20, score_result.experience_signal),
        ("Preferred Skills Coverage", 15, score_result.preferred_signal),
        ("Keyword Coverage", 10, score_result.keyword_signal),
        ("Education Alignment", 5, score_result.education_signal),
    ]

    total_contribution = 0.0
    for label, weight_pct, raw_signal in signal_meta:
        contribution = round(raw_signal * (weight_pct / 100) * 100, 1)
        total_contribution += contribution
        rows.append(
            {
                "Signal": label,
                "Weight": f"{weight_pct}%",
                "Raw Score": f"{raw_signal * 100:.0f}%",
                "Contribution (pts)": f"{contribution:.1f}",
            }
        )

    rows.append(
        {
            "Signal": "**TOTAL**",
            "Weight": "100%",
            "Raw Score": "—",
            "Contribution (pts)": f"**{score_result.total_score:.1f}**",
        }
    )

    return rows
