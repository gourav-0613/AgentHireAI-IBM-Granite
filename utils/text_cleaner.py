"""
utils/text_cleaner.py

Normalises raw text extracted from PDF resumes before it is passed to agents.

PDF extraction libraries (even PyMuPDF) produce artefacts that degrade
LLM prompt quality:
    - Excess whitespace / newlines from column layout detection
    - Ligature characters (ﬁ, ﬂ) not in standard Unicode
    - Invisible control characters
    - Repeated header/footer text from page breaks
    - Non-breaking spaces (\\xa0) and soft hyphens (\\xad)

Responsibilities:
    - clean_text(raw: str) -> str:   primary normalisation pipeline
    - Each transformation is a separate private function for testability

Usage:
    from utils.text_cleaner import clean_text
    cleaned = clean_text(raw_pdf_text)
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_text(raw: str) -> str:
    """
    Run the full normalisation pipeline on *raw* text extracted from a PDF.

    Transformations applied in order:

    1. NFKC Unicode normalisation — resolves compatibility equivalents and
       decomposes composed characters.
    2. Ligature replacement — converts typographic ligatures (ﬁ, ﬂ, …) to
       their plain ASCII equivalents so tokenisers handle them correctly.
    3. Control-character removal — strips invisible Unicode control / format
       characters while keeping structurally meaningful ``\\n`` and ``\\t``.
    4. Whitespace collapse — normalises runs of blank lines, multiple spaces,
       and trailing/leading whitespace per line.

    Parameters
    ----------
    raw : str
        The raw string as returned by a PDF extraction library.

    Returns
    -------
    str
        The cleaned, normalised text string.
    """
    text = _normalise_unicode(raw)
    text = _replace_ligatures(text)
    text = _remove_control_characters(text)
    text = _collapse_whitespace(text)
    return text


# ---------------------------------------------------------------------------
# Private cleaning functions
# ---------------------------------------------------------------------------

def _normalise_unicode(text: str) -> str:
    """
    Apply NFKC normalisation to *text*.

    NFKC decomposes compatibility characters (e.g. ﬁ→fi handled by Unicode
    itself for some code points) and recomposes canonical forms.  It also
    converts non-breaking spaces (U+00A0) and soft hyphens (U+00AD) to their
    standard equivalents.

    Parameters
    ----------
    text : str
        Input string.

    Returns
    -------
    str
        NFKC-normalised string.
    """
    return unicodedata.normalize("NFKC", text)


def _replace_ligatures(text: str) -> str:
    """
    Replace common typographic ligature characters with ASCII equivalents.

    Many PDF fonts encode ligatures as single code points in the private-use
    range or the Alphabetic Presentation Forms block (U+FB00–U+FB06).  These
    confuse tokenisers and keyword matchers.

    Parameters
    ----------
    text : str
        Input string (already NFKC-normalised).

    Returns
    -------
    str
        String with ligatures replaced by their ASCII multi-character forms.
    """
    _LIGATURES: dict[str, str] = {
        "\uFB00": "ff",   # ﬀ
        "\uFB01": "fi",   # ﬁ
        "\uFB02": "fl",   # ﬂ
        "\uFB03": "ffi",  # ﬃ
        "\uFB04": "ffl",  # ﬄ
        "\uFB05": "st",   # ﬅ
        "\uFB06": "st",   # ﬆ
    }
    for ligature, replacement in _LIGATURES.items():
        text = text.replace(ligature, replacement)
    return text


def _remove_control_characters(text: str) -> str:
    """
    Strip invisible Unicode control and format characters from *text*.

    Characters in Unicode general categories ``Cc`` (Other, Control) and
    ``Cf`` (Other, Format) are removed, *except* for the newline (``\\n``)
    and horizontal tab (``\\t``) characters which carry structural meaning
    in resume text.

    Parameters
    ----------
    text : str
        Input string.

    Returns
    -------
    str
        String with control/format characters removed.
    """
    result: list[str] = []
    for ch in text:
        if ch in ("\n", "\t"):
            result.append(ch)
            continue
        cat = unicodedata.category(ch)
        if cat not in ("Cc", "Cf"):
            result.append(ch)
    return "".join(result)


def _collapse_whitespace(text: str) -> str:
    """
    Normalise whitespace throughout *text*.

    Steps:
    - Strip leading and trailing whitespace from every individual line.
    - Replace runs of multiple spaces or tabs on a single line with a
      single space.
    - Replace three or more consecutive blank lines with exactly two newlines
      (one blank line separator).
    - Strip leading and trailing whitespace from the full string.

    Parameters
    ----------
    text : str
        Input string.

    Returns
    -------
    str
        Whitespace-collapsed string.
    """
    # Normalise each line: strip edges, collapse internal spaces/tabs
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    normalised = "\n".join(lines)

    # Collapse 3+ consecutive newlines (i.e. 2+ blank lines) → 2 newlines
    normalised = re.sub(r"\n{3,}", "\n\n", normalised)

    return normalised.strip()
