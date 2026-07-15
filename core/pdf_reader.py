"""
core/pdf_reader.py

Converts an uploaded PDF binary into a clean, normalised text string
suitable for passing to the Resume Parser agent.

Responsibilities:
    - Accept raw PDF bytes (e.g. from Streamlit's ``file_uploader``)
    - Validate the byte payload before attempting extraction
    - Extract text from every page using PyMuPDF (``fitz``), preserving
      top-to-bottom reading order within each page
    - Delegate text normalisation to ``utils.text_cleaner.clean_text``
    - Raise descriptive, typed exceptions on all failure modes

No OCR is performed — this module only extracts embedded text streams.
Scanned PDFs (image-only) will raise ``PDFExtractionError``.

Usage::

    from core.pdf_reader import extract_text_from_pdf
    raw_text = extract_text_from_pdf(pdf_bytes)
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import fitz  # PyMuPDF

from utils.text_cleaner import clean_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class PDFReadError(ValueError):
    """
    Raised when the supplied bytes cannot be opened as a valid PDF.

    Inherits from ``ValueError`` so callers can catch it as a broad
    input-validation error without depending on this module's exception
    hierarchy.
    """


class PDFExtractionError(ValueError):
    """
    Raised when the PDF opens successfully but yields no extractable text.

    Typical causes:
    - All pages are scanned images (no embedded text stream)
    - The PDF is encrypted / access-restricted
    - All pages are blank
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_text_from_pdf(
    pdf_bytes: bytes,
    *,
    max_size_bytes: Optional[int] = None,
) -> str:
    """
    Extract and normalise all text from a PDF supplied as raw bytes.

    Pages are processed in document order.  Text from each page is
    concatenated with a double newline separator to preserve section
    boundaries, then passed through ``utils.text_cleaner.clean_text``
    before being returned.

    Parameters
    ----------
    pdf_bytes : bytes
        Raw binary content of the PDF file.  Must be a valid PDF byte
        stream — passing file-like objects or paths is not supported.
    max_size_bytes : int, optional
        If provided, a ``PDFReadError`` is raised when ``len(pdf_bytes)``
        exceeds this value.  Allows callers to enforce upload-size limits
        without re-reading the ``settings`` object here.

    Returns
    -------
    str
        Cleaned, normalised text extracted from all pages of the PDF.

    Raises
    ------
    PDFReadError
        If *pdf_bytes* is empty, too large (when *max_size_bytes* is set),
        or cannot be parsed as a PDF document.
    PDFExtractionError
        If the PDF opens successfully but contains no readable text — e.g.
        a scanned / image-only document or a fully encrypted file.

    Examples
    --------
    >>> with open("resume.pdf", "rb") as fh:
    ...     text = extract_text_from_pdf(fh.read())
    """
    # ------------------------------------------------------------------
    # Input guards
    # ------------------------------------------------------------------

    if not pdf_bytes:
        raise PDFReadError("PDF bytes are empty.  Please upload a non-empty PDF file.")

    if max_size_bytes is not None and len(pdf_bytes) > max_size_bytes:
        size_mb = len(pdf_bytes) / (1024 * 1024)
        limit_mb = max_size_bytes / (1024 * 1024)
        raise PDFReadError(
            f"PDF file size ({size_mb:.1f} MB) exceeds the "
            f"{limit_mb:.0f} MB limit.  Please upload a smaller file."
        )

    # ------------------------------------------------------------------
    # Open the PDF
    # ------------------------------------------------------------------

    try:
        doc: fitz.Document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFReadError(
            f"Could not open the uploaded file as a PDF document.  "
            f"Ensure the file is a valid, unencrypted PDF.  "
            f"Detail: {exc}"
        ) from exc

    page_count = len(doc)
    logger.debug("pdf_reader | opened PDF | pages=%d", page_count)

    if page_count == 0:
        doc.close()
        raise PDFExtractionError(
            "The uploaded PDF contains no pages.  "
            "Please upload a valid resume PDF."
        )

    # ------------------------------------------------------------------
    # Extract text page by page
    # ------------------------------------------------------------------

    page_texts: list[str] = []
    for page_number in range(page_count):
        try:
            page: fitz.Page = doc.load_page(page_number)
            # "text" mode returns plain text in reading order, top-to-bottom
            page_text: str = page.get_text("text")  # type: ignore[call-overload]
        except Exception as exc:
            logger.warning(
                "pdf_reader | failed to read page %d/%d: %s",
                page_number + 1,
                page_count,
                exc,
            )
            continue
        finally:
            pass  # fitz pages are not context managers; page lifetime is per-call

        if page_text.strip():
            page_texts.append(page_text)

    doc.close()

    logger.debug(
        "pdf_reader | extracted text from %d/%d pages",
        len(page_texts),
        page_count,
    )

    # ------------------------------------------------------------------
    # Validate and clean
    # ------------------------------------------------------------------

    if not page_texts:
        raise PDFExtractionError(
            "No readable text was found in the uploaded PDF.  "
            "The file may be a scanned image or access-restricted.  "
            "Please upload a text-based PDF resume."
        )

    raw_text: str = "\n\n".join(page_texts)
    cleaned: str = clean_text(raw_text)

    if not cleaned:
        raise PDFExtractionError(
            "Text extraction succeeded but the result was empty after "
            "normalisation.  Please check your PDF and try again."
        )

    logger.info(
        "pdf_reader | extraction complete | raw_chars=%d | clean_chars=%d",
        len(raw_text),
        len(cleaned),
    )
    return cleaned
