"""
core/session_state.py

Streamlit session-state schema definition and lifecycle helpers.

This module is the single source of truth for every key stored in
``st.session_state``.  No page or agent should write ad-hoc keys outside
this schema — all additions must go through this module.

Responsibilities:
    - Declare the canonical set of session-state keys with their types and
      default values (``_DEFAULTS``).
    - Provide ``initialise()`` — called once in ``app.py`` on every Streamlit
      re-run.  Idempotent: only sets keys that are not already present.
    - Provide ``reset_downstream(from_stage)`` — clears stale data when the
      user re-uploads a resume or changes the job description.
    - Expose typed accessor helpers (``get_*`` / ``set_*``) so the rest of
      the codebase avoids raw ``st.session_state`` string lookups.

Session-state keys and types
-----------------------------

+-------------------+-------------------------------+----------------------------------+
| Key               | Type                          | Set by                           |
+===================+===============================+==================================+
| resume_raw_text   | ``str | None``                | ``core.pdf_reader``              |
+-------------------+-------------------------------+----------------------------------+
| resume_profile    | ``ResumeProfile | None``      | Agent 1 (Resume Parser)          |
+-------------------+-------------------------------+----------------------------------+
| job_description   | ``JobDescription | None``     | Agent 2 (JD Analyzer)            |
+-------------------+-------------------------------+----------------------------------+
| skill_gap_report  | ``SkillGapAnalysis | None``   | Agent 3 (Skill Gap Analyzer)     |
+-------------------+-------------------------------+----------------------------------+
| ats_report        | ``ATSScore | None``           | Agent 4 (ATS Keyword Optimizer)  |
+-------------------+-------------------------------+----------------------------------+
| tailored_resume   | ``TailoredResume | None``     | Agent 5 (Resume Tailor)          |
+-------------------+-------------------------------+----------------------------------+
| match_score       | ``float | None``              | ``core.scorer``                  |
+-------------------+-------------------------------+----------------------------------+
| pdf_bytes         | ``bytes | None``              | ``core.pdf_generator``           |
+-------------------+-------------------------------+----------------------------------+
| pipeline_stage    | ``str``                       | Lifecycle helpers below          |
+-------------------+-------------------------------+----------------------------------+

Pipeline stage transitions
---------------------------

.. code-block:: text

    IDLE → PARSED      after Agent 1 succeeds and user confirms preview
    PARSED → ANALYZED  after Agents 2–4 complete
    ANALYZED → COMPLETE after Agent 5 + scorer + pdf_generator complete

Usage::

    from core.session_state import initialise, reset_downstream
    initialise()                  # call in app.py on every re-run
    reset_downstream("PARSED")    # call when the JD text changes
"""

from __future__ import annotations

import logging
from typing import Any, Optional, TYPE_CHECKING

import streamlit as st

if TYPE_CHECKING:
    # Imported for type annotations only — avoids circular imports at runtime
    from models.resume import ResumeProfile
    from models.job_description import JobDescription
    from models.analysis import SkillGapAnalysis, ATSScore, TailoredResume

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pipeline stage constants
# ---------------------------------------------------------------------------

STAGE_IDLE: str = "IDLE"
"""Pipeline has not started; no resume has been uploaded yet."""

STAGE_PARSED: str = "PARSED"
"""Agent 1 has completed; ``resume_profile`` is populated."""

STAGE_ANALYZED: str = "ANALYZED"
"""Agents 2–4 have completed; ``job_description``, ``skill_gap_report``,
and ``ats_report`` are all populated."""

STAGE_COMPLETE: str = "COMPLETE"
"""Agent 5, scorer, and pdf_generator have all completed; the tailored
PDF resume is ready for download."""

#: Ordered tuple used to validate stage strings at runtime.
_VALID_STAGES: tuple[str, ...] = (
    STAGE_IDLE,
    STAGE_PARSED,
    STAGE_ANALYZED,
    STAGE_COMPLETE,
)

# ---------------------------------------------------------------------------
# Default state schema
# ---------------------------------------------------------------------------

