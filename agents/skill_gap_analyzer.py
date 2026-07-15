"""
agents/skill_gap_analyzer.py

Agent 3 — Skill Gap Analyzer.

Responsibility
--------------
Compare a candidate's :class:`~models.resume.ResumeProfile` against a
:class:`~models.job_description.JobDescription` and produce a validated
:class:`~models.analysis.SkillGapAnalysis` that quantifies matched skills,
critical gaps, preferred gaps, transferable skills, and actionable
recommendations.

Hybrid matching strategy
------------------------
A two-phase approach maximises accuracy while minimising LLM calls:

**Phase 1 — Deterministic exact / near-exact matching** (no LLM)
    :func:`_exact_match` normalises both skill sets (lowercase, strip
    punctuation) and performs set intersection.  Handles ``"Python"`` ==
    ``"python"`` and ``"Node.js"`` == ``"nodejs"`` without any API call.

**Phase 2 — Granite fuzzy / semantic matching** (single LLM call)
    :func:`_fuzzy_match` sends *only the unmatched remainders* to Granite,
    asking it to identify semantically equivalent pairs (e.g.
    ``"Scikit-learn"`` ↔ ``"ML modelling"``, ``"React"`` ↔ ``"React.js"``).
    This keeps the prompt small and the API cost low.

**Phase 3 — Recommendations** (same LLM call)
    Granite generates concise, actionable recommendations from the combined
    gap information in a single prompt alongside the fuzzy-match request.

Pipeline position
-----------------
::

    ResumeProfile  ──┐
                     ├─→ **this module** (Agent 3)
    JobDescription ──┘      → SkillGapAnalysis
                                → Agent 4 (ATS Keyword Optimizer)
                                → Agent 5 (Resume Tailor)
                                → core.scorer

Public API
----------
.. code-block:: python

    from agents.skill_gap_analyzer import run
    gap: SkillGapAnalysis = run(resume_profile, job_description)

Internal helpers (exported for unit-test access)
-------------------------------------------------
.. code-block:: python

    from agents.skill_gap_analyzer import (
        _normalise, _exact_match, _fuzzy_match,
        _build_prompt, _extract_json, _schema_json, _validate,
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
from models.analysis import SkillGapAnalysis
from models.job_description import JobDescription
from models.resume import ResumeProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

# The prompt is self-contained here (config/prompts.py is still a stub).
# It is sent to Granite only for Phase 2 (fuzzy matching) + recommendations.
# The full SkillGapAnalysis schema is injected so Granite returns a
# validated-ready JSON object in one round-trip.

_PROMPT_TEMPLATE: str = """\
You are an expert technical recruiter and career advisor performing a \
skill-gap analysis.

You have already been given the results of deterministic exact matching \
(see below).  Your tasks are:

1. FUZZY MATCH: From the unmatched candidate skills, identify any that are \
semantically equivalent to, or a strong substitute for, a required or \
preferred JD skill that was NOT already matched.  Add these to \
"matched_skills" and remove them from the missing lists accordingly.

2. TRANSFERABLE SKILLS: Identify candidate skills that partially satisfy a \
JD requirement — e.g. "Pandas" is transferable toward "Data Manipulation", \
"Flask" is transferable toward "REST API development".  List them under \
"transferable_skills".

3. RECOMMENDATIONS: Write 3–5 concise, actionable recommendations to help \
the candidate close their gaps (e.g. certifications to pursue, technologies \
to learn).  Be specific and realistic.

4. MATCH PERCENTAGE: Estimate the overall skill match as a percentage (0–100) \
considering both required and preferred skill coverage after fuzzy matching.

Return a single JSON object matching the schema exactly.

Rules:
- Return ONLY the JSON object — no markdown fences, no commentary, no extra keys.
- Use null for any field that is absent or cannot be determined.
- For list fields, return an empty array [] if there are no items.
- Do NOT add skills to matched_skills that are not genuinely equivalent.
- Preserve the deterministically matched skills already listed below.

JSON Schema:
{schema}

--- Deterministic matching results ---
Candidate Skills (all, normalised): {candidate_skills}
Required Skills (JD): {required_skills}
Preferred Skills (JD): {preferred_skills}

Deterministically Matched (exact): {deterministic_matches}
Still Missing Critical (after exact match): {missing_critical}
Still Missing Preferred (after exact match): {missing_preferred}
Unmatched Candidate Skills: {unmatched_candidate}
---

