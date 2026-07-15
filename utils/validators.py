"""
utils/validators.py

Input guard helpers used by pages/2_Analyzer.py before passing data
to any agent or core module.

Validates:
    - PDF file upload: type, size, non-empty content
    - Job description text: minimum length, not just whitespace

All functions raise ValueError with a user-friendly message on failure.
They return None on success so callers can use a simple try/except pattern
and surface the error message directly in the Streamlit UI via st.error().

Usage:
    from utils.validators import validate_pdf_upload, validate_jd_text
    try:
        validate_pdf_upload(uploaded_file)
    except ValueError as e:
        st.error(str(e))
        st.stop()
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_JD_CHARACTERS: int = 100
MAX_JD_CHARACTERS: int = 10_000
ALLOWED_MIME_TYPES: tuple[str, ...] = ("application/pdf",)
ALLOWED_EXTENSIONS: tuple[str, ...] = (".pdf",)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_pdf_upload(uploaded_file: Any) -> None:
    """
    Validate a Streamlit ``UploadedFile`` object as a resume PDF.

    Checks performed (in order):
        1. File is not None.
        2. File name ends with ``.pdf`` (case-insensitive).
        3. MIME type is ``application/pdf``.
        4. File size does not exceed ``settings.pdf_max_size_mb`` MB.

    Parameters
    ----------
    uploaded_file : streamlit.runtime.uploaded_file_manager.UploadedFile
        The object returned by ``st.file_uploader``.

    Returns
    -------
    None
        Returns ``None`` on success.

    Raises
    ------
    ValueError
        With a user-friendly message if any check fails.
    """
    if uploaded_file is None:
        raise ValueError("No file uploaded. Please upload a PDF resume.")

    # Extension check
    filename: str = getattr(uploaded_file, "name", "") or ""
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise ValueError(
            f"Invalid file type: '{filename}'. "
            "Only PDF files are accepted. Please upload a .pdf resume."
        )

    # MIME type check
    mime_type: str = getattr(uploaded_file, "type", "") or ""
    if mime_type and mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(
            f"Unexpected MIME type '{mime_type}'. "
            "Please upload a valid PDF file (application/pdf)."
        )

    # Size check
    max_bytes: int = settings.pdf_max_size_mb * 1024 * 1024
    file_size: int = getattr(uploaded_file, "size", 0) or 0
    if file_size > max_bytes:
        size_mb = file_size / (1024 * 1024)
        raise ValueError(
            f"File is too large ({size_mb:.1f} MB). "
            f"Maximum allowed size is {settings.pdf_max_size_mb} MB. "
            "Please compress or reduce the resume to under "
            f"{settings.pdf_max_size_mb} MB."
        )

    logger.debug(
        "validators.validate_pdf_upload | ok | file=%r | size=%d bytes",
        filename,
        file_size,
    )


def validate_jd_text(jd_text: str) -> None:
    """
    Validate raw job description text before analysis.

    Checks performed (in order):
        1. ``jd_text`` is not None and not empty after stripping.
        2. Stripped length >= ``MIN_JD_CHARACTERS`` (100).
        3. Stripped length <= ``MAX_JD_CHARACTERS`` (10 000).

    Parameters
    ----------
    jd_text : str
        Raw job description text provided by the user.

    Returns
    -------
    None
        Returns ``None`` on success.

    Raises
    ------
    ValueError
        With a user-friendly message if any check fails.
    """
    if not jd_text or not jd_text.strip():
        raise ValueError(
            "Job description is empty. "
            "Please paste the full job posting text before running the analysis."
        )

    stripped: str = jd_text.strip()

    if len(stripped) < MIN_JD_CHARACTERS:
        raise ValueError(
            f"Job description is too short ({len(stripped)} characters). "
            f"Please provide at least {MIN_JD_CHARACTERS} characters so the "
            "AI agents have enough context to perform an accurate analysis."
        )

    if len(stripped) > MAX_JD_CHARACTERS:
        raise ValueError(
            f"Job description is too long ({len(stripped):,} characters). "
            f"Please trim it to under {MAX_JD_CHARACTERS:,} characters. "
            "You can paste only the key sections (skills, responsibilities, requirements)."
        )

    logger.debug(
        "validators.validate_jd_text | ok | chars=%d", len(stripped)
    )
