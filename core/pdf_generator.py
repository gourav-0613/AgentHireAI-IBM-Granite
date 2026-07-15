"""
core/pdf_generator.py

ATS-friendly PDF resume generator.

Generates a clean, single-column PDF from a
:class:`~models.analysis.TailoredResume` and the original
:class:`~models.resume.ResumeProfile` using ReportLab.  Also embeds an
ATS match-score panel (from :class:`~core.scorer.ScoreResult`) at the end
of the document so the candidate can review their score alongside the
tailored CV.

ATS compliance rules enforced
------------------------------
- **Single-column layout** — no tables, multi-column frames, or text boxes.
- **Standard section order** — SUMMARY → EXPERIENCE → SKILLS → EDUCATION →
  CERTIFICATIONS → PROJECTS → ATS SCORE REPORT.
- **Embedded vector fonts** — Helvetica family; no bitmap text.
- **No graphics** — no images, icons, logos, or decorative lines beyond
  thin horizontal rules rendered as underlined paragraph content.
- **Unicode-safe** — all strings are coerced to safe ASCII/Latin-1 before
  rendering to avoid ReportLab encoding errors on non-Latin characters.
- **PDF metadata** — Title = "<CandidateName> – <RoleTitle>"; Author = name.

Usage
-----
.. code-block:: python

    from core.pdf_generator import generate_pdf
    pdf_bytes = generate_pdf(
        tailored_resume=tailored,
        resume_profile=profile,
        score_result=score,
        role_title="Senior Data Engineer",
    )
    # pdf_bytes is ready for st.download_button
"""

from __future__ import annotations

import io
import logging
import unicodedata
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from models.analysis import TailoredResume
from models.resume import ResumeProfile

# ScoreResult imported at runtime to avoid circular imports; type-only import
# is avoided because we access attributes directly in the function body.
from core.scorer import ScoreResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page geometry
# ---------------------------------------------------------------------------

_PAGE_SIZE = LETTER           # 8.5 × 11 inches
_MARGIN_LR = 0.75 * inch      # left / right margin
_MARGIN_TB = 0.65 * inch      # top / bottom margin

# ---------------------------------------------------------------------------
# Colour palette  (ATS-safe: no fills on body text; accents only on headings)
# ---------------------------------------------------------------------------

_C_BLACK = colors.HexColor("#1a1a1a")
_C_DARK = colors.HexColor("#2c2c2c")
_C_MID = colors.HexColor("#555555")
_C_RULE = colors.HexColor("#cccccc")
_C_ACCENT = colors.HexColor("#1a3a6b")   # deep navy for section headings

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

_BASE = getSampleStyleSheet()

# Candidate name — large, navy
_S_NAME = ParagraphStyle(
    "CandidateName",
    fontName="Helvetica-Bold",
    fontSize=20,
    leading=24,
    textColor=_C_ACCENT,
    alignment=TA_CENTER,
    spaceAfter=2,
)

# Contact line beneath name
_S_CONTACT = ParagraphStyle(
    "Contact",
    fontName="Helvetica",
    fontSize=8.5,
    leading=11,
    textColor=_C_MID,
    alignment=TA_CENTER,
    spaceAfter=4,
)

# Section heading (e.g. EXPERIENCE)
_S_SECTION = ParagraphStyle(
    "SectionHeading",
    fontName="Helvetica-Bold",
    fontSize=10,
    leading=13,
    textColor=_C_ACCENT,
    spaceBefore=8,
    spaceAfter=1,
    textTransform="uppercase",
)

# Role / degree title line
_S_ROLE = ParagraphStyle(
    "RoleTitle",
    fontName="Helvetica-Bold",
    fontSize=9.5,
    leading=12,
    textColor=_C_BLACK,
    spaceBefore=5,
    spaceAfter=0,
)

# Company / institution + date (right-aligned date via a small table trick
# avoided for ATS; instead we put it on the same line separated by spaces)
_S_META = ParagraphStyle(
    "RoleMeta",
    fontName="Helvetica-Oblique",
    fontSize=8.5,
    leading=11,
    textColor=_C_MID,
    spaceAfter=1,
)

# Bullet point
_S_BULLET = ParagraphStyle(
    "Bullet",
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=_C_DARK,
    leftIndent=14,
    bulletIndent=4,
    spaceAfter=1,
)

# Body / paragraph text
_S_BODY = ParagraphStyle(
    "Body",
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=_C_DARK,
    spaceAfter=2,
)

# Skills — comma-separated inline list
_S_SKILLS = ParagraphStyle(
    "Skills",
    fontName="Helvetica",
    fontSize=9,
    leading=13,
    textColor=_C_DARK,
    spaceAfter=2,
)

