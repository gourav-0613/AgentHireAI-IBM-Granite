"""
components/theme.py

Shared presentation layer for AgentHire AI's premium dark UI.

Public API:
    load_css()                         -> injects styles.css once per session
    branded_icon(name, size)           -> returns inline <svg> from assets/icons/{name}.svg
    icon(name, size, color)            -> returns an inline Lucide-style <svg> string (kept for non-mapped icons)
    section_title(...)                 -> renders a section heading with accent bar
    glass_card(...)                    -> returns HTML for a feature/info card using branded ai-agent icon
    stage_pill(stage)                  -> renders the sidebar pipeline-stage indicator
    brand_icon_svg() / brand_logo_svg() / favicon_path()
                                       -> raw asset accessors for assets/*.svg
    brand_mark(size, glow)             -> renders the icon mark inside a rounded badge
    brand_header(nav_title)            -> renders the slim top brand bar used on every page (enlarged)
    hero_illustration()                -> renders the premium landing-page hero visual
    empty_state(title, desc, icon_name, compact)
                                       -> renders a polished "nothing here yet" card
    stage_indicator(active_index, completed_index)
                                       -> renders the 6-stage pipeline stepper
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path

import streamlit as st

logger = logging.getLogger(__name__)

_CSS_PATH = Path(__file__).resolve().parent.parent / "styles.css"
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_ICONS_DIR = _ASSETS_DIR / "icons"

# ---------------------------------------------------------------------------
# CSS loader
# ---------------------------------------------------------------------------


def load_css() -> None:
    """
    Inject ``styles.css`` into the current page.

    Streamlit re-parses ``st.markdown`` on every script run (there is no
    persistent <head>), so this is called once at the top of every page —
    it is cheap (a single file read + markdown call) and idempotent.
    """
    try:
        css = _CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        logger.warning("theme.load_css | styles.css not found at %s", _CSS_PATH)


# ---------------------------------------------------------------------------
# Branded SVG icon reader — assets/icons/{name}.svg
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _read_icon_file(filename: str) -> str:
    """Read and cache an SVG icon from assets/icons/."""
    path = _ICONS_DIR / filename
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        logger.warning("theme._read_icon_file | missing icon %s", filename)
        return ""


def branded_icon(name: str, size: int = 22) -> str:
    """
    Return an inline ``<svg>`` string for a branded icon from assets/icons/.

    The SVG file is read once and cached. The ``width`` and ``height``
    attributes on the root ``<svg>`` element are overwritten so that the icon
    renders at the requested ``size`` in pixels.

    Parameters
    ----------
    name : str
        Icon filename without extension, e.g. ``"upload-resume"``.
        Falls back to the Lucide ``upload`` icon if the file is missing.
    size : int
        Width and height in pixels.

    Returns
    -------
    str
        Ready-to-embed ``<svg>...</svg>`` markup.
    """
    svg = _read_icon_file(f"{name}.svg")
    if not svg:
        # Graceful fallback to lucide dot
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="none" stroke="#00D4FF" stroke-width="1.5">'
            f'<circle cx="12" cy="12" r="4" fill="#00D4FF" stroke="none"/></svg>'
        )

    # Overwrite width/height attributes so the caller controls size.
    # We inject them after the opening <svg tag.
    svg = re.sub(
        r'(<svg[^>]*?)\s+width="[^"]*"', r"\1", svg
    )
    svg = re.sub(
        r'(<svg[^>]*?)\s+height="[^"]*"', r"\1", svg
    )
    svg = svg.replace(
        "<svg ",
        f'<svg width="{size}" height="{size}" style="vertical-align:middle;flex-shrink:0;" ',
        1,
    )
    return svg


# ---------------------------------------------------------------------------
# Lucide-style icon set (fallback / non-mapped positions)
# ---------------------------------------------------------------------------

_ICONS: dict[str, str] = {
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
    "upload": '<path d="M12 16V4M12 4l-4 4M12 4l4 4"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>',
    "file-text": '<path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M14 3v4h4"/><path d="M9 13h6M9 17h6M9 9h2"/>',
    "clipboard": '<rect x="6" y="4" width="12" height="17" rx="2"/><rect x="9" y="2.5" width="6" height="3" rx="1"/><path d="M9 11h6M9 15h6"/>',
    "brain": '<path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-1.5 5.2A3 3 0 0 0 7 18h1"/><path d="M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 1.5 5.2A3 3 0 0 1 17 18h-1"/><path d="M9 4v14M15 4v14"/>',
    "key": '<circle cx="8" cy="14" r="4"/><path d="M11 11l8-8M16 5l2 2M19 2l2 2"/>',
    "sparkles": '<path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="M5.5 5.5l2.8 2.8M15.7 15.7l2.8 2.8M18.5 5.5l-2.8 2.8M8.3 15.7l-2.8 2.8"/>',
    "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.3 2.3 4.7-5.1"/>',
    "alert-triangle": '<path d="M12 4 2 20h20L12 4z"/><path d="M12 10v4"/><circle cx="12" cy="17" r="0.9" fill="currentColor" stroke="none"/>',
    "trending-up": '<path d="M4 15l6-6 4 4 6-8"/><path d="M15 5h5v5"/>',
    "layers": '<path d="M12 3 3 8l9 5 9-5-9-5z"/><path d="M3 13l9 5 9-5"/><path d="M3 17.5l9 5 9-5"/>',
    "cpu": '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.5 4.5 7 7M17 17l2.5 2.5M19.5 4.5 17 7M7 17l-2.5 2.5"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.5-3 8-7 9-4-1-7-4.5-7-9V6l7-3z"/><path d="M9 12l2 2 4-4"/>',
    "download": '<path d="M12 4v11M12 15l-4-4M12 15l4-4"/><path d="M5 18h14"/>',
    "briefcase": '<rect x="3" y="8" width="18" height="12" rx="2"/><path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "award": '<circle cx="12" cy="8" r="5"/><path d="M9 12.5 7 21l5-2.5L17 21l-2-8.5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 20c1.5-4 5-6 8-6s6.5 2 8 6"/>',
    "zap": '<path d="M13 3 5 13h6l-1 8 8-11h-6l1-7z"/>',
    "bar-chart": '<path d="M4 20V10M11 20V4M18 20v-7"/>',
    "gauge": '<path d="M4 15a8 8 0 1 1 16 0"/><path d="M12 15l4-5"/><circle cx="12" cy="15" r="1" fill="currentColor" stroke="none"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.35-4.35"/>',
}


def icon(name: str, size: int = 18, color: str = "currentColor", stroke_width: float = 2.0) -> str:
    """
    Return an inline ``<svg>`` string for a Lucide-style icon.

    Kept for internal UI elements that don't map to the branded icon set
    (e.g. dots, check-circles, section decorations).
    """
    body = _ICONS.get(name, '<circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="{stroke_width}" '
        f'stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;">{body}</svg>'
    )


# ---------------------------------------------------------------------------
# Brand assets (assets/logo.svg, icon.svg, favicon.svg — Concept 1 mark)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _read_asset(filename: str) -> str:
    """Read and cache a text asset from the assets/ directory."""
    try:
        return (_ASSETS_DIR / filename).read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("theme._read_asset | missing asset %s", filename)
        return ""


def brand_icon_svg() -> str:
    """Return the raw ``<svg>`` markup for assets/icon.svg."""
    return _read_asset("icon.svg")


def brand_logo_svg() -> str:
    """Return the raw ``<svg>`` markup for assets/logo.svg."""
    return _read_asset("logo.svg")


def favicon_path() -> str:
    """Return an absolute path string to assets/favicon.svg for ``st.set_page_config``."""
    return str(_ASSETS_DIR / "favicon.svg")


# ---------------------------------------------------------------------------
# Pipeline stages — now use branded icon filenames
# ---------------------------------------------------------------------------

#: The six named stages of the pipeline, in order, for the loading stepper.
#: (label, branded_icon_name) — purely presentational.
PIPELINE_STAGES: tuple[tuple[str, str], ...] = (
    ("Resume Parsing", "upload-resume"),
    ("JD Analysis", "job-description"),
    ("Skill Gap", "skill-gap"),
    ("ATS", "ats"),
    ("Resume Tailoring", "resume-tailoring"),
    ("PDF Generation", "pdf-download"),
)


# ---------------------------------------------------------------------------
# HTML snippet builders
# ---------------------------------------------------------------------------


def section_title(title: str, icon_name: str | None = None, subtitle: str | None = None) -> None:
    """Render a section heading with an accent bar and optional branded icon/subtitle."""
    if icon_name:
        # Try branded icon first; fall back to lucide
        ic = branded_icon(icon_name, 20)
        if not ic or ic.startswith('<svg') and 'circle cx="12" cy="12" r="4"' in ic and 'fill="#00D4FF"' in ic:
            # fallback was used — try lucide
            ic = f'{icon(icon_name, 20, "#00D4FF")}'
    else:
        ic = ""
    st.markdown(
        f'<div class="ah-section-title ah-animate">{ic}<span>{title}</span></div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.markdown(f'<div class="ah-section-sub">{subtitle}</div>', unsafe_allow_html=True)


def glass_card(icon_name: str, title: str, desc: str, use_branded: bool = True) -> str:
    """
    Return HTML for a single glass feature card.

    For agent feature cards, always uses the branded ai-agent.svg icon.
    For workflow step cards, uses the icon_name mapped to branded icons.
    """
    if use_branded:
        # Map lucide names to branded equivalents
        _LUCIDE_TO_BRANDED = {
            "file-text": "upload-resume",
            "clipboard": "job-description",
            "brain": "skill-gap",
            "key": "ats",
            "sparkles": "resume-tailoring",
            "download": "pdf-download",
            "gauge": "score",
        }
        branded = _LUCIDE_TO_BRANDED.get(icon_name, "ai-agent")
        ic_html = branded_icon(branded, 26)
    else:
        ic_html = icon(icon_name, 22, "#00D4FF")

    return (
        '<div class="ah-card ah-animate">'
        f'<div class="ah-card-icon">{ic_html}</div>'
        f'<div class="ah-card-title">{title}</div>'
        f'<div class="ah-card-desc">{desc}</div>'
        "</div>"
    )


def stage_pill(stage: str) -> None:
    """Render the pipeline-stage indicator pill used in the sidebar."""
    meta = {
        "IDLE": ("ah-dot-idle", "Awaiting resume upload"),
        "PARSED": ("ah-dot-parsed", "Resume parsed"),
        "ANALYZED": ("ah-dot-analyzed", "Analysis complete"),
        "COMPLETE": ("ah-dot-complete", "Tailored resume ready"),
    }
    dot_class, label = meta.get(stage, ("ah-dot-idle", stage))
    st.markdown(
        f'<div class="ah-stage-pill"><span class="ah-dot {dot_class}"></span>'
        f"<span>{label}</span></div>",
        unsafe_allow_html=True,
    )


def badge(text: str, accent: bool = False) -> str:
    """Return HTML for a small pill badge."""
    cls = "ah-badge ah-badge-accent" if accent else "ah-badge"
    return f'<span class="{cls}">{text}</span>'


def brand_mark(size: int = 76, glow: bool = True) -> str:
    """
    Return HTML for the icon mark (assets/icon.svg) inside a rounded gradient badge.

    Fix #1: default size increased from 56 → 76 (≈35% larger).
    """
    svg = brand_icon_svg()
    shadow = "box-shadow:0 6px 22px rgba(91,95,255,0.4);" if glow else ""
    inner = int(size * 0.62)
    return (
        f'<div class="ah-brand-mark" style="width:{size}px;height:{size}px;{shadow}">'
        f'<div style="width:{inner}px;height:{inner}px;">{svg}</div>'
        f"</div>"
    )


def brand_header(nav_title: str | None = None) -> None:
    """
    Render the slim top brand bar (icon mark + wordmark [+ breadcrumb tail]).

    Fix #1: icon mark 35% larger (34 → 46px), wordmark font 20% larger (1.05 → 1.26rem).
    """
    tail = (
        f'<span class="ah-brand-header-sep">/</span>'
        f'<span class="ah-brand-header-tail">{nav_title}</span>'
        if nav_title
        else ""
    )
    st.markdown(
        f'<div class="ah-brand-header ah-animate">'
        f"{brand_mark(46, glow=False)}"
        f'<span class="ah-brand-header-name">AgentHire'
        f'<span style="color:#00D4FF;">AI</span></span>'
        f"{tail}"
        f"</div>",
        unsafe_allow_html=True,
    )


def hero_illustration() -> None:
    """
    Render the premium hero visual for the landing page.

    The real brand mark (assets/icon.svg) sits inside a glowing, slowly
    rotating ring with a few floating accent nodes — dark AI-SaaS style.
    """
    svg = brand_icon_svg()
    st.markdown(
        f"""
        <div class="ah-hero-art ah-animate">
          <div class="ah-hero-art-glow"></div>
          <div class="ah-hero-art-ring"></div>
          <div class="ah-hero-art-mark">{svg}</div>
          <span class="ah-hero-art-node ah-node-1"></span>
          <span class="ah-hero-art-node ah-node-2"></span>
          <span class="ah-hero-art-node ah-node-3"></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(
    title: str,
    desc: str,
    icon_name: str = "search",
    compact: bool = False,
) -> None:
    """Render a polished empty-state card."""
    cls = "ah-empty-state ah-empty-compact ah-animate" if compact else "ah-empty-state ah-animate"
    # Try branded icon, fall back to lucide
    _BRANDED_MAP = {
        "upload": "upload-resume",
        "search": None,  # no branded search — use lucide
        "file-text": "upload-resume",
    }
    branded_name = _BRANDED_MAP.get(icon_name)
    if branded_name:
        ic_html = branded_icon(branded_name, 26)
    else:
        ic_html = icon(icon_name, 26, "#5B6478", 1.6)

    st.markdown(
        f"""
        <div class="{cls}">
          <div class="ah-empty-ring">{ic_html}</div>
          <div class="ah-empty-title">{title}</div>
          <div class="ah-empty-desc">{desc}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def stage_indicator(active_index: int = -1, completed_index: int = -1) -> None:
    """
    Render the 6-stage pipeline stepper using branded SVG icons.

    Parameters
    ----------
    active_index : int
        Index (0-5) of the stage currently in progress, or ``-1`` if none.
    completed_index : int
        Index of the last fully completed stage, or ``-1`` if none yet.
    """
    steps_html = []
    for i, (label, ic_name) in enumerate(PIPELINE_STAGES):
        if i <= completed_index:
            state = "done"
            dot_html = icon("check-circle", 15, "#0B1020")
        elif i == active_index:
            state = "active"
            dot_html = branded_icon(ic_name, 15)
        else:
            state = "pending"
            dot_html = branded_icon(ic_name, 15)

        steps_html.append(
            f'<div class="ah-stage-step ah-stage-{state}">'
            f'<div class="ah-stage-dot">{dot_html}</div>'
            f'<span class="ah-stage-label">{label}</span>'
            f"</div>"
        )
        if i < len(PIPELINE_STAGES) - 1:
            steps_html.append('<div class="ah-stage-line"></div>')

    st.markdown(
        f'<div class="ah-stage-track">{"".join(steps_html)}</div>',
        unsafe_allow_html=True,
    )
