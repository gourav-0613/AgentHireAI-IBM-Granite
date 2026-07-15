"""
components package

Reusable Streamlit UI widgets used by pages/2_Analyzer.py.
Each component is a module with a single public render() function.
Components are purely presentational — they accept Pydantic models
and render Streamlit elements.  They do not call agents or write session state.

Modules:
    resume_preview   — render a structured ResumeProfile or TailoredResume card
    skill_gap_chart  — render a Plotly radar/bar chart from SkillGapReport
    keyword_badges   — render ATS keyword pills from ATSReport
    score_gauge      — render a Plotly match score gauge + breakdown table
"""
