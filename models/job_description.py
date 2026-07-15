"""
models/job_description.py

Pydantic v2 models representing a parsed job description.

These models are the output contract of Agent 2 (JD Analyzer).
The JSON schema auto-generated from JobDescription is injected directly
into the Granite decomposition prompt.

Models defined here:
    RequiredSkill          — a single must-have skill with optional context
    PreferredSkill         — a single nice-to-have skill with optional context
    ExperienceRequirement  — a structured experience requirement extracted from the JD
    JobDescription         — top-level model, output of the JD Analyzer agent
"""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# RequiredSkill
# ---------------------------------------------------------------------------

class RequiredSkill(BaseModel):
    """A single must-have skill extracted from the job description."""

    skill: str = Field(
        ...,
        min_length=1,
        description="Name of the required skill, e.g. 'Python', 'Kubernetes'.",
    )
    context: Optional[str] = Field(
        default=None,
        description="Optional context or qualifier from the JD, e.g. '3+ years of Python'.",
    )


# ---------------------------------------------------------------------------
# PreferredSkill
# ---------------------------------------------------------------------------

class PreferredSkill(BaseModel):
    """A single nice-to-have skill extracted from the job description."""

    skill: str = Field(
        ...,
        min_length=1,
        description="Name of the preferred skill, e.g. 'Spark', 'dbt'.",
    )
    context: Optional[str] = Field(
        default=None,
        description="Optional context or qualifier from the JD, e.g. 'experience with dbt preferred'.",
    )


# ---------------------------------------------------------------------------
# ExperienceRequirement
# ---------------------------------------------------------------------------

class ExperienceRequirement(BaseModel):
    """A structured work-experience requirement extracted from the job description."""

    description: str = Field(
        ...,
        min_length=1,
        description="Human-readable description of the experience requirement.",
    )
    min_years: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Minimum number of years of experience required.",
    )
    max_years: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Maximum number of years stated, if an upper bound is given.",
    )
    domain: Optional[str] = Field(
        default=None,
        description="Specific domain or technology the experience requirement relates to.",
    )


# ---------------------------------------------------------------------------
# JobDescription
# ---------------------------------------------------------------------------

class JobDescription(BaseModel):
    """
    Top-level model representing a fully parsed and structured job description.

    This is the output contract of Agent 2 (JD Analyzer). Every field is
    either extracted verbatim or inferred by the Granite LLM during a single
    decomposition call.
    """

    raw_text: str = Field(
        ...,
        min_length=1,
        description="Original, unmodified job description text as supplied by the user.",
    )
    role_title: str = Field(
        ...,
        min_length=1,
        description="Job title extracted or inferred from the posting, e.g. 'Senior Data Engineer'.",
    )
    company_name: Optional[str] = Field(
        default=None,
        description="Name of the hiring company, if stated in the posting.",
    )
    company_signals: List[str] = Field(
        default_factory=list,
        description="Inferred company values, culture cues, or mission signals from the JD.",
    )
    required_skills: List[RequiredSkill] = Field(
        default_factory=list,
        description="Structured list of must-have skills extracted from the JD.",
    )
    preferred_skills: List[PreferredSkill] = Field(
        default_factory=list,
        description="Structured list of nice-to-have skills extracted from the JD.",
    )
    experience_requirements: List[ExperienceRequirement] = Field(
        default_factory=list,
        description="Structured list of experience requirements extracted from the JD.",
    )
    responsibilities: List[str] = Field(
        default_factory=list,
        description="Key role responsibilities and day-to-day duties listed in the JD.",
    )
    seniority_level: Optional[str] = Field(
        default=None,
        description="Seniority level inferred from the JD, e.g. 'Senior', 'Mid-level', 'Entry-level'.",
    )
    location: Optional[str] = Field(
        default=None,
        description="Work location stated in the JD, e.g. 'Remote', 'New York, NY'.",
    )
    employment_type: Optional[str] = Field(
        default=None,
        description="Employment type, e.g. 'Full-time', 'Contract', 'Part-time'.",
    )

    @field_validator("required_skills", "preferred_skills", mode="before")
    @classmethod
    def coerce_skill_strings(cls, v: list) -> list:
        """
        Allow plain strings in required_skills / preferred_skills by coercing
        them to the appropriate dict structure so callers can pass either
        ``["Python", "Go"]`` or ``[{"skill": "Python"}]``.
        """
        result = []
        for item in v:
            if isinstance(item, str):
                result.append({"skill": item})
            else:
                result.append(item)
        return result
