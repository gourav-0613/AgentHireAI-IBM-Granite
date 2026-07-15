"""
tests/test_jd_analyzer.py

Unit tests for agents/jd_analyzer.py (Agent 2).

Test strategy:
    - Mock watsonx_client.generate() to return controlled JSON strings
    - Test happy path: well-formed JSON → validated JobDescription
    - Test that raw_text is preserved on the returned model
    - Test error handling: malformed JSON / schema mismatch raise ValueError

No real IBM API calls are made in these tests.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# TODO: Import run from agents.jd_analyzer
# TODO: Import JobDescription from models.job_description

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: Define @pytest.fixture `sample_jd_json` — dict matching JobDescription schema
# TODO: Define @pytest.fixture `sample_jd_text` — realistic JD string
#       (load from tests/fixtures/sample_jd.txt)

# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------

# TODO: test_run_returns_job_description
#   - Patch generate() → json.dumps(sample_jd_json)
#   - Assert result is a JobDescription instance

# TODO: test_raw_text_is_preserved
#   - Call run(sample_jd_text)
#   - Assert result.raw_text == sample_jd_text

# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------

# TODO: test_run_raises_on_malformed_json
# TODO: test_run_raises_on_schema_mismatch
