"""
core package

Deterministic infrastructure modules used by agents and pages.
None of these modules contain AI/LLM logic — they are pure utility layers.

Modules:
    watsonx_client  — singleton IBM Watsonx.ai API wrapper
    pdf_reader      — PDF binary → cleaned text
    pdf_generator   — TailoredResume → ATS-friendly PDF bytes
    scorer          — deterministic ATS match score calculator
    session_state   — Streamlit session state schema and reset helpers
"""
