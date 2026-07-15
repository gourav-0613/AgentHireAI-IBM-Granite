"""
tests/test_ats_optimizer.py

Unit tests for agents/ats_optimizer.py (Agent 4).

Test strategy:
    - Mock watsonx_client.generate() to return controlled ATSReport JSON
    - Test happy path: valid JSON → ATSReport with KeywordWeight entries
    - Test that present_in_resume is correctly flagged based on profile skills
    - Test error handling: malformed JSON / schema mismatch raise ValueError

No real IBM API calls are made in these tests.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

# TODO: Import run from agents.ats_optimizer
# TODO: Import ATSReport, KeywordWeight from models.analysis
# TODO: Import ResumeProfile from models.resume
# TODO: Import JobDescription from models.job_description

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: Define @pytest.fixture `sample_ats_json` — dict matching ATSReport schema
# TODO: Define @pytest.fixture `sample_profile`   — ResumeProfile with known skills
# TODO: Define @pytest.fixture `sample_jd`        — JobDescription instance

# ---------------------------------------------------------------------------
# Tests — happy path
# ---------------------------------------------------------------------------

# TODO: test_run_returns_ats_report
#   - Patch generate() → valid ATSReport JSON
#   - Assert result is ATSReport with non-empty priority_keywords

# TODO: test_keyword_weight_within_range
#   - Assert all keyword weights are between 0.0 and 1.0

# ---------------------------------------------------------------------------
# Tests — error handling
# ---------------------------------------------------------------------------

# TODO: test_run_raises_on_malformed_json
# TODO: test_run_raises_on_schema_mismatch
