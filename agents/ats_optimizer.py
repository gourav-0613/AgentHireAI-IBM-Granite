"""
agents/ats_optimizer.py

Agent 4 — ATS Keyword Optimizer.

Responsibility
--------------
Analyse keyword coverage between a candidate's
:class:`~models.resume.ResumeProfile` and a
:class:`~models.job_description.JobDescription`, enriched with the
:class:`~models.analysis.SkillGapAnalysis` from Agent 3, and produce a
validated :class:`~models.analysis.ATSScore` that ranks ATS-critical
keywords by importance, flags their presence in the resume, recommends
phrases to include or avoid, and estimates current and projected ATS
pass-through scores.

Pipeline position
-----------------
::

    ResumeProfile    ──┐
    JobDescription   ──┼─→ **this module** (Agent 4)
    SkillGapAnalysis ──┘      → ATSScore
                                  → Agent 5 (Resume Tailor)
                                  → core.scorer

Design note — ``present_in_resume`` flags
------------------------------------------
Each :class:`~models.analysis.KeywordWeight` entry carries a
``present_in_resume`` boolean.  Rather than asking Granite to determine
this (which risks hallucination), :func:`run` performs a deterministic
post-processing step: after the LLM response is parsed, every keyword is
checked against the candidate's normalised full-text corpus (skills list +
all experience bullet text + summary).  This guarantees the flag is always
accurate regardless of LLM behaviour.

Public API
----------
.. code-block:: python

    from agents.ats_optimizer import run
    ats: ATSScore = run(resume_profile, job_description, skill_gap)

Internal helpers (exported for unit-test access)
-------------------------------------------------
.. code-block:: python

    from agents.ats_optimizer import (
        _build_prompt, _extract_json, _schema_json, _validate,
        _build_resume_corpus, _flag_keywords,
    )
"""

from __future__ import annotations

import json
import logging
import re
import string
from typing import Any

from pydantic import ValidationError

from config.settings import settings
from core.watsonx_client import watsonx_client
from models.analysis import ATSScore, KeywordWeight, SkillGapAnalysis
from models.job_description import JobDescription
from models.resume import ResumeProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

# The template is self-contained here because config/prompts.py is currently
# a stub with empty strings (to be filled in a later step).  The schema
# placeholder is injected at call time from ATSScore.model_json_schema().

_PROMPT_TEMPLATE: str = """\
You are an expert ATS (Applicant Tracking System) optimisation specialist.

Your task is to analyse the job description and candidate profile below and \
produce a structured ATS keyword report that exactly matches the provided \
JSON Schema.

Instructions:
1. PRIORITY KEYWORDS: Extract 10–20 of the most ATS-critical keywords and \
keyphrases from the job description. For each keyword:
   - "keyword": the exact term or short phrase (e.g. "Apache Spark", "CI/CD").
   - "weight": a relevance score from 0.0 to 1.0, where 1.0 = absolutely \
critical, 0.5 = moderately important, 0.1 = minor signal.  Base weight on \
frequency, position in the JD (title/requirements = high), and industry \
ATS scanning patterns.
   - "present_in_resume": set to false for ALL keywords — the system will \
determine presence deterministically after your response.

2. PHRASES TO INCLUDE: List 5–10 exact phrases, acronyms, or industry-standard \
terms that ATS parsers specifically scan for and that should be added to the \
resume if not already present (e.g. "data pipeline", "ETL", "REST API").

3. PHRASES TO AVOID: List 3–8 overused buzzwords, clichés, or phrases that \
modern ATS systems and recruiters penalise (e.g. "synergy", "rockstar", \
"ninja", "thought leader", "go-getter").

4. OVERALL ATS SCORE: Estimate the candidate's current ATS pass-through score \
as a percentage (0–100) based on keyword coverage between their current skills \
and the JD requirements.

5. OPTIMISED ATS SCORE: Estimate the projected ATS pass-through score (0–100) \
if the candidate incorporates all recommended phrases and addresses the gaps.

Rules:
- Return ONLY the JSON object — no markdown fences, no commentary, no extra keys.
- Use null for any optional field that cannot be determined.
- For list fields, return an empty array [] if there are no items.
- Set "present_in_resume" to false for every keyword — the pipeline handles this.
- Weight values must be between 0.0 and 1.0 inclusive.
- Scores must be between 0.0 and 100.0 inclusive.

JSON Schema:
{schema}

--- Candidate Profile ---
Name: {candidate_name}
Current Skills: {candidate_skills}
Matched Skills (already found in JD): {matched_skills}
Missing Critical Skills: {missing_critical}
Missing Preferred Skills: {missing_preferred}
Transferable Skills: {transferable_skills}
Total Years Experience: {total_years_experience}
Seniority Level: {seniority_level}

--- Job Description ---
Role: {role_title}
Company: {company_name}
Seniority: {jd_seniority}

Required Skills: {required_skills}
Preferred Skills: {preferred_skills}
Responsibilities: {responsibilities}
Company Signals: {company_signals}
---

JSON output:"""

