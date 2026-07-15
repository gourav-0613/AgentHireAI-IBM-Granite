"""
tests/test_scorer.py

Unit tests for core/scorer.py (deterministic ATS Match Score).

This is the most important test file in the project.
The scorer is the only module with a correctness guarantee — same inputs
must always produce the same output.  Full branch coverage is required.

Test strategy:
    - No mocking required (scorer makes no external calls)
    - Test each of the four score signals in isolation
    - Test the weighted combination formula
    - Test _seniority_signal all cases: exact, adjacent, mismatch, None inputs
    - Test edge cases: empty skill lists, zero keyword weights, division-by-zero guards
    - Test score is clamped to [0.0, 100.0]
    - Test score is rounded to 1 decimal place
"""

import pytest

# TODO: Import calculate_score, ScoreResult from core.scorer
# TODO: Import _seniority_signal from core.scorer (if made importable)
# TODO: Import ResumeProfile from models.resume
# TODO: Import JobDescription from models.job_description
# TODO: Import SkillGapReport, ATSReport, KeywordWeight from models.analysis

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# TODO: Define @pytest.fixture `perfect_match_inputs` — all four models configured
#       so that the expected score is 100.0

# TODO: Define @pytest.fixture `zero_match_inputs` — all four models configured
#       so that the expected score is 0.0

# TODO: Define @pytest.fixture `partial_match_inputs` — known expected score (e.g. 74.5)
#       to test the weighted formula exactly

# ---------------------------------------------------------------------------
# Tests — _seniority_signal
# ---------------------------------------------------------------------------

# TODO: test_seniority_exact_match            → 1.0
# TODO: test_seniority_adjacent_up            → 0.5  (e.g. Mid vs Senior)
# TODO: test_seniority_adjacent_down          → 0.5  (e.g. Senior vs Mid)
# TODO: test_seniority_mismatch               → 0.0  (e.g. Junior vs Lead)
# TODO: test_seniority_none_candidate         → 0.5  (benefit of the doubt)
# TODO: test_seniority_none_jd                → 0.5
# TODO: test_seniority_both_none              → 0.5

# ---------------------------------------------------------------------------
# Tests — full score calculation
# ---------------------------------------------------------------------------

# TODO: test_perfect_match_score_is_100
# TODO: test_zero_match_score_is_0
# TODO: test_partial_match_weighted_formula   — verify arithmetic exactly
# TODO: test_score_is_rounded_to_one_decimal
# TODO: test_empty_required_skills_no_division_error
# TODO: test_empty_keywords_no_division_error
# TODO: test_score_result_has_breakdown_dict
