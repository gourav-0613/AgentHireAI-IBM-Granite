"""
models/analysis.py

Pydantic v2 models for all analysis pipeline outputs.

These models are the output contracts of Agents 3, 4, and 5:
    SkillGapAnalysis — output of Agent 3 (Skill Gap Analyzer)
    ATSScore         — output of Agent 4 (ATS Keyword Optimizer)
    ResumeAnalysis   — composite analysis result combining gap and ATS data
    TailoredResume   — output of Agent 5 (Resume Tailor)

KeywordWeight is a sub-model used within ATSScore.

All models are also consumed by core/scorer.py (deterministic scoring)
and core/pdf_generator.py (ATS-friendly PDF generation).
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from models.resume import WorkExperience


# ---------------------------------------------------------------------------
# KeywordWeight  (sub-model for ATSScore)
# ---------------------------------------------------------------------------

class KeywordWeight(BaseModel):
    """Relevance weight and presence metadata for a single ATS keyword."""

    keyword: str = Field(
        ...,
        min_length=1,
        description="The ATS keyword or keyphrase extracted from the job description.",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "Relevance score between 0.0 and 1.0 derived from keyword frequency "
            "and positional importance within the job description."
        ),
    )
    present_in_resume: bool = Field(
        ...,
        description="True if this keyword was found in the candidate's current resume profile.",
    )


# ---------------------------------------------------------------------------
# SkillGapAnalysis
# ---------------------------------------------------------------------------

class SkillGapAnalysis(BaseModel):
    """
    Structured skill-gap analysis comparing a candidate's resume against a job description.

    This is the output contract of Agent 3 (Skill Gap Analyzer).
    """

    matched_skills: List[str] = Field(
        default_factory=list,
        description="Skills present in both the candidate's resume and the job description.",
    )
    missing_critical: List[str] = Field(
        default_factory=list,
        description="Required skills from the job description that are absent from the resume.",
    )
    missing_preferred: List[str] = Field(
        default_factory=list,
        description="Preferred (nice-to-have) skills from the JD that are absent from the resume.",
    )
    transferable_skills: List[str] = Field(
        default_factory=list,
        description=(
            "Resume skills that partially or indirectly satisfy job description requirements, "
            "e.g. 'Pandas' as a transferable signal for 'Data Manipulation'."
        ),
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description=(
            "Human-readable, actionable suggestions to help the candidate close identified gaps, "
            "e.g. 'Consider obtaining the AWS Certified Solutions Architect certification'."
        ),
    )
    match_percentage: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Overall skill match percentage (0–100) relative to the job description.",
    )


# ---------------------------------------------------------------------------
# ATSScore
# ---------------------------------------------------------------------------

class ATSScore(BaseModel):
    """
    ATS keyword optimisation report for a candidate's resume against a job description.

    This is the output contract of Agent 4 (ATS Keyword Optimizer).
    """

    priority_keywords: List[KeywordWeight] = Field(
        default_factory=list,
        description=(
            "Ranked list of ATS keywords with relevance weights and resume-presence flags, "
            "ordered by descending weight."
        ),
    )
    phrases_to_include: List[str] = Field(
        default_factory=list,
        description=(
            "Exact phrases, acronyms, or industry-standard terms that ATS systems are likely "
            "to scan for and that should be incorporated into the resume."
        ),
    )
    phrases_to_avoid: List[str] = Field(
        default_factory=list,
        description=(
            "Overused buzzwords, clichés, or penalised phrases that should be removed "
            "or replaced in the resume."
        ),
    )
    overall_ats_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Estimated ATS pass-through score (0–100) for the current resume.",
    )
    optimised_ats_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Projected ATS pass-through score (0–100) after applying all recommendations.",
    )

    @field_validator("priority_keywords", mode="before")
    @classmethod
    def sort_keywords_by_weight(cls, v: list) -> list:
        """Sort priority keywords by descending weight after construction."""
        if not v:
            return v
        # Only sort dicts/objects that have a 'weight' key to avoid errors
        try:
            return sorted(
                v,
                key=lambda x: x["weight"] if isinstance(x, dict) else x.weight,
                reverse=True,
            )
        except (KeyError, AttributeError, TypeError):
            return v


# ---------------------------------------------------------------------------
# ResumeAnalysis
# ---------------------------------------------------------------------------

class ResumeAnalysis(BaseModel):
    """
    Composite analysis result that combines skill-gap and ATS outputs for a
    single (resume, job description) pair.

    Acts as the shared state object passed between Agent 3, Agent 4, and the
    reporting layer.
    """

    candidate_name: Optional[str] = Field(
        default=None,
        description="Candidate's full name, carried forward from the parsed resume.",
    )
    role_title: Optional[str] = Field(
        default=None,
        description="Target role title, carried forward from the parsed job description.",
    )
    skill_gap: SkillGapAnalysis = Field(
        ...,
        description="Skill-gap analysis result for this (resume, JD) pair.",
    )
    ats_score: ATSScore = Field(
        ...,
        description="ATS keyword optimisation report for this (resume, JD) pair.",
    )
    overall_fit_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description=(
            "Composite fit score (0–100) combining skill match percentage and ATS score, "
            "computed deterministically by core/scorer.py."
        ),
    )
    fit_label: Optional[str] = Field(
        default=None,
        description="Human-readable label for the fit score, e.g. 'Strong Match', 'Partial Match', 'Low Match'.",
    )


# ---------------------------------------------------------------------------
# TailoredResume
# ---------------------------------------------------------------------------

class TailoredResume(BaseModel):
    """
    Tailored resume content produced by Agent 5 (Resume Tailor).

    Contains rewritten sections optimised for the target job description.
    The source WorkExperience model is reused to avoid duplication.
    """

    rewritten_summary: str = Field(
        ...,
        min_length=1,
        description=(
            "Rewritten professional summary tailored to align with the target role's "
            "language, keywords, and value propositions."
        ),
    )
    rewritten_experience: List[WorkExperience] = Field(
        default_factory=list,
        description=(
            "Work experience entries with rewritten bullet points that incorporate "
            "job description keywords and quantify achievements where possible."
        ),
    )
    highlighted_skills: List[str] = Field(
        default_factory=list,
        description=(
            "Skills from the candidate's profile that are most relevant to the target role "
            "and should be prominently featured in the tailored resume."
        ),
    )
    suggested_additions: List[str] = Field(
        default_factory=list,
        description=(
            "Certifications, courses, or projects the candidate could add to strengthen "
            "their application, e.g. 'AWS Certified Data Analytics – Specialty'."
        ),
    )
    tailoring_notes: List[str] = Field(
        default_factory=list,
        description=(
            "Internal notes from the tailor agent explaining key decisions made during "
            "the tailoring process. Not rendered in the final PDF."
        ),
    )

    @field_validator("highlighted_skills", mode="before")
    @classmethod
    def deduplicate_highlighted_skills(cls, v: List[str]) -> List[str]:
        """Remove duplicate entries in highlighted_skills while preserving order."""
        seen: set = set()
        result: List[str] = []
        for item in v:
            normalised = item.strip()
            if normalised and normalised.lower() not in seen:
                seen.add(normalised.lower())
                result.append(normalised)
        return result


# ---------------------------------------------------------------------------
# Backward-compatible aliases (match __init__.py public contract)
# ---------------------------------------------------------------------------

#: Alias — SkillGapAnalysis was originally named SkillGapReport in __init__.py
SkillGapReport = SkillGapAnalysis

#: Alias — ATSScore was originally named ATSReport in __init__.py
ATSReport = ATSScore
