"""
agents/resume_parser.py

Agent 1 — Resume Parser.

Responsibility
--------------
Convert a plain-text resume string into a validated :class:`~models.resume.ResumeProfile`
by making a single structured-extraction call to IBM Granite through
:data:`~core.watsonx_client.watsonx_client`.

Pipeline position
-----------------
    PDF bytes
        → ``core.pdf_reader.extract_text_from_pdf``  (Step 4)
        → ``resume_text: str``
        → **this module** (Agent 1)
        → ``ResumeProfile``
        → downstream agents 2–5

Public API
----------
.. code-block:: python

    from agents.resume_parser import run
    profile: ResumeProfile = run(resume_text)

Internal helpers (exported for unit-test access)
-------------------------------------------------
.. code-block:: python

    from agents.resume_parser import _extract_json, _build_prompt
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from config.settings import settings
from core.watsonx_client import watsonx_client
from models.resume import ResumeProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

# The template is self-contained here because config/prompts.py is currently
# a stub with empty strings (to be filled in a later step).  The schema
# placeholder is intentionally verbose so Granite produces a complete object
# even for sparse resumes.

_PROMPT_TEMPLATE: str = """\
You are an expert resume parser. Your task is to extract all structured \
information from the resume text below and return it as a single JSON object \
that exactly matches the provided JSON Schema.

Rules:
- Return ONLY the JSON object — no markdown fences, no commentary, no extra keys.
- Use null (JSON null) for any field that is absent or cannot be determined.
- For list fields, return an empty array [] if there are no items.
- Do not fabricate or infer information that is not present in the resume.
- The "seniority_level" field must be one of: "Junior", "Mid", "Senior", "Lead", or null.
- The "total_years_experience" field must be a number (float), not a string.
- All date fields (start_date, end_date) must follow "YYYY-MM" or "Month YYYY" format.

JSON Schema:
{schema}

Resume Text:
\"\"\"
{resume_text}
\"\"\"

JSON output:"""

# Generation parameters tuned for deterministic structured extraction.
# Low temperature + greedy decoding → minimal hallucination.
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


def run(resume_text: str) -> ResumeProfile:
    """
    Parse *resume_text* and return a validated :class:`~models.resume.ResumeProfile`.

    This function performs a single Granite LLM call to extract every
    structured field defined in :class:`~models.resume.ResumeProfile`.  The
    full Pydantic JSON Schema is injected into the prompt so the model
    understands the exact output contract.

    Parameters
    ----------
    resume_text : str
        Cleaned plain-text content of the candidate's resume, as produced by
        ``core.pdf_reader.extract_text_from_pdf``.

    Returns
    -------
    ResumeProfile
        A fully validated Pydantic model instance populated with all
        extractable information from *resume_text*.

    Raises
    ------
    ValueError
        If *resume_text* is empty or whitespace-only.
        If the LLM returns malformed JSON that cannot be decoded.
        If the decoded JSON does not satisfy the ``ResumeProfile`` schema
        (wraps :class:`pydantic.ValidationError`).
    RuntimeError
        Propagated from :data:`~core.watsonx_client.watsonx_client` when the
        IBM Watsonx API is unreachable or credentials are not configured.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError(
            "resume_text must be a non-empty string.  "
            "Ensure the PDF was extracted successfully before calling this agent."
        )

    schema: str = _schema_json()
    prompt: str = _build_prompt(resume_text=resume_text, schema=schema)

    logger.info(
        "resume_parser.run | starting extraction | "
        "model=%s | resume_chars=%d",
        settings.model_extraction,
        len(resume_text),
    )

    raw_response: str = watsonx_client.generate(
        prompt=prompt,
        model_id=settings.model_extraction,
        params=_EXTRACTION_PARAMS,
    )

    logger.debug(
        "resume_parser.run | raw response received | chars=%d",
        len(raw_response),
    )

    parsed_dict: dict[str, Any] = _extract_json(raw_response)
    profile: ResumeProfile = _validate(parsed_dict)

    logger.info(
        "resume_parser.run | extraction complete | "
        "name=%r | seniority=%r | years_exp=%s",
        profile.personal_info.full_name,
        profile.seniority_level,
        profile.total_years_experience,
    )

    return profile


# ---------------------------------------------------------------------------
# Internal helpers  (exported so tests can import them directly)
# ---------------------------------------------------------------------------


def _build_prompt(resume_text: str, schema: str) -> str:
    """
    Render the extraction prompt template with *resume_text* and *schema*.

    Parameters
    ----------
    resume_text : str
        Plain-text resume content.
    schema : str
        JSON Schema string (compact JSON) generated from
        :meth:`~models.resume.ResumeProfile.model_json_schema`.

    Returns
    -------
    str
        The fully rendered prompt string ready to send to Granite.
    """
    return _PROMPT_TEMPLATE.format(
        schema=schema,
        resume_text=resume_text,
    )


def _schema_json() -> str:
    """
    Return the compact JSON Schema for :class:`~models.resume.ResumeProfile`.

    The schema is generated fresh from the Pydantic model on every call so
    that any model changes are automatically reflected in the prompt without
    requiring manual updates.

    Returns
    -------
    str
        Compact (no extra whitespace) JSON Schema string.
    """
    return json.dumps(ResumeProfile.model_json_schema(), separators=(",", ":"))


def _extract_json(raw: str) -> dict[str, Any]:
    """
    Extract and decode a JSON object from *raw* LLM output.

    Handles the three most common Granite response formats:

    1. **Plain JSON** — the model returned the object directly.
    2. **Fenced JSON** — the model wrapped the object in a markdown
       code block (e.g. ``\\`\\`\\`json ... \\`\\`\\``).
    3. **Prefixed JSON** — the model emitted some preamble text before the
       opening brace; the first ``{`` is used as the start of the object.

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
            "Cannot extract a JSON resume profile."
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

    # Strategy 2: find the first '{' and last '}' to isolate the JSON object.
    # This handles models that emit preamble text before the object.
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


def _validate(data: dict[str, Any]) -> ResumeProfile:
    """
    Validate *data* against the :class:`~models.resume.ResumeProfile` schema.

    Parameters
    ----------
    data : dict
        Decoded JSON dict as returned by :func:`_extract_json`.

    Returns
    -------
    ResumeProfile
        A fully validated Pydantic model instance.

    Raises
    ------
    ValueError
        Wraps :class:`pydantic.ValidationError` with a human-readable message
        that includes the field-level error details.
    """
    try:
        return ResumeProfile.model_validate(data)
    except ValidationError as exc:
        # Summarise the Pydantic errors into a readable message so callers
        # (and the UI) can surface a meaningful explanation.
        error_summary: str = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(
            f"LLM response failed ResumeProfile validation — {error_summary}.  "
            f"Raw data keys: {list(data.keys())}"
        ) from exc
