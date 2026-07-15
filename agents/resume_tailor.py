"""
agents/resume_tailor.py

Agent 5 — Resume Tailor.

Responsibility
--------------
Rewrite a candidate's resume sections to be optimally aligned with a specific
job description, integrating ATS keywords naturally, strengthening bullet
points with achievement-oriented language, and improving the professional
summary — while strictly preserving factual accuracy and never inventing
experience.

The output is a validated :class:`~models.analysis.TailoredResume` containing
rewritten content ready to be passed to ``core.pdf_generator`` for PDF
rendering.

Content integrity guarantee
----------------------------
The prompt explicitly prohibits fabrication.  Every rewritten bullet must be
traceable to an original statement.  The agent is instructed to:

- Rephrase using stronger action verbs and quantify existing achievements.
- Embed ATS keywords from :class:`~models.analysis.ATSScore` *in context*,
  not as a keyword dump.
- Prioritise skills from ``skill_gap.matched_skills`` in the
  ``highlighted_skills`` list.
- Recommend certifications / courses in ``suggested_additions`` rather than
  pretending the candidate already holds them.

Pipeline position
-----------------
::

    ResumeProfile    ──┐
    JobDescription   ──┤
                       ├─→ **this module** (Agent 5) → TailoredResume
    SkillGapAnalysis ──┤                                  → core.pdf_generator
    ATSScore         ──┘                                  → core.scorer

Public API
----------
.. code-block:: python

    from agents.resume_tailor import run
    tailored: TailoredResume = run(
        resume_profile, job_description, skill_gap, ats_report
    )

Internal helpers (exported for unit-test access)
-------------------------------------------------
.. code-block:: python

    from agents.resume_tailor import (
        _build_prompt, _extract_json, _schema_json, _validate,
    )

Design note — ``rewritten_experience`` and token budget
--------------------------------------------------------
:class:`~models.analysis.TailoredResume` contains
``rewritten_experience: List[WorkExperience]``.  Each ``WorkExperience`` is a
nested Pydantic object.  To keep the prompt within token limits for long
resumes, experience is serialised as compact JSON and the generation model
(``settings.model_generation``) is used — which supports the higher
``settings.max_tokens_generation`` cap.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from config.settings import settings
from core.watsonx_client import watsonx_client
from models.analysis import ATSScore, SkillGapAnalysis, TailoredResume
from models.job_description import JobDescription
from models.resume import ResumeProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

# Agent 5 uses the generation model (higher token budget, higher temperature)
# because it is producing creative prose, not extracting structured data.
# The schema is still injected to guarantee a JSON output contract.

_PROMPT_TEMPLATE: str = """\
You are an expert professional resume writer and ATS optimisation specialist.

Your task is to rewrite the candidate's resume sections for the target job, \
producing a JSON object that exactly matches the provided schema.

Core principles — you MUST follow these without exception:
1. FACTUAL ACCURACY: Never invent, fabricate, or exaggerate experience, skills, \
   or qualifications. Only rewrite what already exists.
2. ATS OPTIMISATION: Integrate high-weight ATS keywords naturally into bullet \
   points and the summary. Do not keyword-stuff.
3. ACHIEVEMENT FOCUS: Rewrite bullets using strong action verbs. Quantify \
   achievements wherever the original text hints at scale or impact.
4. RELEVANCE FIRST: Prioritise responsibilities and skills most relevant to \
   the target role. Deprioritise unrelated content.
5. SUGGESTED ADDITIONS: Add certifications, courses, or projects the candidate \
   COULD pursue — clearly framed as suggestions, not claimed accomplishments.
6. TRUTHFULNESS: The tailoring_notes field must record any significant rewrites \
   so reviewers understand what changed.

Rewriting instructions:
- "rewritten_summary": A 3–5 sentence professional summary highlighting the \
  candidate's most relevant strengths for this specific role. Embed 2–3 \
  priority ATS keywords naturally.
- "rewritten_experience": For EACH role in the original experience list, \
  rewrite the bullet points to be achievement-focused and keyword-rich. \
  Keep title, company, start_date, end_date, and location unchanged.
- "highlighted_skills": A ranked list of the candidate's skills most relevant \
  to the target role, drawn from their actual skill set.
- "suggested_additions": 2–5 actionable suggestions (certifications, courses, \
  side projects) the candidate could pursue to strengthen their application.
- "tailoring_notes": 3–5 brief internal notes explaining key decisions made.

Rules:
- Return ONLY the JSON object — no markdown fences, no commentary, no extra keys.
- Use null for any optional field that cannot be determined.
- For list fields, return an empty array [] if there are no items.
- All experience entries must preserve the original title, company, \
  start_date, end_date, and location fields unchanged.
- Do NOT add skills to highlighted_skills that are not in the candidate's \
  actual skill set.

JSON Schema:
{schema}

--- Target Role ---
Title: {role_title}
Company: {company_name}
Seniority: {jd_seniority}
Employment Type: {employment_type}
Location: {jd_location}
Required Skills: {required_skills}
Preferred Skills: {preferred_skills}
Key Responsibilities: {responsibilities}
Company Signals: {company_signals}

