"""
core/pipeline.py

End-to-end AgentHireAI orchestration pipeline.

This module is the single entry-point that runs all five agents plus the
deterministic scorer and PDF generator in the correct order, managing
session state transitions and propagating errors with structured context.

Pipeline stages and transitions
---------------------------------
::

    IDLE
     │  run_resume_parsing(pdf_bytes, jd_text)
     ▼
    PARSED          ← resume_profile stored in session state
     │  run_analysis()
     ▼
    ANALYZED        ← job_description, skill_gap_report, ats_report stored
     │  run_tailoring()
     ▼
    COMPLETE        ← tailored_resume, match_score, pdf_bytes stored

Each stage function is independently callable so the Streamlit UI can run
them progressively (e.g. show the parsed resume preview before starting
the analysis phase).

Architecture
------------
- **No UI code** — zero Streamlit component imports.
- **No direct IBM API calls** — all LLM work is delegated to the agents.
- **Session state as shared memory** — all outputs are persisted via
  ``core.session_state`` accessors so the UI can read them at any time.
- **Structured error propagation** — every public function returns a
  :class:`PipelineResult` that carries either the outputs or a typed error,
  so the caller never needs to handle raw exceptions from internals.

Usage
-----
.. code-block:: python

    from core.pipeline import run_resume_parsing, run_analysis, run_tailoring
    from core.pipeline import run_full_pipeline, PipelineResult

    # Progressive (used by Streamlit pages)
    result = run_resume_parsing(pdf_bytes=uploaded_bytes, jd_text=pasted_jd)
    if result.success:
        result = run_analysis()
    if result.success:
        result = run_tailoring()

    # Single-shot (used for batch / API / testing)
    result = run_full_pipeline(pdf_bytes=uploaded_bytes, jd_text=pasted_jd)
    if result.success:
        print(result.outputs["total_score"])
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Optional

import core.session_state as ss
from agents import ats_optimizer, jd_analyzer, resume_parser, resume_tailor
from agents import skill_gap_analyzer
from core.pdf_generator import generate_pdf
from core.pdf_reader import extract_text_from_pdf
from core.scorer import ScoreResult, calculate_score
from models.analysis import ATSScore, SkillGapAnalysis, TailoredResume
from models.job_description import JobDescription
from models.resume import ResumeProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PipelineResult — structured return container
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """
    Structured result returned by every public pipeline function.

    Attributes
    ----------
    success : bool
        ``True`` if the stage completed without error.
    stage : str
        The pipeline stage that was attempted (e.g. ``"PARSED"``).
    outputs : dict[str, Any]
        Named outputs produced in this stage.  Keys vary per stage (see
        individual function docstrings).  Empty dict on failure.
    error : str or None
        Human-readable error message if ``success`` is ``False``.
    error_type : str or None
        The exception class name (e.g. ``"ValueError"``) for the UI to
        categorise errors.
    elapsed_seconds : float
        Wall-clock seconds the stage took to complete.
    """

    success: bool
    stage: str
    outputs: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_type: Optional[str] = None
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Public pipeline functions
# ---------------------------------------------------------------------------


def run_resume_parsing(
    pdf_bytes: bytes,
    jd_text: str,
) -> PipelineResult:
    """
    Stage 1 — Parse the resume PDF and store the result in session state.

    Runs:
    - ``core.pdf_reader.extract_text_from_pdf`` → ``resume_raw_text``
    - ``agents.resume_parser.run`` → ``resume_profile``

    On success the pipeline stage is advanced to ``STAGE_PARSED``.

    Parameters
    ----------
    pdf_bytes : bytes
        Raw bytes of the uploaded PDF resume.
    jd_text : str
        The raw job description text (stored for later stages but not parsed
        here — the user may edit it before confirming).

    Returns
    -------
    PipelineResult
        On success:
            ``outputs["resume_raw_text"]`` — cleaned resume text.
            ``outputs["resume_profile"]``  — validated :class:`~models.resume.ResumeProfile`.
        On failure:
            ``error`` contains a human-readable description of what went wrong.
    """
    t0 = time.perf_counter()
    logger.info("pipeline.run_resume_parsing | starting")

    try:
        # Validate inputs
        if not pdf_bytes:
            raise ValueError("PDF bytes are empty — please upload a valid resume PDF.")
        if not jd_text or not jd_text.strip():
            raise ValueError(
                "Job description text is empty — please paste the job posting."
            )

        # Extract text from PDF
        from config.settings import settings

        max_bytes = settings.pdf_max_size_mb * 1024 * 1024
        resume_raw_text: str = extract_text_from_pdf(
            pdf_bytes, max_size_bytes=max_bytes
        )
        logger.info(
            "pipeline.run_resume_parsing | PDF extracted | chars=%d",
            len(resume_raw_text),
        )

        # Parse resume into structured model
        resume_profile: ResumeProfile = resume_parser.run(resume_raw_text)

        # Persist in session state
        ss.set_resume_raw_text(resume_raw_text)
        ss.set_resume_profile(resume_profile)
        # Store raw JD text so it's available when run_analysis() is called
        # We use the raw session key because there is no set_jd_text helper
        import streamlit as st  # noqa: PLC0415
        st.session_state["_jd_text_pending"] = jd_text

        ss.set_pipeline_stage(ss.STAGE_PARSED)

        elapsed = time.perf_counter() - t0
        logger.info(
            "pipeline.run_resume_parsing | complete | "
            "name=%r | elapsed=%.2fs",
            resume_profile.personal_info.full_name,
            elapsed,
        )

        return PipelineResult(
            success=True,
            stage=ss.STAGE_PARSED,
            outputs={
                "resume_raw_text": resume_raw_text,
                "resume_profile": resume_profile,
            },
            elapsed_seconds=elapsed,
        )

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.error(
            "pipeline.run_resume_parsing | failed | %s: %s",
            type(exc).__name__,
            exc,
        )
        return PipelineResult(
            success=False,
            stage=ss.STAGE_IDLE,
            error=_format_error(exc),
            error_type=type(exc).__name__,
            elapsed_seconds=elapsed,
        )


def run_analysis(
    jd_text: Optional[str] = None,
) -> PipelineResult:
    """
    Stage 2 — Analyze the JD and compute the skill gap and ATS report.

    Requires ``run_resume_parsing`` to have completed successfully.

    Runs (in order):
    - ``agents.jd_analyzer.run``         → ``job_description``
    - ``agents.skill_gap_analyzer.run``  → ``skill_gap_report``
    - ``agents.ats_optimizer.run``       → ``ats_report``

    On success the pipeline stage is advanced to ``STAGE_ANALYZED``.

    Parameters
    ----------
    jd_text : str, optional
        Raw job description text.  If ``None``, the value stored during
        ``run_resume_parsing`` is used.  Pass an explicit value to re-run
        analysis with a different JD without re-parsing the resume.

    Returns
    -------
    PipelineResult
        On success:
            ``outputs["job_description"]``  — validated :class:`~models.job_description.JobDescription`.
            ``outputs["skill_gap_report"]`` — validated :class:`~models.analysis.SkillGapAnalysis`.
            ``outputs["ats_report"]``       — validated :class:`~models.analysis.ATSScore`.
        On failure:
            ``error`` contains a human-readable description.
    """
    t0 = time.perf_counter()
    logger.info("pipeline.run_analysis | starting")

    try:
        import streamlit as st  # noqa: PLC0415

        # Retrieve resume profile from session state
        resume_profile: Optional[ResumeProfile] = ss.get_resume_profile()
        if resume_profile is None:
            raise ValueError(
                "Resume has not been parsed yet.  "
                "Call run_resume_parsing() before run_analysis()."
            )

        # Resolve JD text
        resolved_jd_text: str = (
            jd_text
            or st.session_state.get("_jd_text_pending", "")
        )
        if not resolved_jd_text or not resolved_jd_text.strip():
            raise ValueError(
                "Job description text is empty.  "
                "Provide jd_text or call run_resume_parsing() first."
            )

        # Agent 2 — JD Analyzer
        job_description: JobDescription = jd_analyzer.run(resolved_jd_text)
        ss.set_job_description(job_description)
        logger.info(
            "pipeline.run_analysis | JD analyzed | role=%r | required_skills=%d",
            job_description.role_title,
            len(job_description.required_skills),
        )

        # Agent 3 — Skill Gap Analyzer
        skill_gap: SkillGapAnalysis = skill_gap_analyzer.run(
            resume_profile=resume_profile,
            job_description=job_description,
        )
        ss.set_skill_gap_report(skill_gap)
        logger.info(
            "pipeline.run_analysis | skill gap complete | "
            "matched=%d | missing_critical=%d | match_pct=%s",
            len(skill_gap.matched_skills),
            len(skill_gap.missing_critical),
            skill_gap.match_percentage,
        )

        # Agent 4 — ATS Keyword Optimizer
        ats_report: ATSScore = ats_optimizer.run(
            resume_profile=resume_profile,
            job_description=job_description,
            skill_gap=skill_gap,
        )
        ss.set_ats_report(ats_report)
        logger.info(
            "pipeline.run_analysis | ATS report complete | "
            "keywords=%d | overall_ats=%s",
            len(ats_report.priority_keywords),
            ats_report.overall_ats_score,
        )

        ss.set_pipeline_stage(ss.STAGE_ANALYZED)

        elapsed = time.perf_counter() - t0
        logger.info(
            "pipeline.run_analysis | complete | elapsed=%.2fs", elapsed
        )

        return PipelineResult(
            success=True,
            stage=ss.STAGE_ANALYZED,
            outputs={
                "job_description": job_description,
                "skill_gap_report": skill_gap,
                "ats_report": ats_report,
            },
            elapsed_seconds=elapsed,
        )

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.error(
            "pipeline.run_analysis | failed | %s: %s",
            type(exc).__name__,
            exc,
        )
        return PipelineResult(
            success=False,
            stage=ss.get_pipeline_stage(),
            error=_format_error(exc),
            error_type=type(exc).__name__,
            elapsed_seconds=elapsed,
        )


def run_tailoring() -> PipelineResult:
    """
    Stage 3 — Tailor the resume and generate the output PDF.

    Requires ``run_analysis`` to have completed successfully.

    Runs (in order):
    - ``agents.resume_tailor.run``       → ``tailored_resume``
    - ``core.scorer.calculate_score``    → ``score_result``
    - ``core.pdf_generator.generate_pdf``→ ``pdf_bytes``

    On success the pipeline stage is advanced to ``STAGE_COMPLETE``.

    Returns
    -------
    PipelineResult
        On success:
            ``outputs["tailored_resume"]`` — validated :class:`~models.analysis.TailoredResume`.
            ``outputs["score_result"]``    — :class:`~core.scorer.ScoreResult`.
            ``outputs["total_score"]``     — ``float`` total score (0–100).
            ``outputs["fit_label"]``       — ``str`` fit label.
            ``outputs["pdf_bytes"]``       — raw PDF ``bytes``.
        On failure:
            ``error`` contains a human-readable description.
    """
    t0 = time.perf_counter()
    logger.info("pipeline.run_tailoring | starting")

    try:
        # Retrieve all required data from session state
        resume_profile: Optional[ResumeProfile] = ss.get_resume_profile()
        job_description: Optional[JobDescription] = ss.get_job_description()
        skill_gap: Optional[SkillGapAnalysis] = ss.get_skill_gap_report()
        ats_report: Optional[ATSScore] = ss.get_ats_report()

        if resume_profile is None:
            raise ValueError("resume_profile is missing — run run_resume_parsing() first.")
        if job_description is None:
            raise ValueError("job_description is missing — run run_analysis() first.")
        if skill_gap is None:
            raise ValueError("skill_gap_report is missing — run run_analysis() first.")
        if ats_report is None:
            raise ValueError("ats_report is missing — run run_analysis() first.")

        # Agent 5 — Resume Tailor
        tailored: TailoredResume = resume_tailor.run(
            resume_profile=resume_profile,
            job_description=job_description,
            skill_gap=skill_gap,
            ats_report=ats_report,
        )
        ss.set_tailored_resume(tailored)
        logger.info(
            "pipeline.run_tailoring | resume tailored | "
            "experience_entries=%d | highlighted_skills=%d",
            len(tailored.rewritten_experience),
            len(tailored.highlighted_skills),
        )

        # Deterministic scorer — no LLM call
        score_result: ScoreResult = calculate_score(
            skill_gap=skill_gap,
            ats_report=ats_report,
            profile=resume_profile,
            jd=job_description,
        )
        ss.set_match_score(score_result.total_score)
        logger.info(
            "pipeline.run_tailoring | score calculated | "
            "total=%.1f | label=%r",
            score_result.total_score,
            score_result.fit_label,
        )

        # PDF Generator
        pdf_bytes: bytes = generate_pdf(
            tailored_resume=tailored,
            resume_profile=resume_profile,
            score_result=score_result,
            role_title=job_description.role_title,
        )
        ss.set_pdf_bytes(pdf_bytes)
        logger.info(
            "pipeline.run_tailoring | PDF generated | bytes=%d",
            len(pdf_bytes),
        )

        ss.set_pipeline_stage(ss.STAGE_COMPLETE)

        elapsed = time.perf_counter() - t0
        logger.info(
            "pipeline.run_tailoring | complete | elapsed=%.2fs", elapsed
        )

        return PipelineResult(
            success=True,
            stage=ss.STAGE_COMPLETE,
            outputs={
                "tailored_resume": tailored,
                "score_result": score_result,
                "total_score": score_result.total_score,
                "fit_label": score_result.fit_label,
                "pdf_bytes": pdf_bytes,
            },
            elapsed_seconds=elapsed,
        )

    except Exception as exc:
        elapsed = time.perf_counter() - t0
        logger.error(
            "pipeline.run_tailoring | failed | %s: %s",
            type(exc).__name__,
            exc,
        )
        return PipelineResult(
            success=False,
            stage=ss.get_pipeline_stage(),
            error=_format_error(exc),
            error_type=type(exc).__name__,
            elapsed_seconds=elapsed,
        )


def run_full_pipeline(
    pdf_bytes: bytes,
    jd_text: str,
) -> PipelineResult:
    """
    Execute all three pipeline stages in sequence and return the final result.

    Convenience function for single-shot execution (batch processing, API
    endpoints, integration tests).  Stops at the first failed stage and
    returns that stage's :class:`PipelineResult`.

    Parameters
    ----------
    pdf_bytes : bytes
        Raw bytes of the uploaded PDF resume.
    jd_text : str
        Raw job description text.

    Returns
    -------
    PipelineResult
        The result of the last stage that was attempted.  If all three
        stages succeed, this is the Stage 3 result (``stage="COMPLETE"``)
        which contains all outputs including ``pdf_bytes`` and
        ``score_result``.
    """
    t0 = time.perf_counter()
    logger.info("pipeline.run_full_pipeline | starting")

    # Stage 1
    result = run_resume_parsing(pdf_bytes=pdf_bytes, jd_text=jd_text)
    if not result.success:
        logger.error(
            "pipeline.run_full_pipeline | aborted at Stage 1 | %s",
            result.error,
        )
        return result

    # Stage 2
    result = run_analysis(jd_text=jd_text)
    if not result.success:
        logger.error(
            "pipeline.run_full_pipeline | aborted at Stage 2 | %s",
            result.error,
        )
        return result

    # Stage 3
    result = run_tailoring()
    if not result.success:
        logger.error(
            "pipeline.run_full_pipeline | aborted at Stage 3 | %s",
            result.error,
        )
        return result

    elapsed = time.perf_counter() - t0
    logger.info(
        "pipeline.run_full_pipeline | all stages complete | "
        "total_elapsed=%.2fs | score=%.1f",
        elapsed,
        result.outputs.get("total_score", 0.0),
    )

    # Patch elapsed to reflect full wall-clock time
    return PipelineResult(
        success=True,
        stage=ss.STAGE_COMPLETE,
        outputs=result.outputs,
        elapsed_seconds=elapsed,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _format_error(exc: Exception) -> str:
    """
    Format an exception into a concise, user-facing error string.

    Includes the exception type and message but not a full traceback
    (which would expose internals to end-users).  The full traceback is
    always written to the logger at ERROR level before this function is
    called.

    Parameters
    ----------
    exc : Exception
        The caught exception.

    Returns
    -------
    str
        Human-readable error message.
    """
    return f"{type(exc).__name__}: {exc}"
