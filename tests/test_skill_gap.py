"""
tests/test_skill_gap.py

Unit tests for agents/skill_gap_analyzer.py (Agent 3).

Test strategy:
    - Test _exact_match with controlled skill lists (no Granite call needed)
    - Test _normalise with edge cases (casing, punctuation, extra whitespace)
    - Test _fuzzy_match by mocking watsonx_client.generate()
    - Test the full run() end-to-end with mocked Granite
    - Test edge cases: empty skill lists, all skills matched, no skills matched

The hybrid approach (deterministic first, Granite for fuzzy only) means
the majority of test cases require no mocking at all.
"""

import pytest
from unittest.mock import patch, MagicMock

# TODO: Import run, _exact_match, _normalise from agents.skill_gap_analyzer
# TODO: Import ResumeProfile from models.resume
# TODO: Import JobDescription from models.job_description
# TODO: Import SkillGapReport from models.analysis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: Define @pytest.fixture `profile_with_skills` — ResumeProfile with known skills list
# TODO: Define @pytest.fixture `jd_with_requirements` — JobDescription with known required/preferred

# ---------------------------------------------------------------------------
# Tests — _normalise
# ---------------------------------------------------------------------------

# TODO: test_normalise_lowercases
# TODO: test_normalise_strips_whitespace
# TODO: test_normalise_handles_empty_list

# ---------------------------------------------------------------------------
# Tests — _exact_match (pure Python, no mocking)
# ---------------------------------------------------------------------------

# TODO: test_exact_match_identifies_matches
# TODO: test_exact_match_identifies_missing_critical
# TODO: test_exact_match_identifies_missing_preferred
# TODO: test_exact_match_empty_required

# ---------------------------------------------------------------------------
# Tests — run() end-to-end
# ---------------------------------------------------------------------------

# TODO: test_run_returns_skill_gap_report
#   - Mock Granite fuzzy call
#   - Assert result is SkillGapReport instance with expected populated fields

# TODO: test_run_all_skills_matched
#   - Profile skills ⊇ JD required skills
#   - Assert missing_critical is empty
