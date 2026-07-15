"""
models/resume.py

Pydantic v2 models representing a candidate's resume.

These models are the output contract of Agent 1 (Resume Parser).
The JSON schema auto-generated from ResumeProfile is injected directly
into the Granite extraction prompt to guarantee output fidelity.

Models defined here:
    PersonalInfo     — candidate contact and personal details
    Education        — a single educational qualification
    WorkExperience   — a single role / position
    Project          — a single personal or professional project
    Certification    — a single certification or licence
    ResumeProfile    — top-level model, output of the Resume Parser agent
"""

from __future__ import annotations

from typing import List, Literal, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# PersonalInfo
# ---------------------------------------------------------------------------

class PersonalInfo(BaseModel):
    """Contact and personal identification details for a candidate."""

    full_name: str = Field(
        ...,
        min_length=1,
        description="Candidate's full legal name.",
    )
    email: Optional[EmailStr] = Field(
        default=None,
        description="Primary contact e-mail address.",
    )
    phone: Optional[str] = Field(
        default=None,
        description="Phone number in any locally accepted format.",
    )
    location: Optional[str] = Field(
        default=None,
        description="City, state, country, or 'Remote'.",
    )
    linkedin: Optional[str] = Field(
        default=None,
        description="Full LinkedIn profile URL.",
    )
    github: Optional[str] = Field(
        default=None,
        description="Full GitHub profile URL.",
    )
    portfolio: Optional[str] = Field(
        default=None,
        description="Personal website or portfolio URL.",
    )


# ---------------------------------------------------------------------------
# Education
# ---------------------------------------------------------------------------

class Education(BaseModel):
    """A single educational qualification obtained by the candidate."""

    degree: str = Field(
        ...,
        min_length=1,
        description="Degree or qualification title, e.g. 'Bachelor of Science in Computer Science'.",
    )
    institution: str = Field(
        ...,
        min_length=1,
        description="Name of the university, college, or educational body.",
    )
    year: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Year of graduation or expected graduation.",
    )
    gpa: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,
        description="Grade Point Average on a 4.0 scale, if applicable.",
    )
    field_of_study: Optional[str] = Field(
        default=None,
        description="Specific major or concentration, if separate from degree title.",
    )


# ---------------------------------------------------------------------------
# WorkExperience
# ---------------------------------------------------------------------------

class WorkExperience(BaseModel):
    """A single employment role or position held by the candidate."""

    title: str = Field(
        ...,
        min_length=1,
        description="Job title / position held, e.g. 'Senior Software Engineer'.",
    )
    company: str = Field(
        ...,
        min_length=1,
        description="Employer or organisation name.",
    )
    start_date: str = Field(
        ...,
        description="Start date in 'YYYY-MM' or 'Month YYYY' format.",
    )
    end_date: Optional[str] = Field(
        default=None,
        description="End date in 'YYYY-MM' or 'Month YYYY' format. None indicates 'Present'.",
    )
    location: Optional[str] = Field(
        default=None,
        description="Work location, e.g. 'New York, NY' or 'Remote'.",
    )
    bullets: List[str] = Field(
        default_factory=list,
        description="Achievement and responsibility bullet points for this role.",
    )


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

class Project(BaseModel):
    """A personal, academic, or professional project completed by the candidate."""

    name: str = Field(
        ...,
        min_length=1,
        description="Project name or title.",
    )
    description: Optional[str] = Field(
        default=None,
        description="Brief description of the project, its purpose and outcomes.",
    )
    technologies: List[str] = Field(
        default_factory=list,
        description="Technologies, languages, or frameworks used in the project.",
    )
    url: Optional[str] = Field(
        default=None,
        description="Live URL or repository link for the project.",
    )
    year: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Year the project was completed or last active.",
    )


# ---------------------------------------------------------------------------
# Certification
# ---------------------------------------------------------------------------

class Certification(BaseModel):
    """A professional certification or licence held by the candidate."""

    name: str = Field(
        ...,
        min_length=1,
        description="Full name of the certification or licence.",
    )
    issuer: Optional[str] = Field(
        default=None,
        description="Issuing organisation, e.g. 'AWS', 'Google', 'PMI'.",
    )
    year: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Year the certification was awarded.",
    )
    expiry_year: Optional[int] = Field(
        default=None,
        ge=1900,
        le=2100,
        description="Year the certification expires, if applicable.",
    )
    credential_id: Optional[str] = Field(
        default=None,
        description="Unique credential or badge ID issued by the certifying body.",
    )


# ---------------------------------------------------------------------------
# ResumeProfile
# ---------------------------------------------------------------------------

class ResumeProfile(BaseModel):
    """
    Top-level model representing a fully parsed candidate resume.

    This is the output contract of Agent 1 (Resume Parser). Every field
    below may be extracted directly from the resume text or inferred by
    the parsing agent during a single Granite LLM call.
    """

    personal_info: PersonalInfo = Field(
        ...,
        description="Candidate's contact and personal identification details.",
    )
    summary: Optional[str] = Field(
        default=None,
        description="Professional summary or objective statement extracted from the resume.",
    )
    education: List[Education] = Field(
        default_factory=list,
        description="List of educational qualifications, most recent first.",
    )
    experience: List[WorkExperience] = Field(
        default_factory=list,
        description="List of work experiences / roles, most recent first.",
    )
    projects: List[Project] = Field(
        default_factory=list,
        description="List of personal, academic, or professional projects.",
    )
    skills: List[str] = Field(
        default_factory=list,
        description="Flat list of technical and soft skills extracted from the resume.",
    )
    certifications: List[Certification] = Field(
        default_factory=list,
        description="List of professional certifications or licences held.",
    )
    seniority_level: Optional[Literal["Junior", "Mid", "Senior", "Lead"]] = Field(
        default=None,
        description="Inferred seniority level based on experience depth and title signals.",
    )
    dominant_domain: Optional[str] = Field(
        default=None,
        description="Primary technical or business domain inferred from the resume, e.g. 'Data Engineering'.",
    )
    total_years_experience: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Total years of professional work experience, inferred from work history.",
    )

    @field_validator("skills", mode="before")
    @classmethod
    def deduplicate_skills(cls, v: List[str]) -> List[str]:
        """Remove duplicate skill entries while preserving insertion order."""
        seen: set = set()
        result: List[str] = []
        for item in v:
            normalised = item.strip()
            if normalised and normalised.lower() not in seen:
                seen.add(normalised.lower())
                result.append(normalised)
        return result


# ---------------------------------------------------------------------------
# Backward-compatible alias (matches __init__.py public contract)
# ---------------------------------------------------------------------------

#: Alias — PersonalInfo was originally named ContactInfo in __init__.py
ContactInfo = PersonalInfo