# ATS Score panel heading
_S_SCORE_LABEL = ParagraphStyle(
    "ScoreLabel",
    fontName="Helvetica-Bold",
    fontSize=9,
    leading=12,
    textColor=_C_MID,
    spaceAfter=1,
)

# ATS Score value (large)
_S_SCORE_VALUE = ParagraphStyle(
    "ScoreValue",
    fontName="Helvetica-Bold",
    fontSize=22,
    leading=26,
    textColor=_C_ACCENT,
    alignment=TA_CENTER,
    spaceAfter=2,
)

_S_BREAKDOWN = ParagraphStyle(
    "Breakdown",
    fontName="Helvetica",
    fontSize=8.5,
    leading=11,
    textColor=_C_MID,
    spaceAfter=1,
)

_S_REC = ParagraphStyle(
    "Recommendation",
    fontName="Helvetica",
    fontSize=9,
    leading=12,
    textColor=_C_DARK,
    leftIndent=10,
    spaceAfter=2,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pdf(
    tailored_resume: TailoredResume,
    resume_profile: ResumeProfile,
    score_result: ScoreResult,
    role_title: str,
) -> bytes:
    """
    Build an ATS-friendly PDF resume and return the raw bytes.

    The document is assembled entirely in memory — no temporary files are
    created.  The returned bytes are ready to be passed directly to
    Streamlit's ``st.download_button``.

    Structure
    ---------
    1. Header — candidate name + contact details
    2. Professional Summary (rewritten by Agent 5)
    3. Work Experience (rewritten bullets from Agent 5)
    4. Skills (highlighted_skills from Agent 5)
    5. Education (from original ResumeProfile)
    6. Certifications (from original ResumeProfile)
    7. Projects (from original ResumeProfile)
    8. ATS Match Score Report (score + breakdown + recommendations)

    Parameters
    ----------
    tailored_resume : TailoredResume
        Validated output of Agent 5 — contains rewritten sections.
    resume_profile : ResumeProfile
        Validated output of Agent 1 — provides education, certifications,
        projects, and contact info (unchanged by tailoring).
    score_result : ScoreResult
        Output of ``core.scorer.calculate_score`` — provides total score,
        fit label, and per-signal breakdown.
    role_title : str
        Target role title used in the PDF title metadata and score panel.

    Returns
    -------
    bytes
        Raw PDF bytes suitable for binary file I/O or Streamlit download.

    Raises
    ------
    RuntimeError
        If ReportLab fails to build the document for any reason.
    """
    candidate_name: str = resume_profile.personal_info.full_name

    logger.info(
        "pdf_generator.generate_pdf | building PDF | "
        "candidate=%r | role=%r",
        candidate_name,
        role_title,
    )

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN_LR,
        rightMargin=_MARGIN_LR,
        topMargin=_MARGIN_TB,
        bottomMargin=_MARGIN_TB,
        title=f"{_safe(candidate_name)} – {_safe(role_title)}",
        author=_safe(candidate_name),
        subject=f"Tailored resume for {_safe(role_title)}",
    )

    story: list = []

    # 1. Header
    story.extend(_render_header(resume_profile))

    # 2. Summary
    if tailored_resume.rewritten_summary:
        story.extend(_render_section("Summary"))
        story.append(
            Paragraph(_safe(tailored_resume.rewritten_summary), _S_BODY)
        )

    # 3. Experience
    if tailored_resume.rewritten_experience:
        story.extend(_render_section("Experience"))
        story.extend(_render_experience(tailored_resume.rewritten_experience))

    # 4. Skills
    skills_to_show = tailored_resume.highlighted_skills or resume_profile.skills
    if skills_to_show:
        story.extend(_render_section("Skills"))
        story.extend(_render_skills(skills_to_show))

    # 5. Education
    if resume_profile.education:
        story.extend(_render_section("Education"))
        story.extend(_render_education(resume_profile.education))

    # 6. Certifications
    if resume_profile.certifications:
        story.extend(_render_section("Certifications"))
        story.extend(_render_certifications(resume_profile.certifications))

    # 7. Projects
    if resume_profile.projects:
        story.extend(_render_section("Projects"))
        story.extend(_render_projects(resume_profile.projects))

    # 8. ATS Score Report
    story.extend(_render_section("ATS Match Score Report"))
    story.extend(
        _render_score_panel(
            score_result=score_result,
            role_title=role_title,
            recommended_additions=tailored_resume.suggested_additions,
        )
    )

    try:
        doc.build(story)
    except Exception as exc:
        raise RuntimeError(
            f"ReportLab failed to build the PDF: {exc}"
        ) from exc

    pdf_bytes = buffer.getvalue()

    logger.info(
        "pdf_generator.generate_pdf | complete | size_bytes=%d",
        len(pdf_bytes),
    )

    return pdf_bytes