--- Skill Gap Context ---
Matched Skills: {matched_skills}
Missing Critical: {missing_critical}
Missing Preferred: {missing_preferred}
Transferable Skills: {transferable_skills}
Gap Recommendations: {gap_recommendations}

--- ATS Keywords (ranked by weight) ---
Priority Keywords: {priority_keywords}
Phrases to Include: {phrases_to_include}
Phrases to Avoid: {phrases_to_avoid}

--- Candidate Current Resume ---
Name: {candidate_name}
Seniority: {seniority_level}
Total Years Experience: {total_years_experience}
Current Summary: {current_summary}
Current Skills: {current_skills}
Current Experience (JSON):
{current_experience}
Current Projects (JSON):
{current_projects}
Certifications: {certifications}
---

JSON output:"""

# Generation model + higher token cap for creative prose rewriting.
_GENERATION_PARAMS: dict[str, Any] = {
    "decoding_method": "greedy",
    "max_new_tokens": settings.max_tokens_generation,
    "min_new_tokens": 1,
    "temperature": settings.temperature_generation,
    "repetition_penalty": 1.1,
    "stop_sequences": [],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    resume_profile: ResumeProfile,
    job_description: JobDescription,
    skill_gap: SkillGapAnalysis,
    ats_report: ATSScore,
) -> TailoredResume:
    """
    Rewrite *resume_profile* sections to be optimally aligned with *job_description*.

    Uses a single Granite generation call with the full context from all
    upstream agents.  The response is validated against the
    :class:`~models.analysis.TailoredResume` schema before being returned.

    Parameters
    ----------
    resume_profile : ResumeProfile
        Validated output of Agent 1 (Resume Parser).
    job_description : JobDescription
        Validated output of Agent 2 (JD Analyzer).
    skill_gap : SkillGapAnalysis
        Validated output of Agent 3 (Skill Gap Analyzer).
    ats_report : ATSScore
        Validated output of Agent 4 (ATS Keyword Optimizer).

    Returns
    -------
    TailoredResume
        A fully validated Pydantic model containing rewritten resume sections
        optimised for the target job description.

    Raises
    ------
    ValueError
        If the LLM returns malformed JSON or a response that fails
        ``TailoredResume`` schema validation.
    RuntimeError
        Propagated from :data:`~core.watsonx_client.watsonx_client` when the
        IBM Watsonx API is unreachable or credentials are not configured.
    """
    schema: str = _schema_json()
    prompt: str = _build_prompt(
        schema=schema,
        resume_profile=resume_profile,
        job_description=job_description,
        skill_gap=skill_gap,
        ats_report=ats_report,
    )

    logger.info(
        "resume_tailor.run | starting generation | "
        "model=%s | role=%r | candidate=%r",
        settings.model_generation,
        job_description.role_title,
        resume_profile.personal_info.full_name,
    )

    raw_response: str = watsonx_client.generate(
        prompt=prompt,
        model_id=settings.model_generation,
        params=_GENERATION_PARAMS,
    )

    logger.debug(
        "Raw Watson response:\n%s",
        raw_response,
    )

    parsed_dict: dict[str, Any] = _extract_json(raw_response)
    tailored: TailoredResume = _validate(parsed_dict)

    logger.info(
        "resume_tailor.run | generation complete | "
        "experience_entries=%d | highlighted_skills=%d | "
        "suggestions=%d | notes=%d",
        len(tailored.rewritten_experience),
        len(tailored.highlighted_skills),
        len(tailored.suggested_additions),
        len(tailored.tailoring_notes),
    )

    return tailored


# ---------------------------------------------------------------------------
# Internal helpers  (exported so tests can import them directly)
# ---------------------------------------------------------------------------


def _build_prompt(
    schema: str,
    resume_profile: ResumeProfile,
    job_description: JobDescription,
    skill_gap: SkillGapAnalysis,
    ats_report: ATSScore,
) -> str:
    """
    Render the resume tailoring prompt with all runtime variables.

    Experience and projects are serialised as compact JSON arrays so that
    Granite receives the full structured context without ambiguity.  The
    priority keywords list is serialised as ``[{"keyword": ..., "weight": ...}]``
    — the ``present_in_resume`` flag is omitted to keep the prompt concise.

    Parameters
    ----------
    schema : str
        Compact JSON Schema string for :class:`~models.analysis.TailoredResume`.
    resume_profile : ResumeProfile
        Parsed candidate resume.
    job_description : JobDescription
        Parsed job description.
    skill_gap : SkillGapAnalysis
        Skill gap analysis from Agent 3.
    ats_report : ATSScore
        ATS keyword report from Agent 4.

    Returns
    -------
    str
        Fully rendered prompt string ready to send to Granite.
    """
    # Serialise experience compactly — only the fields Granite needs to
    # understand context and rewrite bullets.
    experience_json: str = json.dumps(
        [
            {
                "title": exp.title,
                "company": exp.company,
                "start_date": exp.start_date,
                "end_date": exp.end_date,
                "location": exp.location,
                "bullets": exp.bullets,
            }
            for exp in resume_profile.experience
        ],
        indent=2,
    )

    projects_json: str = json.dumps(
        [
            {
                "name": proj.name,
                "description": proj.description,
                "technologies": proj.technologies,
                "year": proj.year,
            }
            for proj in resume_profile.projects
        ],
        indent=2,
    )

    # Priority keywords: emit keyword + weight only (present_in_resume is
    # internal bookkeeping, not useful for the rewriting task).
    priority_kw_summary: list[dict[str, Any]] = [
        {"keyword": kw.keyword, "weight": round(kw.weight, 2)}
        for kw in ats_report.priority_keywords[:15]  # cap at 15 to save tokens
    ]

    certifications: list[str] = [cert.name for cert in resume_profile.certifications]

    return _PROMPT_TEMPLATE.format(
        schema=schema,
        # JD section
        role_title=job_description.role_title,
        company_name=job_description.company_name or "Not specified",
        jd_seniority=job_description.seniority_level or "Not specified",
        employment_type=job_description.employment_type or "Not specified",
        jd_location=job_description.location or "Not specified",
        required_skills=json.dumps(
            [rs.skill for rs in job_description.required_skills]
        ),
        preferred_skills=json.dumps(
            [ps.skill for ps in job_description.preferred_skills]
        ),
        responsibilities=json.dumps(job_description.responsibilities),
        company_signals=json.dumps(job_description.company_signals),
        # Skill gap section
        matched_skills=json.dumps(skill_gap.matched_skills),
        missing_critical=json.dumps(skill_gap.missing_critical),
        missing_preferred=json.dumps(skill_gap.missing_preferred),
        transferable_skills=json.dumps(skill_gap.transferable_skills),
        gap_recommendations=json.dumps(skill_gap.recommendations),
        # ATS section
        priority_keywords=json.dumps(priority_kw_summary),
        phrases_to_include=json.dumps(ats_report.phrases_to_include),
        phrases_to_avoid=json.dumps(ats_report.phrases_to_avoid),
        # Candidate section
        candidate_name=resume_profile.personal_info.full_name,
        seniority_level=resume_profile.seniority_level or "Not specified",
        total_years_experience=resume_profile.total_years_experience,
        current_summary=resume_profile.summary or "None provided",
        current_skills=json.dumps(resume_profile.skills),
        current_experience=experience_json,
        current_projects=projects_json,
        certifications=json.dumps(certifications),
    )


def _schema_json() -> str:
    """
    Return the compact JSON Schema for :class:`~models.analysis.TailoredResume`.

    Generated fresh from the Pydantic model on every call so that any model
    changes are automatically reflected in the prompt.

    Returns
    -------
    str
        Compact JSON Schema string.
    """
    return json.dumps(TailoredResume.model_json_schema(), separators=(",", ":"))


def _extract_json(raw: str) -> dict[str, Any]:
    """
    Extract and decode a JSON object from *raw* LLM output.

    Handles three common Granite response formats:

    1. **Plain JSON** — the model returned the object directly.
    2. **Fenced JSON** — wrapped in a markdown code block.
    3. **Prefixed JSON** — preamble text before the opening brace.

    Parameters
    ----------
    raw : str
        The raw string returned by ``watsonx_client.generate()``.

    Returns
    -------
    dict
        The decoded JSON object.

    Raises
    ------
    ValueError
        If no valid JSON object can be extracted from *raw*.
    """
    if not raw or not raw.strip():
        raise ValueError(
            "The LLM returned an empty response.  "
            "Cannot extract a JSON tailored resume."
        )

    text = raw.strip()

    # Strategy 1: strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(
        r"```(?:json)?\s*(\{.*?\})\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if fence_match:
        text = fence_match.group(1).strip()

    # Strategy 2: slice from first '{' to last '}' to handle preamble text.
    brace_start = text.find("{")
    brace_end = text.rfind("}")

    if brace_start == -1 or brace_end == -1 or brace_end <= brace_start:
        raise ValueError(
            f"No JSON object found in the LLM response.  "
            f"Raw response: {raw}"
        )

    candidate = text[brace_start : brace_end + 1]

    try:
        decoded: dict[str, Any] = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to decode JSON:\n{candidate}"
        ) from exc

    if not isinstance(decoded, dict):
        raise ValueError(
            f"Expected a JSON object (dict) but got {type(decoded).__name__}.  "
            f"Raw response: {raw}"
        )

    return decoded


def _validate(data: dict[str, Any]) -> TailoredResume:
    """
    Validate *data* against the :class:`~models.analysis.TailoredResume` schema.

    Parameters
    ----------
    data : dict
        Decoded JSON dict as returned by :func:`_extract_json`.

    Returns
    -------
    TailoredResume
        A fully validated Pydantic model instance.

    Raises
    ------
    ValueError
        Wraps :class:`pydantic.ValidationError` with a human-readable message
        that includes field-level error details.
    """
    try:
        return TailoredResume.model_validate(data)
    except ValidationError as exc:
        error_summary: str = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(
            f"LLM response failed TailoredResume validation — {error_summary}.  "
            f"Raw data keys: {list(data.keys())}"
        ) from exc
