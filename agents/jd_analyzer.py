"""
agents/jd_analyzer.py

Agent 2 — Job Description Analyzer.

Responsibility
--------------
Convert a raw job description string (from LinkedIn, Indeed, Naukri,
Greenhouse, Lever, Workday, or plain text) into a validated
:class:`~models.job_description.JobDescription` by making a single
structured-extraction call to IBM Granite through
:data:`~core.watsonx_client.watsonx_client`.

The agent handles the full variety of real-world JD formats:

- Markdown formatting (``**bold**``, ``# headings``, ``- bullets``)
- HTML remnants (``<br>``, ``&amp;``, ``<p>``, ``<li>``)
- Noisy copy-paste artefacts (excess whitespace, emoji, unicode dashes)
- Mixed required / preferred skill sections
- Inline seniority signals ("5+ years", "Senior", "L5", "IC3")

Pipeline position
-----------------
::

    User pastes raw JD text
        → ``jd_text: str``
        → **this module** (Agent 2)
        → ``JobDescription``
        → Agent 3 (Skill Gap Analyzer)
        → Agent 4 (ATS Keyword Optimizer)
        → Agent 5 (Resume Tailor)

Public API
----------
.. code-block:: python

    from agents.jd_analyzer import run
    jd: JobDescription = run(jd_text)

Internal helpers (exported for unit-test access)
-------------------------------------------------
.. code-block:: python

    from agents.jd_analyzer import _extract_json, _build_prompt, _schema_json, _validate

Design note — ``raw_text`` field
---------------------------------
:class:`~models.job_description.JobDescription` carries a required
``raw_text`` field that preserves the original unmodified JD text for
downstream agents and the UI.  Granite is **not** asked to echo this field
back (that would waste tokens and risk truncation).  Instead, ``run()``
injects ``raw_text`` into the validated dict before constructing the model.
The schema passed to Granite has ``raw_text`` stripped from its ``required``
list and its ``properties`` so the model is not confused by a field it should
not produce.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from config.settings import settings
from core.watsonx_client import watsonx_client
from models.job_description import JobDescription

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

# The template is self-contained here because config/prompts.py is currently
# a stub with empty strings (to be filled in a later step).  The prompt is
# deliberately explicit about handling noisy / real-world JD formatting so
# Granite produces clean, complete JSON even from messy LinkedIn copy-pastes.

_PROMPT_TEMPLATE: str = """\
You are an expert job description analyst. Your task is to decompose the job \
description below into a single structured JSON object that exactly matches \
the provided JSON Schema.

Rules:
- Return ONLY the JSON object — no markdown fences, no commentary, no extra keys.
- Use null (JSON null) for any field that is absent or cannot be determined.
- For list fields, return an empty array [] if there are no items.
- Do not fabricate information that is not present in the job description.
- Ignore HTML tags, markdown formatting, emoji, and copy-paste artefacts in the input.
- "required_skills": extract must-have / required skills. Each item is an object \
with "skill" (string) and optional "context" (string, e.g. "5+ years of Python").
- "preferred_skills": extract nice-to-have / preferred / bonus skills. Same object shape.
- "experience_requirements": extract structured experience requirements. Each item has \
"description" (string), optional "min_years" (number), optional "max_years" (number), \
optional "domain" (string).
- "company_signals": infer company values, culture cues, or mission signals (e.g. \
"fast-paced startup", "data-driven culture", "remote-first"). Return as plain strings.
- "responsibilities": extract key day-to-day duties as plain strings.
- "seniority_level": infer from title and requirements (e.g. "Junior", "Mid-level", \
"Senior", "Staff", "Principal", "Lead", "Director"). Use null if unclear.
- "employment_type": e.g. "Full-time", "Part-time", "Contract", "Internship". \
Use null if not stated.
- "location": the work location as stated, e.g. "Remote", "New York, NY", \
"Hybrid — London". Use null if not stated.

JSON Schema:
{schema}

Job Description:
\"\"\"
{jd_text}
\"\"\"