# ---------------------------------------------------------------------------
# Private section renderers
# ---------------------------------------------------------------------------


def _render_header(profile: ResumeProfile) -> list:
    """
    Render the candidate name and contact details block.

    Parameters
    ----------
    profile : ResumeProfile
        Source of name and contact fields.

    Returns
    -------
    list
        ReportLab flowable elements for the header block.
    """
    elements: list = []

    elements.append(Paragraph(_safe(profile.personal_info.full_name), _S_NAME))

    # Build a single contact line from available fields
    contact_parts: list[str] = []
    pi = profile.personal_info
    if pi.email:
        contact_parts.append(_safe(str(pi.email)))
    if pi.phone:
        contact_parts.append(_safe(pi.phone))
    if pi.location:
        contact_parts.append(_safe(pi.location))
    if pi.linkedin:
        contact_parts.append(_safe(pi.linkedin))
    if pi.github:
        contact_parts.append(_safe(pi.github))
    if pi.portfolio:
        contact_parts.append(_safe(pi.portfolio))

    if contact_parts:
        elements.append(Paragraph("  |  ".join(contact_parts), _S_CONTACT))

    elements.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=_C_ACCENT,
            spaceAfter=4,
        )
    )
    return elements


def _render_section(title: str) -> list:
    """
    Render a section-heading block with a thin horizontal rule beneath it.

    Parameters
    ----------
    title : str
        Section title text (will be uppercased by the style).

    Returns
    -------
    list
        [Paragraph, HRFlowable, Spacer]
    """
    return [
        Paragraph(_safe(title.upper()), _S_SECTION),
        HRFlowable(
            width="100%",
            thickness=0.5,
            color=_C_RULE,
            spaceAfter=3,
        ),
    ]


def _render_experience(experiences: list) -> list:
    """
    Render the work experience section.

    Parameters
    ----------
    experiences : list[WorkExperience]
        Work experience entries from ``TailoredResume.rewritten_experience``.

    Returns
    -------
    list
        ReportLab flowable elements for all experience entries.
    """
    elements: list = []
    for exp in experiences:
        # Role title
        elements.append(Paragraph(_safe(exp.title), _S_ROLE))

        # Company | Location | Dates
        date_range = _fmt_date_range(exp.start_date, exp.end_date)
        meta_parts: list[str] = [_safe(exp.company)]
        if exp.location:
            meta_parts.append(_safe(exp.location))
        meta_parts.append(date_range)
        elements.append(Paragraph("  ·  ".join(meta_parts), _S_META))

        # Bullet points
        for bullet in exp.bullets:
            elements.append(
                Paragraph(f"• {_safe(bullet)}", _S_BULLET)
            )

        elements.append(Spacer(1, 3))

    return elements


def _render_education(education: list) -> list:
    """
    Render the education section.

    Parameters
    ----------
    education : list[Education]
        Education entries from ``ResumeProfile.education``.

    Returns
    -------
    list
        ReportLab flowable elements for all education entries.
    """
    elements: list = []
    for edu in education:
        degree_text = _safe(edu.degree)
        if edu.field_of_study:
            degree_text += f", {_safe(edu.field_of_study)}"
        elements.append(Paragraph(degree_text, _S_ROLE))

        meta_parts: list[str] = [_safe(edu.institution)]
        if edu.year:
            meta_parts.append(str(edu.year))
        if edu.gpa:
            meta_parts.append(f"GPA: {edu.gpa:.1f}")
        elements.append(Paragraph("  ·  ".join(meta_parts), _S_META))
        elements.append(Spacer(1, 3))

    return elements


def _render_skills(skills: list[str]) -> list:
    """
    Render the skills section as a comma-separated inline list.

    Groups skills into lines of ≤ 8 items each for readability.

    Parameters
    ----------
    skills : list[str]
        Skill strings to render.

    Returns
    -------
    list
        ReportLab flowable elements.
    """
    elements: list = []
    # Chunk into rows of 8 for readability
    chunk_size = 8
    chunks = [skills[i : i + chunk_size] for i in range(0, len(skills), chunk_size)]
    for chunk in chunks:
        elements.append(
            Paragraph(", ".join(_safe(s) for s in chunk), _S_SKILLS)
        )
    return elements