#: Maps every session-state key to its initial (reset) value.
#: ``None`` indicates "not yet computed".
_DEFAULTS: dict[str, Any] = {
    # ── Resume pipeline ───────────────────────────────────────────────────
    "resume_raw_text": None,   # str | None
    "resume_profile": None,    # ResumeProfile | None
    # ── JD pipeline ──────────────────────────────────────────────────────
    "job_description": None,   # JobDescription | None
    # ── Analysis pipeline ────────────────────────────────────────────────
    "skill_gap_report": None,  # SkillGapAnalysis | None
    "ats_report": None,        # ATSScore | None
    "tailored_resume": None,   # TailoredResume | None
    # ── Scoring and output ───────────────────────────────────────────────
    "match_score": None,       # float | None  (0.0–100.0)
    "pdf_bytes": None,         # bytes | None
    # ── Workflow metadata ────────────────────────────────────────────────
    "pipeline_stage": STAGE_IDLE,  # str (one of _VALID_STAGES)
}

# ---------------------------------------------------------------------------
# Keys cleared at each downstream reset point
# ---------------------------------------------------------------------------

#: Keys cleared when the user re-uploads a new resume (from_stage="IDLE")
_RESET_FROM_IDLE: tuple[str, ...] = tuple(_DEFAULTS.keys())

#: Keys cleared when the JD changes but the parsed resume is kept
_RESET_FROM_PARSED: tuple[str, ...] = (
    "job_description",
    "skill_gap_report",
    "ats_report",
    "tailored_resume",
    "match_score",
    "pdf_bytes",
)

