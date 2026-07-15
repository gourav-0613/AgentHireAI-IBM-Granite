"""
models package

Pydantic v2 models that act as the data contracts for the entire project.
Every agent receives a model as input and returns a model as output.
Every LLM JSON response must be validated through the relevant model before
being stored in session state or passed to the next agent.

Public re-exports for convenience:
    from models import ResumeProfile, JobDescription, SkillGapReport, ATSReport, TailoredResume
"""

from models.resume import ContactInfo, Education, WorkExperience, ResumeProfile
from models.job_description import JobDescription
from models.analysis import KeywordWeight, SkillGapReport, ATSReport, TailoredResume

__all__ = [
    "ContactInfo",
    "Education",
    "WorkExperience",
    "ResumeProfile",
    "JobDescription",
    "KeywordWeight",
    "SkillGapReport",
    "ATSReport",
    "TailoredResume",
]