def _render_certifications(certifications: list) -> list:
    """
    Render the certifications section.

    Parameters
    ----------
    certifications : list[Certification]
        Certification entries from ``ResumeProfile.certifications``.

    Returns
    -------
    list
        ReportLab flowable elements.
    """
    elements: list = []
    for cert in certifications:
        parts: list[str] = [_safe(cert.name)]
        if cert.issuer:
            parts.append(_safe(cert.issuer))
        if cert.year:
            parts.append(str(cert.year))
        elements.append(
            Paragraph("  ·  ".join(parts), _S_BODY)
        )
    return elements


def _render_projects(projects: list) -> list:
    """
    Render the projects section.

    Parameters
    ----------
    projects : list[Project]
        Project entries from ``ResumeProfile.projects``.

    Returns
    -------
    list
        ReportLab flowable elements.
    """
    elements: list = []
    for proj in projects:
        elements.append(Paragraph(_safe(proj.name), _S_ROLE))

        meta_parts: list[str] = []
        if proj.year:
            meta_parts.append(str(proj.year))
        if proj.technologies:
            meta_parts.append(", ".join(_safe(t) for t in proj.technologies))
        if meta_parts:
            elements.append(Paragraph("  ·  ".join(meta_parts), _S_META))

        if proj.description:
            elements.append(Paragraph(_safe(proj.description), _S_BODY))

        elements.append(Spacer(1, 3))

    return elements


def _render_score_panel(
    score_result: ScoreResult,
    role_title: str,
    recommended_additions: list[str],
) -> list:
    """
    Render the ATS match score panel at the end of the document.

    Includes:
    - Role title context
    - Total score (large display)
    - Fit label
    - Per-signal breakdown
    - Recommended additions from Agent 5

    Parameters
    ----------
    score_result : ScoreResult
        Scoring result from ``core.scorer.calculate_score``.
    role_title : str
        Target role title for context.
    recommended_additions : list[str]
        Suggested additions from ``TailoredResume.suggested_additions``.

    Returns
    -------
    list
        ReportLab flowable elements for the score panel.
    """
    elements: list = []

    elements.append(
        Paragraph(
            f"Target Role: {_safe(role_title)}",
            _S_SCORE_LABEL,
        )
    )

    # Big score number + label
    elements.append(
        Paragraph(
            f"{score_result.total_score:.1f} / 100",
            _S_SCORE_VALUE,
        )
    )
    elements.append(
        Paragraph(
            _safe(score_result.fit_label),
            ParagraphStyle(
                "FitLabel",
                parent=_S_SCORE_LABEL,
                alignment=TA_CENTER,
                spaceAfter=6,
            ),
        )
    )

    # Per-signal breakdown
    if score_result.breakdown:
        elements.append(Paragraph("Score Breakdown:", _S_SCORE_LABEL))
        for label, value in score_result.breakdown.items():
            elements.append(
                Paragraph(
                    f"  {_safe(label)}: {value:.1f} pts",
                    _S_BREAKDOWN,
                )
            )

    # Recommended additions
    if recommended_additions:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph("Recommended Next Steps:", _S_SCORE_LABEL))
        for rec in recommended_additions:
            elements.append(
                Paragraph(f"→ {_safe(rec)}", _S_REC)
            )

    return elements


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _safe(text: str) -> str:
    """
    Coerce *text* to a ReportLab-safe Latin-1 string.

    Replaces characters outside the Latin-1 range with their closest ASCII
    approximation using NFKD normalisation, then drops any remaining
    non-encodable code points.  Also strips ``<`` and ``>`` characters to
    prevent them being misinterpreted as XML tags by ReportLab's Paragraph
    parser.

    Parameters
    ----------
    text : str
        Raw Unicode string.

    Returns
    -------
    str
        Sanitised string safe for ReportLab Paragraph rendering.
    """
    if not isinstance(text, str):
        text = str(text)
    # Normalise to NFKD, then encode to ASCII ignoring non-ASCII
    normalised = unicodedata.normalize("NFKD", text)
    ascii_bytes = normalised.encode("ascii", errors="ignore")
    safe = ascii_bytes.decode("ascii")
    # Strip XML-special characters to avoid ReportLab markup parsing errors
    safe = safe.replace("<", "").replace(">", "").replace("&", "and")
    return safe


def _fmt_date_range(start: str, end: Optional[str]) -> str:
    """
    Format a date range string from *start* and *end*.

    Parameters
    ----------
    start : str
        Start date string (e.g. ``"2020-03"`` or ``"March 2020"``).
    end : str or None
        End date string, or ``None`` / ``"Present"``.

    Returns
    -------
    str
        Human-readable date range, e.g. ``"Mar 2020 – Present"``.
    """
    start_s = _safe(start) if start else ""
    end_s = _safe(end) if end else "Present"
    if start_s:
        return f"{start_s} – {end_s}"
    return end_s