# Low temperature + greedy decoding for deterministic structured extraction.
_EXTRACTION_PARAMS: dict[str, Any] = {
    "decoding_method": "greedy",
    "max_new_tokens": settings.max_tokens_extraction,
    "min_new_tokens": 1,
    "temperature": settings.temperature_extraction,
    "repetition_penalty": 1.05,
    "stop_sequences": [],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run(
    resume_profile: ResumeProfile,
    job_description: JobDescription,
    skill_gap: SkillGapAnalysis,
) -> ATSScore:
    """
    Produce an ATS keyword optimisation report for a (resume, JD) pair.

    Makes a single Granite LLM call to extract and rank ATS-critical keywords,
    generate phrase recommendations, and estimate ATS pass-through scores.
    After the LLM response is validated, a deterministic post-processing step
    sets each keyword's ``present_in_resume`` flag by scanning the candidate's
    full-text corpus — ensuring accuracy regardless of LLM behaviour.

    Parameters
    ----------
    resume_profile : ResumeProfile
        Validated output of Agent 1 (Resume Parser).
    job_description : JobDescription
        Validated output of Agent 2 (JD Analyzer).
    skill_gap : SkillGapAnalysis
        Validated output of Agent 3 (Skill Gap Analyzer).

    Returns
    -------
    ATSScore
        A fully validated Pydantic model containing prioritised keywords
        with presence flags, phrases to include/avoid, and ATS score
        estimates.

    Raises
    ------
    ValueError
        If the LLM returns malformed JSON or a response that fails
        ``ATSScore`` schema validation.
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
    )

    logger.info(
        "ats_optimizer.run | starting extraction | "
        "model=%s | role=%r | candidate=%r",
        settings.model_extraction,
        job_description.role_title,
        resume_profile.personal_info.full_name,
    )

    raw_response: str = watsonx_client.generate(
        prompt=prompt,
        model_id=settings.model_extraction,
        params=_EXTRACTION_PARAMS,
    )

    logger.debug(
        "ats_optimizer.run | raw response received | chars=%d",
        len(raw_response),
    )

    parsed_dict: dict[str, Any] = _extract_json(raw_response)

    # Deterministically set present_in_resume on every keyword.
    # This overrides whatever the LLM set (instruction says false for all),
    # guaranteeing correctness regardless of model behaviour.
    corpus: str = _build_resume_corpus(resume_profile)
    parsed_dict = _flag_keywords(parsed_dict, corpus)

    ats: ATSScore = _validate(parsed_dict)

    present_count = sum(
        1 for kw in ats.priority_keywords if kw.present_in_resume
    )
    logger.info(
        "ats_optimizer.run | extraction complete | "
        "keywords=%d | present=%d | "
        "overall_ats=%s | optimised_ats=%s",
        len(ats.priority_keywords),
        present_count,
        ats.overall_ats_score,
        ats.optimised_ats_score,
    )

    return ats


# ---------------------------------------------------------------------------
# Internal helpers  (exported so tests can import them directly)
# ---------------------------------------------------------------------------


def _build_prompt(
    schema: str,
    resume_profile: ResumeProfile,
    job_description: JobDescription,
    skill_gap: SkillGapAnalysis,
) -> str:
    """
    Render the ATS optimisation prompt with all runtime variables.

    Parameters
    ----------
    schema : str
        Compact JSON Schema string for :class:`~models.analysis.ATSScore`.
    resume_profile : ResumeProfile
        Parsed candidate resume.
    job_description : JobDescription
        Parsed job description.
    skill_gap : SkillGapAnalysis
        Skill gap analysis result from Agent 3.

    Returns
    -------
    str
        Fully rendered prompt string ready to send to Granite.
    """
    return _PROMPT_TEMPLATE.format(
        schema=schema,
        # Candidate section
        candidate_name=resume_profile.personal_info.full_name,
        candidate_skills=json.dumps(resume_profile.skills),
        matched_skills=json.dumps(skill_gap.matched_skills),
        missing_critical=json.dumps(skill_gap.missing_critical),
        missing_preferred=json.dumps(skill_gap.missing_preferred),
        transferable_skills=json.dumps(skill_gap.transferable_skills),
        total_years_experience=resume_profile.total_years_experience,
        seniority_level=resume_profile.seniority_level,
        # JD section
        role_title=job_description.role_title,
        company_name=job_description.company_name,
        jd_seniority=job_description.seniority_level,
        required_skills=json.dumps(
            [rs.skill for rs in job_description.required_skills]
        ),
        preferred_skills=json.dumps(
            [ps.skill for ps in job_description.preferred_skills]
        ),
        responsibilities=json.dumps(job_description.responsibilities),
        company_signals=json.dumps(job_description.company_signals),
    )


def _schema_json() -> str:
    """
    Return the compact JSON Schema for :class:`~models.analysis.ATSScore`.

    Generated fresh from the Pydantic model on every call so that any model
    changes are automatically reflected in the prompt.

    Returns
    -------
    str
        Compact JSON Schema string.
    """
    return json.dumps(ATSScore.model_json_schema(), separators=(",", ":"))


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
            "Cannot extract a JSON ATS keyword report."
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
            f"Raw response (first 200 chars): {raw[:200]!r}"
        )

    candidate = text[brace_start : brace_end + 1]

    try:
        decoded: dict[str, Any] = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Failed to decode JSON from LLM response: {exc}.  "
            f"Extracted candidate (first 200 chars): {candidate[:200]!r}"
        ) from exc

    if not isinstance(decoded, dict):
        raise ValueError(
            f"Expected a JSON object (dict) but got {type(decoded).__name__}.  "
            f"Raw response (first 200 chars): {raw[:200]!r}"
        )

    return decoded


def _validate(data: dict[str, Any]) -> ATSScore:
    """
    Validate *data* against the :class:`~models.analysis.ATSScore` schema.

    Parameters
    ----------
    data : dict
        Decoded JSON dict as returned by :func:`_extract_json`, with
        ``present_in_resume`` flags already set by :func:`_flag_keywords`.

    Returns
    -------
    ATSScore
        A fully validated Pydantic model instance.

    Raises
    ------
    ValueError
        Wraps :class:`pydantic.ValidationError` with a human-readable message
        that includes field-level error details.
    """
    try:
        return ATSScore.model_validate(data)
    except ValidationError as exc:
        error_summary: str = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(
            f"LLM response failed ATSScore validation — {error_summary}.  "
            f"Raw data keys: {list(data.keys())}"
        ) from exc


def _build_resume_corpus(profile: ResumeProfile) -> str:
    """
    Build a single normalised text corpus from all searchable resume fields.

    The corpus is used by :func:`_flag_keywords` to determine whether each
    ATS keyword is already present in the candidate's resume.  It includes:

    - All skill strings from ``profile.skills``
    - Professional summary (if any)
    - All experience bullet points from every role
    - All job titles and company names
    - All project names, descriptions, and technology lists
    - All certification names

    Parameters
    ----------
    profile : ResumeProfile
        Parsed candidate resume.

    Returns
    -------
    str
        Lowercased, whitespace-collapsed corpus string.
    """
    parts: list[str] = []

    # Skills
    parts.extend(profile.skills)

    # Summary
    if profile.summary:
        parts.append(profile.summary)

    # Work experience — titles, companies, bullet text
    for exp in profile.experience:
        parts.append(exp.title)
        parts.append(exp.company)
        parts.extend(exp.bullets)

    # Projects — names, descriptions, technologies
    for proj in profile.projects:
        parts.append(proj.name)
        if proj.description:
            parts.append(proj.description)
        parts.extend(proj.technologies)

    # Certifications
    for cert in profile.certifications:
        parts.append(cert.name)

    # Education
    for edu in profile.education:
        parts.append(edu.degree)
        parts.append(edu.institution)

    return " ".join(parts).lower()


def _flag_keywords(
    data: dict[str, Any],
    corpus: str,
) -> dict[str, Any]:
    """
    Set ``present_in_resume`` on each keyword entry in *data* deterministically.

    For each keyword in ``data["priority_keywords"]``, normalises the keyword
    string (lowercase, strip punctuation) and checks whether it appears as a
    substring of *corpus* (which has been similarly normalised).  Sets
    ``present_in_resume`` to ``True`` if found, ``False`` otherwise.

    This step overrides whatever the LLM wrote for the flag, ensuring the
    value is always accurate regardless of model behaviour.

    Parameters
    ----------
    data : dict
        Decoded JSON dict from :func:`_extract_json`.  Modified in place and
        returned.
    corpus : str
        Normalised full-text resume corpus from :func:`_build_resume_corpus`.

    Returns
    -------
    dict
        The same *data* dict with ``present_in_resume`` fields updated.
    """
    # Normalise corpus: remove punctuation, collapse whitespace
    _punct_table = str.maketrans("", "", string.punctuation)
    norm_corpus = corpus.translate(_punct_table)
    norm_corpus = re.sub(r"\s+", " ", norm_corpus)

    keywords: list[Any] = data.get("priority_keywords", [])
    for kw in keywords:
        if isinstance(kw, dict):
            raw_kw: str = str(kw.get("keyword", ""))
        else:
            raw_kw = str(getattr(kw, "keyword", ""))

        # Normalise keyword the same way as the corpus
        norm_kw = raw_kw.lower().translate(_punct_table)
        norm_kw = re.sub(r"\s+", " ", norm_kw).strip()

        present = bool(norm_kw and norm_kw in norm_corpus)

        if isinstance(kw, dict):
            kw["present_in_resume"] = present

    return data