JSON output:"""

# Parameters: same low-temperature deterministic profile as Agent 1 and 2,
# but slightly higher max tokens because recommendations add prose length.
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
) -> SkillGapAnalysis:
    """
    Analyze the skill gap between *resume_profile* and *job_description*.

    Combines deterministic set-matching with a single Granite LLM call for
    fuzzy / semantic matching and recommendation generation.

    Parameters
    ----------
    resume_profile : ResumeProfile
        Validated output of Agent 1 (Resume Parser).
    job_description : JobDescription
        Validated output of Agent 2 (JD Analyzer).

    Returns
    -------
    SkillGapAnalysis
        A fully validated Pydantic model containing matched skills, gaps,
        transferable skills, recommendations, and an estimated match
        percentage.

    Raises
    ------
    ValueError
        If the LLM returns malformed JSON or a response that fails
        ``SkillGapAnalysis`` schema validation.
    RuntimeError
        Propagated from :data:`~core.watsonx_client.watsonx_client` when the
        IBM Watsonx API is unreachable or credentials are not configured.
    """
    # ------------------------------------------------------------------
    # Phase 1: deterministic exact matching (no LLM call)
    # ------------------------------------------------------------------
    candidate_skills: list[str] = resume_profile.skills
    required_skills: list[str] = [rs.skill for rs in job_description.required_skills]
    preferred_skills: list[str] = [ps.skill for ps in job_description.preferred_skills]

    exact: dict[str, list[str]] = _exact_match(
        candidate_skills=candidate_skills,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
    )

    deterministic_matches: list[str] = exact["matched"]
    missing_critical_after_exact: list[str] = exact["missing_critical"]
    missing_preferred_after_exact: list[str] = exact["missing_preferred"]
    unmatched_candidate: list[str] = exact["unmatched_candidate"]

    logger.info(
        "skill_gap_analyzer.run | exact match complete | "
        "matched=%d | missing_critical=%d | missing_preferred=%d | "
        "unmatched_candidate=%d",
        len(deterministic_matches),
        len(missing_critical_after_exact),
        len(missing_preferred_after_exact),
        len(unmatched_candidate),
    )

    # ------------------------------------------------------------------
    # Phase 2 + 3: fuzzy matching + recommendations via Granite
    # ------------------------------------------------------------------
    schema: str = _schema_json()
    prompt: str = _build_prompt(
        schema=schema,
        candidate_skills=candidate_skills,
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        deterministic_matches=deterministic_matches,
        missing_critical=missing_critical_after_exact,
        missing_preferred=missing_preferred_after_exact,
        unmatched_candidate=unmatched_candidate,
    )

    logger.info(
        "skill_gap_analyzer.run | starting LLM call | model=%s",
        settings.model_extraction,
    )

    raw_response: str = watsonx_client.generate(
        prompt=prompt,
        model_id=settings.model_extraction,
        params=_EXTRACTION_PARAMS,
    )

    logger.debug(
        "skill_gap_analyzer.run | raw response received | chars=%d",
        len(raw_response),
    )

    parsed_dict: dict[str, Any] = _extract_json(raw_response)

    # ------------------------------------------------------------------
    # Guarantee deterministic matches are always present in matched_skills.
    # The LLM may return a superset (it added fuzzy matches) but it must
    # never drop the exact matches we already found.
    # ------------------------------------------------------------------
    llm_matched: list[str] = parsed_dict.get("matched_skills", [])
    llm_matched_normalised = {_normalise_single(s) for s in llm_matched}
    for skill in deterministic_matches:
        if _normalise_single(skill) not in llm_matched_normalised:
            llm_matched.append(skill)
            llm_matched_normalised.add(_normalise_single(skill))
    parsed_dict["matched_skills"] = llm_matched

    gap: SkillGapAnalysis = _validate(parsed_dict)

    logger.info(
        "skill_gap_analyzer.run | analysis complete | "
        "matched=%d | missing_critical=%d | missing_preferred=%d | "
        "transferable=%d | match_pct=%s",
        len(gap.matched_skills),
        len(gap.missing_critical),
        len(gap.missing_preferred),
        len(gap.transferable_skills),
        gap.match_percentage,
    )

    return gap


# ---------------------------------------------------------------------------
# Internal helpers  (exported so tests can import them directly)
# ---------------------------------------------------------------------------


def _normalise(skills: list[str]) -> list[str]:
    """
    Normalise a list of skill strings for case- and punctuation-insensitive
    comparison.

    Transformations applied to each skill:

    - Strip leading/trailing whitespace.
    - Lowercase.
    - Remove all punctuation characters (``string.punctuation``).
    - Collapse internal whitespace runs to a single space.

    Parameters
    ----------
    skills : list[str]
        Raw skill strings.

    Returns
    -------
    list[str]
        Normalised skill strings, one per input element (order preserved).
    """
    return [_normalise_single(s) for s in skills]


def _normalise_single(skill: str) -> str:
    """
    Apply the normalisation pipeline to a single skill string.

    Parameters
    ----------
    skill : str
        A single raw skill string.

    Returns
    -------
    str
        Normalised skill string.
    """
    s = skill.strip().lower()
    # Remove all punctuation (handles "Node.js" → "nodejs", "C++" → "c")
    s = s.translate(str.maketrans("", "", string.punctuation))
    # Collapse internal whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _exact_match(
    candidate_skills: list[str],
    required_skills: list[str],
    preferred_skills: list[str],
) -> dict[str, list[str]]:
    """
    Perform deterministic exact / near-exact skill matching.

    Uses :func:`_normalise_single` on all skill strings so that differences
    in casing, punctuation, and whitespace do not produce false negatives.
    ``"Python"`` matches ``"python"``, ``"Node.js"`` matches ``"Nodejs"``,
    ``"REST APIs"`` matches ``"rest apis"``.

    Parameters
    ----------
    candidate_skills : list[str]
        Skills extracted from the candidate's resume.
    required_skills : list[str]
        Must-have skills from the job description.
    preferred_skills : list[str]
        Nice-to-have skills from the job description.

    Returns
    -------
    dict with keys:
        ``"matched"`` — skills present in both candidate and JD (required or preferred).
        ``"missing_critical"`` — required skills absent from candidate.
        ``"missing_preferred"`` — preferred skills absent from candidate.
        ``"unmatched_candidate"`` — candidate skills that matched nothing in the JD.
    """
    # Build normalised → original lookup for candidate skills
    cand_norm_map: dict[str, str] = {
        _normalise_single(s): s for s in candidate_skills
    }
    cand_norm_set: set[str] = set(cand_norm_map.keys())

    # Normalise JD skill lists
    req_norm: list[str] = [_normalise_single(s) for s in required_skills]
    pref_norm: list[str] = [_normalise_single(s) for s in preferred_skills]

    # Determine which required / preferred skills are satisfied
    matched_set: set[str] = set()  # normalised candidate skills that matched anything
    matched_originals: list[str] = []

    missing_critical: list[str] = []
    for norm, orig in zip(req_norm, required_skills):
        if norm in cand_norm_set:
            # Use the candidate's original spelling in the output
            matched_originals.append(cand_norm_map[norm])
            matched_set.add(norm)
        else:
            missing_critical.append(orig)

    missing_preferred: list[str] = []
    for norm, orig in zip(pref_norm, preferred_skills):
        if norm in cand_norm_set:
            if norm not in matched_set:  # avoid double-counting
                matched_originals.append(cand_norm_map[norm])
                matched_set.add(norm)
        else:
            missing_preferred.append(orig)

    # Candidate skills that didn't match any JD requirement
    unmatched_candidate: list[str] = [
        cand_norm_map[norm]
        for norm in cand_norm_set
        if norm not in matched_set
    ]

    return {
        "matched": matched_originals,
        "missing_critical": missing_critical,
        "missing_preferred": missing_preferred,
        "unmatched_candidate": unmatched_candidate,
    }


def _build_prompt(
    schema: str,
    candidate_skills: list[str],
    required_skills: list[str],
    preferred_skills: list[str],
    deterministic_matches: list[str],
    missing_critical: list[str],
    missing_preferred: list[str],
    unmatched_candidate: list[str],
) -> str:
    """
    Render the skill-gap analysis prompt with all runtime variables.

    Parameters
    ----------
    schema : str
        Compact JSON Schema string for :class:`~models.analysis.SkillGapAnalysis`.
    candidate_skills : list[str]
        Full list of candidate skills (for context).
    required_skills : list[str]
        Full list of required JD skills (for context).
    preferred_skills : list[str]
        Full list of preferred JD skills (for context).
    deterministic_matches : list[str]
        Skills already matched in Phase 1.
    missing_critical : list[str]
        Required skills not yet matched.
    missing_preferred : list[str]
        Preferred skills not yet matched.
    unmatched_candidate : list[str]
        Candidate skills that didn't match anything in Phase 1.

    Returns
    -------
    str
        Fully rendered prompt string ready to send to Granite.
    """
    return _PROMPT_TEMPLATE.format(
        schema=schema,
        candidate_skills=json.dumps(candidate_skills),
        required_skills=json.dumps(required_skills),
        preferred_skills=json.dumps(preferred_skills),
        deterministic_matches=json.dumps(deterministic_matches),
        missing_critical=json.dumps(missing_critical),
        missing_preferred=json.dumps(missing_preferred),
        unmatched_candidate=json.dumps(unmatched_candidate),
    )


def _schema_json() -> str:
    """
    Return the compact JSON Schema for :class:`~models.analysis.SkillGapAnalysis`.

    Generated fresh from the Pydantic model on every call so that schema
    changes are automatically reflected in the prompt.

    Returns
    -------
    str
        Compact JSON Schema string.
    """
    return json.dumps(SkillGapAnalysis.model_json_schema(), separators=(",", ":"))


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
            "Cannot extract a JSON skill gap analysis."
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


def _validate(data: dict[str, Any]) -> SkillGapAnalysis:
    """
    Validate *data* against the :class:`~models.analysis.SkillGapAnalysis` schema.

    Parameters
    ----------
    data : dict
        Decoded JSON dict as returned by :func:`_extract_json`.

    Returns
    -------
    SkillGapAnalysis
        A fully validated Pydantic model instance.

    Raises
    ------
    ValueError
        Wraps :class:`pydantic.ValidationError` with a human-readable message
        that includes field-level error details.
    """
    try:
        return SkillGapAnalysis.model_validate(data)
    except ValidationError as exc:
        error_summary: str = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(
            f"LLM response failed SkillGapAnalysis validation — {error_summary}.  "
            f"Raw data keys: {list(data.keys())}"
        ) from exc