JSON output:"""

# Generation parameters — identical strategy to Agent 1: greedy decoding at
# low temperature for maximum determinism in structured extraction.
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


def run(jd_text: str) -> JobDescription:
    """
    Analyze *jd_text* and return a validated :class:`~models.job_description.JobDescription`.

    This function performs a single Granite LLM call to decompose every
    extractable field defined in :class:`~models.job_description.JobDescription`.
    The Pydantic JSON Schema (with ``raw_text`` removed — see module docstring)
    is injected into the prompt so the model understands the exact output
    contract.  ``raw_text`` is then attached to the decoded dict before
    Pydantic validation, ensuring the field is always populated with the
    original unmodified input.

    Accepts any real-world JD format including markdown, HTML remnants,
    bullet points, and noisy copy-paste text from LinkedIn, Indeed, Naukri,
    Greenhouse, Lever, or Workday.

    Parameters
    ----------
    jd_text : str
        The raw job description text as supplied by the user.

    Returns
    -------
    JobDescription
        A fully validated Pydantic model instance populated with all
        extractable information from *jd_text*.

    Raises
    ------
    ValueError
        If *jd_text* is empty or whitespace-only.
        If the LLM returns malformed JSON that cannot be decoded.
        If the decoded JSON does not satisfy the ``JobDescription`` schema
        (wraps :class:`pydantic.ValidationError`).
    RuntimeError
        Propagated from :data:`~core.watsonx_client.watsonx_client` when the
        IBM Watsonx API is unreachable or credentials are not configured.
    """
    if not jd_text or not jd_text.strip():
        raise ValueError(
            "jd_text must be a non-empty string.  "
            "Paste the full job description text before calling this agent."
        )

    schema: str = _schema_json()
    prompt: str = _build_prompt(jd_text=jd_text, schema=schema)

    logger.info(
        "jd_analyzer.run | starting extraction | model=%s | jd_chars=%d",
        settings.model_extraction,
        len(jd_text),
    )

    raw_response: str = watsonx_client.generate(
        prompt=prompt,
        model_id=settings.model_extraction,
        params=_EXTRACTION_PARAMS,
    )

    logger.debug(
        "jd_analyzer.run | raw response received | chars=%d",
        len(raw_response),
    )

    parsed_dict: dict[str, Any] = _extract_json(raw_response)

    # Inject the original JD text into the decoded dict so that the required
    # ``raw_text`` field is always present without asking the LLM to echo it.
    parsed_dict["raw_text"] = jd_text

    jd: JobDescription = _validate(parsed_dict)

    logger.info(
        "jd_analyzer.run | extraction complete | "
        "role=%r | company=%r | seniority=%r | "
        "required_skills=%d | preferred_skills=%d",
        jd.role_title,
        jd.company_name,
        jd.seniority_level,
        len(jd.required_skills),
        len(jd.preferred_skills),
    )

    return jd


# ---------------------------------------------------------------------------
# Internal helpers  (exported so tests can import them directly)
# ---------------------------------------------------------------------------


def _build_prompt(jd_text: str, schema: str) -> str:
    """
    Render the extraction prompt template with *jd_text* and *schema*.

    Parameters
    ----------
    jd_text : str
        Raw job description text (any format).
    schema : str
        Compact JSON Schema string generated by :func:`_schema_json` —
        the ``raw_text`` field has already been removed.

    Returns
    -------
    str
        The fully rendered prompt string ready to send to Granite.
    """
    return _PROMPT_TEMPLATE.format(
        schema=schema,
        jd_text=jd_text,
    )


def _schema_json() -> str:
    """
    Return a compact JSON Schema for :class:`~models.job_description.JobDescription`
    with the ``raw_text`` field removed.

    ``raw_text`` is a required field that holds the original user input.
    Asking Granite to produce it would waste tokens and risk truncation or
    hallucination.  The field is injected programmatically in :func:`run`
    after the LLM call, so it is stripped from the schema passed to the model.

    The schema is generated fresh from the Pydantic model on every call so
    that any model changes are automatically reflected in the prompt without
    requiring manual updates.

    Returns
    -------
    str
        Compact (no extra whitespace) JSON Schema string, ``raw_text``
        excluded.
    """
    raw_schema: dict[str, Any] = copy.deepcopy(JobDescription.model_json_schema())

    # Remove raw_text from properties so the LLM does not try to produce it.
    raw_schema.get("properties", {}).pop("raw_text", None)

    # Remove raw_text from the required list (Pydantic may include it there).
    if "required" in raw_schema:
        raw_schema["required"] = [
            field for field in raw_schema["required"] if field != "raw_text"
        ]

    return json.dumps(raw_schema, separators=(",", ":"))


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
            "Cannot extract a JSON job description."
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


def _validate(data: dict[str, Any]) -> JobDescription:
    """
    Validate *data* against the :class:`~models.job_description.JobDescription` schema.

    Parameters
    ----------
    data : dict
        Decoded JSON dict as returned by :func:`_extract_json`, with
        ``raw_text`` already injected by :func:`run`.

    Returns
    -------
    JobDescription
        A fully validated Pydantic model instance.

    Raises
    ------
    ValueError
        Wraps :class:`pydantic.ValidationError` with a human-readable message
        that includes the field-level error details.
    """
    try:
        return JobDescription.model_validate(data)
    except ValidationError as exc:
        # Summarise the Pydantic errors into a readable message so callers
        # (and the UI) can surface a meaningful explanation.
        error_summary: str = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ValueError(
            f"LLM response failed JobDescription validation — {error_summary}.  "
            f"Raw data keys: {list(data.keys())}"
        ) from exc
