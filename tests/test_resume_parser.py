"""
tests/test_resume_parser.py

Unit tests for agents/resume_parser.py (Agent 1).

Test strategy:
    - Mock watsonx_client.generate() to return controlled JSON strings
    - Test the happy path: well-formed JSON → validated ResumeProfile
    - Test the _extract_json helper: markdown fence stripping
    - Test error handling: malformed JSON raises ValueError
    - Test error handling: JSON missing required fields raises ValidationError
    - Test enrichment fields: seniority_level, dominant_domain,
      total_years_experience are correctly parsed

No real IBM API calls are made in these tests.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# TODO: Import run from agents.resume_parser
# TODO: Import _extract_json from agents.resume_parser (if made importable)
# TODO: Import ResumeProfile from models.resume

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: Define a @pytest.fixture `sample_resume_json` returning a dict that
#       matches the ResumeProfile schema with realistic synthetic data

# TODO: Define a @pytest.fixture `sample_resume_text` returning a realistic
#       plain-text resume string (loaded from tests/fixtures/ or inline)

# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------

# TODO: test_run_returns_resume_profile
#   - Patch watsonx_client.generate to return json.dumps(sample_resume_json)
#   - Call run(sample_resume_text)
#   - Assert result is a ResumeProfile instance
#   - Assert result.full_name matches fixture value

# TODO: test_seniority_level_parsed
#   - Patch generate() with JSON containing seniority_level = "Senior"
#   - Assert result.seniority_level == "Senior"

# ---------------------------------------------------------------------------
# Tests — _extract_json helper
# ---------------------------------------------------------------------------

# TODO: test_extract_json_strips_markdown_fences
#   - Input: "```json\n{\"key\": \"value\"}\n```"
#   - Expected: {"key": "value"}

# TODO: test_extract_json_plain_json
#   - Input: '{"key": "value"}'
#   - Expected: {"key": "value"}

# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------

# TODO: test_run_raises_on_malformed_json
#   - Patch generate() to return "not valid json"
#   - Assert run() raises ValueError

# TODO: test_run_raises_on_schema_mismatch
#   - Patch generate() to return JSON missing required field "full_name"
#   - Assert run() raises ValueError (wrapping ValidationError)