#: Keys cleared when re-tailoring is triggered but analysis results are kept
_RESET_FROM_ANALYZED: tuple[str, ...] = (
    "tailored_resume",
    "match_score",
    "pdf_bytes",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def initialise() -> None:
    """
    Ensure every canonical session-state key exists in ``st.session_state``.

    Safe to call on every Streamlit re-run — only missing keys are written;
    existing values are never overwritten.  Call this at the very top of
    ``app.py`` before rendering any page component.

    Returns
    -------
    None
    """
    for key, default in _DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default
    logger.debug("session_state.initialise | schema applied")


def reset_downstream(from_stage: str) -> None:
    """
    Clear all session-state keys that are downstream of *from_stage*.

    Use this to invalidate stale data when the user changes an earlier
    pipeline input (e.g. uploads a new resume or edits the job description).

    Parameters
    ----------
    from_stage : str
        One of ``STAGE_IDLE``, ``STAGE_PARSED``, or ``STAGE_ANALYZED``.

        - ``STAGE_IDLE``     — full reset; all keys restored to defaults.
        - ``STAGE_PARSED``   — clears JD, analysis, scoring, and output data;
                               preserves ``resume_raw_text`` and
                               ``resume_profile``; sets
                               ``pipeline_stage = STAGE_PARSED``.
        - ``STAGE_ANALYZED`` — clears only tailored resume, score, and PDF;
                               sets ``pipeline_stage = STAGE_ANALYZED``.

    Returns
    -------
    None

    Raises
    ------
    ValueError
        If *from_stage* is not one of the recognised stage constants.
    """
    if from_stage not in _VALID_STAGES:
        raise ValueError(
            f"Unknown pipeline stage {from_stage!r}.  "
            f"Valid stages are: {_VALID_STAGES}"
        )

    if from_stage == STAGE_IDLE:
        _apply_defaults(_RESET_FROM_IDLE)
        logger.info("session_state.reset_downstream | full reset to IDLE")

    elif from_stage == STAGE_PARSED:
        _clear_keys(_RESET_FROM_PARSED)
        st.session_state["pipeline_stage"] = STAGE_PARSED
        logger.info(
            "session_state.reset_downstream | downstream of PARSED cleared"
        )

    elif from_stage == STAGE_ANALYZED:
        _clear_keys(_RESET_FROM_ANALYZED)
        st.session_state["pipeline_stage"] = STAGE_ANALYZED
        logger.info(
            "session_state.reset_downstream | downstream of ANALYZED cleared"
        )

    # STAGE_COMPLETE has no downstream keys to clear — nothing to do.


# ---------------------------------------------------------------------------
# Typed accessor helpers
# ---------------------------------------------------------------------------

def get_pipeline_stage() -> str:
    """Return the current pipeline stage string."""
    return st.session_state.get("pipeline_stage", STAGE_IDLE)


def set_pipeline_stage(stage: str) -> None:
    """
    Advance the pipeline to *stage*.

    Parameters
    ----------
    stage : str
        One of the ``STAGE_*`` constants.

    Raises
    ------
    ValueError
        If *stage* is not a recognised stage constant.
    """
    if stage not in _VALID_STAGES:
        raise ValueError(
            f"Unknown pipeline stage {stage!r}.  "
            f"Valid stages are: {_VALID_STAGES}"
        )
    st.session_state["pipeline_stage"] = stage


def get_resume_raw_text() -> Optional[str]:
    """Return the cleaned resume text, or ``None`` if not yet extracted."""
    return st.session_state.get("resume_raw_text")


def set_resume_raw_text(text: str) -> None:
    """Store the cleaned resume text extracted from the uploaded PDF."""
    st.session_state["resume_raw_text"] = text


def get_resume_profile() -> "Optional[ResumeProfile]":
    """Return the parsed ``ResumeProfile``, or ``None`` if Agent 1 has not run."""
    return st.session_state.get("resume_profile")


def set_resume_profile(profile: "ResumeProfile") -> None:
    """Store the ``ResumeProfile`` output from Agent 1."""
    st.session_state["resume_profile"] = profile


def get_job_description() -> "Optional[JobDescription]":
    """Return the parsed ``JobDescription``, or ``None`` if Agent 2 has not run."""
    return st.session_state.get("job_description")


def set_job_description(jd: "JobDescription") -> None:
    """Store the ``JobDescription`` output from Agent 2."""
    st.session_state["job_description"] = jd


def get_skill_gap_report() -> "Optional[SkillGapAnalysis]":
    """Return the ``SkillGapAnalysis``, or ``None`` if Agent 3 has not run."""
    return st.session_state.get("skill_gap_report")


def set_skill_gap_report(report: "SkillGapAnalysis") -> None:
    """Store the ``SkillGapAnalysis`` output from Agent 3."""
    st.session_state["skill_gap_report"] = report


def get_ats_report() -> "Optional[ATSScore]":
    """Return the ``ATSScore``, or ``None`` if Agent 4 has not run."""
    return st.session_state.get("ats_report")


def set_ats_report(report: "ATSScore") -> None:
    """Store the ``ATSScore`` output from Agent 4."""
    st.session_state["ats_report"] = report


def get_tailored_resume() -> "Optional[TailoredResume]":
    """Return the ``TailoredResume``, or ``None`` if Agent 5 has not run."""
    return st.session_state.get("tailored_resume")


def set_tailored_resume(resume: "TailoredResume") -> None:
    """Store the ``TailoredResume`` output from Agent 5."""
    st.session_state["tailored_resume"] = resume


def get_match_score() -> Optional[float]:
    """Return the deterministic ATS match score (0.0–100.0), or ``None``."""
    return st.session_state.get("match_score")


def set_match_score(score: float) -> None:
    """Store the match score computed by ``core.scorer``."""
    st.session_state["match_score"] = score


def get_pdf_bytes() -> Optional[bytes]:
    """Return the generated tailored-resume PDF bytes, or ``None``."""
    return st.session_state.get("pdf_bytes")


def set_pdf_bytes(data: bytes) -> None:
    """Store the PDF bytes generated by ``core.pdf_generator``."""
    st.session_state["pdf_bytes"] = data


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _apply_defaults(keys: tuple[str, ...]) -> None:
    """
    Reset *keys* to their values from ``_DEFAULTS``.

    Parameters
    ----------
    keys : tuple[str, ...]
        Subset of ``_DEFAULTS`` keys to reset.
    """
    for key in keys:
        st.session_state[key] = _DEFAULTS[key]


def _clear_keys(keys: tuple[str, ...]) -> None:
    """
    Set *keys* to ``None`` (or their ``_DEFAULTS`` value if not ``None``).

    Parameters
    ----------
    keys : tuple[str, ...]
        Session-state keys to clear.
    """
    for key in keys:
        st.session_state[key] = _DEFAULTS.get(key)
