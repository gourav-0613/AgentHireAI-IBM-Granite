"""
core/scorer.py

Deterministic ATS Match Score calculator.

The score is computed entirely in Python using five weighted signals derived
from the pipeline's Pydantic models.  **No LLM call is made.**  The same
inputs always produce the same output — this module is fully unit-testable
without mocking.

Score signals and weights
--------------------------

+------------------------+--------+------------------------------------------+
| Signal                 | Weight | Measure                                  |
+========================+========+==========================================+
| Required skill coverage|  50 %  | matched required / total required        |
+------------------------+--------+------------------------------------------+
| Experience match       |  20 %  | years experience vs JD min requirement   |
+------------------------+--------+------------------------------------------+
| Preferred skill        |  15 %  | matched preferred / total preferred      |
| coverage               |        |                                          |
+------------------------+--------+------------------------------------------+
| Keyword coverage       |  10 %  | weighted ATS keyword presence ratio      |
+------------------------+--------+------------------------------------------+
| Education match        |   5 %  | degree level aligned with JD seniority   |
+------------------------+--------+------------------------------------------+

Formula
-------
::

    total = round(
        (0.50 * s_required
       + 0.20 * s_experience
       + 0.15 * s_preferred
       + 0.10 * s_keywords
       + 0.05 * s_education) * 100,
        1
    )

Fit labels
----------
- **Strong Match**   — score ≥ 75
- **Good Match**     — 55 ≤ score < 75
- **Partial Match**  — 35 ≤ score < 55
- **Low Match**      — score < 35

Usage
-----
.. code-block:: python

    from core.scorer import calculate_score
    result = calculate_score(
        skill_gap=gap_analysis,
        ats_report=ats_score,
        profile=resume_profile,
        jd=job_description,
    )
    print(result.total_score)     # e.g. 74.5
    print(result.fit_label)       # e.g. "Good Match"
    print(result.breakdown)       # per-signal contribution dict for UI display
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from models.analysis import SkillGapAnalysis, ATSScore
from models.job_description import JobDescription
from models.resume import ResumeProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight constants  (must sum to 1.0)
# ---------------------------------------------------------------------------

_W_REQUIRED: float = 0.50   # required skill coverage
_W_EXPERIENCE: float = 0.20  # years experience alignment
_W_PREFERRED: float = 0.15  # preferred skill coverage
_W_KEYWORDS: float = 0.10   # ATS keyword weighted presence
_W_EDUCATION: float = 0.05  # education / degree level alignment

# Sanity-check at import time so a future weight edit is caught immediately.
assert abs((_W_REQUIRED + _W_EXPERIENCE + _W_PREFERRED + _W_KEYWORDS + _W_EDUCATION) - 1.0) < 1e-9, \
    "Scorer weights must sum to exactly 1.0"

# ---------------------------------------------------------------------------
# Fit label thresholds
# ---------------------------------------------------------------------------

_LABEL_STRONG: str = "Strong Match"   # ≥ 75
_LABEL_GOOD: str = "Good Match"       # ≥ 55
_LABEL_PARTIAL: str = "Partial Match" # ≥ 35
_LABEL_LOW: str = "Low Match"         # < 35


# ---------------------------------------------------------------------------
# ScoreResult — lightweight result container
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreResult:
    """
    Immutable result of a :func:`calculate_score` call.

    Attributes
    ----------
    total_score : float
        Weighted composite score in the range [0.0, 100.0], rounded to
        one decimal place.
    fit_label : str
        Human-readable fit tier: ``"Strong Match"``, ``"Good Match"``,
        ``"Partial Match"``, or ``"Low Match"``.
    required_signal : float
        Raw required-skill coverage signal in [0.0, 1.0].
    experience_signal : float
        Raw experience alignment signal in [0.0, 1.0].
    preferred_signal : float
        Raw preferred-skill coverage signal in [0.0, 1.0].
    keyword_signal : float
        Raw ATS keyword weighted-presence signal in [0.0, 1.0].
    education_signal : float
        Raw education alignment signal in [0.0, 1.0].
    breakdown : dict[str, float]
        Per-signal contributions to the total score (each value is the
        signal × weight × 100, rounded to one decimal place).  Suitable
        for rendering a score breakdown chart in the UI.
    """

    total_score: float
    fit_label: str
    required_signal: float
    experience_signal: float
    preferred_signal: float
    keyword_signal: float
    education_signal: float
    breakdown: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def calculate_score(
    skill_gap: SkillGapAnalysis,
    ats_report: ATSScore,
    profile: ResumeProfile,
    jd: JobDescription,
) -> ScoreResult:
    """
    Compute a deterministic weighted ATS match score for a (resume, JD) pair.

    All five signals are computed from the validated Pydantic models with no
    external calls.  Results are fully reproducible: identical inputs always
    produce identical outputs.

    Parameters
    ----------
    skill_gap : SkillGapAnalysis
        Output of Agent 3 — contains matched and missing skill lists.
    ats_report : ATSScore
        Output of Agent 4 — contains priority keywords with weights and
        presence flags.  Pass an empty ``ATSScore()`` if Agent 4 has not
        yet run (keyword signal will be 0.0).
    profile : ResumeProfile
        Validated resume profile from Agent 1.
    jd : JobDescription
        Validated job description from Agent 2.

    Returns
    -------
    ScoreResult
        Immutable result containing the total score, fit label, raw signals,
        and per-signal breakdown dict.
    """
    # ------------------------------------------------------------------
    # Signal 1 — Required skill coverage  (weight 50%)
    # ------------------------------------------------------------------
    # matched_skills holds skills found in both resume and JD (required + pref).
    # We measure coverage against the required set specifically.
    n_required: int = len(jd.required_skills)
    if n_required == 0:
        s_required = 1.0  # vacuously satisfied when no requirements exist
    else:
        # Count how many required skills are present in matched_skills
        required_names_norm = {
            _normalise(rs.skill) for rs in jd.required_skills
        }
        matched_norm = {_normalise(s) for s in skill_gap.matched_skills}
        n_matched_required = len(required_names_norm & matched_norm)
        s_required = n_matched_required / n_required

    # ------------------------------------------------------------------
    # Signal 2 — Experience match  (weight 20%)
    # ------------------------------------------------------------------
    s_experience = _experience_signal(
        candidate_years=profile.total_years_experience,
        experience_requirements=jd.experience_requirements,
    )

    # ------------------------------------------------------------------
    # Signal 3 — Preferred skill coverage  (weight 15%)
    # ------------------------------------------------------------------
    n_preferred: int = len(jd.preferred_skills)
    if n_preferred == 0:
        s_preferred = 1.0  # vacuously satisfied when no preferences exist
    else:
        preferred_names_norm = {
            _normalise(ps.skill) for ps in jd.preferred_skills
        }
        n_matched_preferred = len(preferred_names_norm & matched_norm)
        s_preferred = n_matched_preferred / n_preferred

    # ------------------------------------------------------------------
    # Signal 4 — ATS keyword coverage  (weight 10%)
    # ------------------------------------------------------------------
    s_keywords = _keyword_signal(ats_report)

    # ------------------------------------------------------------------
    # Signal 5 — Education alignment  (weight 5%)
    # ------------------------------------------------------------------
    s_education = _education_signal(
        profile=profile,
        jd_seniority=jd.seniority_level,
    )

    # ------------------------------------------------------------------
    # Weighted combination
    # ------------------------------------------------------------------
    raw = (
        _W_REQUIRED * s_required
        + _W_EXPERIENCE * s_experience
        + _W_PREFERRED * s_preferred
        + _W_KEYWORDS * s_keywords
        + _W_EDUCATION * s_education
    )

    # Clamp to [0.0, 1.0] before scaling (guards against floating-point drift)
    raw = max(0.0, min(1.0, raw))
    total_score = round(raw * 100, 1)
    fit_label = _fit_label(total_score)

    breakdown: dict[str, float] = {
        "Required Skills (50%)": round(_W_REQUIRED * s_required * 100, 1),
        "Experience Match (20%)": round(_W_EXPERIENCE * s_experience * 100, 1),
        "Preferred Skills (15%)": round(_W_PREFERRED * s_preferred * 100, 1),
        "Keyword Coverage (10%)": round(_W_KEYWORDS * s_keywords * 100, 1),
        "Education Match (5%)": round(_W_EDUCATION * s_education * 100, 1),
    }

    result = ScoreResult(
        total_score=total_score,
        fit_label=fit_label,
        required_signal=round(s_required, 4),
        experience_signal=round(s_experience, 4),
        preferred_signal=round(s_preferred, 4),
        keyword_signal=round(s_keywords, 4),
        education_signal=round(s_education, 4),
        breakdown=breakdown,
    )

    logger.info(
        "scorer.calculate_score | total=%.1f | label=%r | "
        "req=%.3f | exp=%.3f | pref=%.3f | kw=%.3f | edu=%.3f",
        result.total_score,
        result.fit_label,
        result.required_signal,
        result.experience_signal,
        result.preferred_signal,
        result.keyword_signal,
        result.education_signal,
    )

    return result


# ---------------------------------------------------------------------------
# Private signal helpers
# ---------------------------------------------------------------------------


def _normalise(skill: str) -> str:
    """
    Lowercase and strip whitespace from *skill* for case-insensitive
    set comparison.

    Parameters
    ----------
    skill : str
        Raw skill string.

    Returns
    -------
    str
        Lowercased, stripped skill string.
    """
    return skill.strip().lower()


def _seniority_signal(
    candidate_level: Optional[str],
    jd_level: Optional[str],
) -> float:
    """
    Compute a seniority alignment signal in [0.0, 1.0].

    Maps seniority level strings to ordinal integers and computes alignment:

    +----------+-------+
    | Level    | Value |
    +==========+=======+
    | Junior   |   1   |
    +----------+-------+
    | Mid      |   2   |
    +----------+-------+
    | Senior   |   3   |
    +----------+-------+
    | Lead     |   4   |
    +----------+-------+

    Signal rules:

    - **1.0** — exact level match.
    - **0.5** — adjacent levels (difference of 1), e.g. Mid↔Senior.
    - **0.0** — non-adjacent mismatch (difference ≥ 2).
    - **0.5** — either or both levels are ``None`` (benefit of the doubt).

    Parameters
    ----------
    candidate_level : str or None
        Candidate's inferred seniority level (from ``ResumeProfile``).
    jd_level : str or None
        Seniority level stated or inferred from the job description.

    Returns
    -------
    float
        Alignment signal in {0.0, 0.5, 1.0}.
    """
    if candidate_level is None or jd_level is None:
        return 0.5  # benefit of the doubt when level is unknown

    _LEVEL_MAP: dict[str, int] = {
        "junior": 1,
        "mid": 2,
        "mid-level": 2,
        "senior": 3,
        "lead": 4,
        "staff": 4,
        "principal": 5,
        "director": 6,
    }

    c_val = _LEVEL_MAP.get(candidate_level.strip().lower())
    j_val = _LEVEL_MAP.get(jd_level.strip().lower())

    if c_val is None or j_val is None:
        # Unrecognised level string — benefit of the doubt
        return 0.5

    diff = abs(c_val - j_val)
    if diff == 0:
        return 1.0
    if diff == 1:
        return 0.5
    return 0.0


def _experience_signal(
    candidate_years: Optional[float],
    experience_requirements: list,
) -> float:
    """
    Compute an experience alignment signal in [0.0, 1.0].

    Finds the most constraining (highest minimum) experience requirement in
    *experience_requirements* and compares it against *candidate_years*.

    Signal rules:

    - If there are no experience requirements, return **1.0** (vacuously met).
    - If *candidate_years* is ``None``, return **0.5** (benefit of the doubt).
    - If *candidate_years* ≥ ``min_years``, return **1.0**.
    - If *candidate_years* < ``min_years``, return a partial score:
      ``candidate_years / min_years`` (linear ramp, clamped to [0, 1]).

    Parameters
    ----------
    candidate_years : float or None
        Total years of professional experience from ``ResumeProfile``.
    experience_requirements : list[ExperienceRequirement]
        Experience requirements from ``JobDescription``.

    Returns
    -------
    float
        Experience alignment signal in [0.0, 1.0].
    """
    # Extract the tightest (highest) minimum requirement
    min_years_required: Optional[float] = None
    for req in experience_requirements:
        if req.min_years is not None:
            if min_years_required is None or req.min_years > min_years_required:
                min_years_required = req.min_years

    if min_years_required is None:
        return 1.0  # no minimum stated — vacuously satisfied

    if candidate_years is None:
        return 0.5  # unknown experience — benefit of the doubt

    if candidate_years >= min_years_required:
        return 1.0

    # Partial credit: linear ramp from 0 to 1 as years approach the requirement
    return max(0.0, candidate_years / min_years_required)


def _keyword_signal(ats_report: ATSScore) -> float:
    """
    Compute a weighted ATS keyword presence signal in [0.0, 1.0].

    For each keyword in ``ats_report.priority_keywords``, adds its ``weight``
    to the numerator if ``present_in_resume`` is True.  The denominator is
    the sum of all weights.

    Returns **0.0** if there are no priority keywords (conservative default).
    Returns **0.0** if the total weight is effectively zero.

    Parameters
    ----------
    ats_report : ATSScore
        ATS keyword optimisation report from Agent 4.

    Returns
    -------
    float
        Weighted keyword presence ratio in [0.0, 1.0].
    """
    if not ats_report.priority_keywords:
        return 0.0

    total_weight: float = sum(kw.weight for kw in ats_report.priority_keywords)
    if total_weight < 1e-9:
        return 0.0

    present_weight: float = sum(
        kw.weight for kw in ats_report.priority_keywords if kw.present_in_resume
    )
    return present_weight / total_weight


def _education_signal(
    profile: ResumeProfile,
    jd_seniority: Optional[str],
) -> float:
    """
    Compute an education alignment signal in [0.0, 1.0].

    Uses a simple proxy: maps the candidate's highest degree to an ordinal
    level and checks alignment with the JD's seniority expectation.

    Degree levels:

    +------------------------------+-------+
    | Degree (normalised)          | Level |
    +==============================+=======+
    | High school / diploma        |   1   |
    +------------------------------+-------+
    | Associate / certificate      |   2   |
    +------------------------------+-------+
    | Bachelor / undergraduate     |   3   |
    +------------------------------+-------+
    | Master / postgraduate        |   4   |
    +------------------------------+-------+
    | PhD / doctorate              |   5   |
    +------------------------------+-------+

    Seniority → expected minimum degree level:

    +-----------+------------------+
    | Seniority | Min degree level |
    +===========+==================+
    | Junior    | 2 (Associate)    |
    +-----------+------------------+
    | Mid       | 3 (Bachelor)     |
    +-----------+------------------+
    | Senior    | 3 (Bachelor)     |
    +-----------+------------------+
    | Lead      | 3 (Bachelor)     |
    +-----------+------------------+
    | (unknown) | 3 (Bachelor)     |
    +-----------+------------------+

    Signal: **1.0** if candidate degree ≥ expected; **0.5** if one level below;
    **0.0** if two or more levels below.  Returns **0.5** if no education data.

    Parameters
    ----------
    profile : ResumeProfile
        Parsed candidate resume.
    jd_seniority : str or None
        Seniority level from the job description.

    Returns
    -------
    float
        Education alignment signal in {0.0, 0.5, 1.0}.
    """
    if not profile.education:
        return 0.5  # no education data — benefit of the doubt

    _DEGREE_LEVEL: dict[str, int] = {
        "high school": 1,
        "diploma": 1,
        "associate": 2,
        "certificate": 2,
        "bachelor": 3,
        "undergraduate": 3,
        "master": 4,
        "mba": 4,
        "postgraduate": 4,
        "phd": 5,
        "doctorate": 5,
        "doctoral": 5,
    }

    # Determine highest degree level from candidate's education list
    highest_level: int = 0
    for edu in profile.education:
        degree_lower = edu.degree.lower()
        for keyword, level in _DEGREE_LEVEL.items():
            if keyword in degree_lower:
                highest_level = max(highest_level, level)

    if highest_level == 0:
        return 0.5  # degree not recognised — benefit of the doubt

    # Determine expected minimum degree from JD seniority
    _SENIORITY_MIN_DEGREE: dict[str, int] = {
        "junior": 2,
        "entry-level": 2,
        "entry": 2,
        "mid": 3,
        "mid-level": 3,
        "senior": 3,
        "lead": 3,
        "staff": 3,
        "principal": 4,
        "director": 4,
    }
    jd_seniority_norm = (jd_seniority or "").strip().lower()
    expected_min = _SENIORITY_MIN_DEGREE.get(jd_seniority_norm, 3)

    diff = expected_min - highest_level  # positive = candidate below expected
    if diff <= 0:
        return 1.0
    if diff == 1:
        return 0.5
    return 0.0


def _fit_label(score: float) -> str:
    """
    Map a numeric score to a human-readable fit label.

    +---------------+--------+
    | Label         | Range  |
    +===============+========+
    | Strong Match  | ≥ 75   |
    +---------------+--------+
    | Good Match    | ≥ 55   |
    +---------------+--------+
    | Partial Match | ≥ 35   |
    +---------------+--------+
    | Low Match     | < 35   |
    +---------------+--------+

    Parameters
    ----------
    score : float
        Total score in [0.0, 100.0].

    Returns
    -------
    str
        Human-readable fit label.
    """
    if score >= 75:
        return _LABEL_STRONG
    if score >= 55:
        return _LABEL_GOOD
    if score >= 35:
        return _LABEL_PARTIAL
    return _LABEL_LOW
