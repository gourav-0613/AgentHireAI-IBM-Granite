"""
config/prompts.py

Single source of truth for all IBM Granite prompt templates.

Every LLM prompt used by every agent lives here as a module-level string
constant.  Agents import the constant they need and format it with their
runtime variables — no prompt string should be defined inside an agent module.

Naming convention:
    <AGENT_NAME>_PROMPT  — the primary prompt template for that agent
    <AGENT_NAME>_SYSTEM  — optional system message if the model supports it

Template variables use Python str.format() style: {variable_name}
The Pydantic JSON schema for each agent's output model is injected at
runtime via the {schema} placeholder.

Usage:
    from config.prompts import RESUME_PARSER_PROMPT
    filled = RESUME_PARSER_PROMPT.format(schema=..., resume_text=...)
"""

# ---------------------------------------------------------------------------
# Agent 1 — Resume Parser
# ---------------------------------------------------------------------------

# TODO: Define RESUME_PARSER_PROMPT
#   Template variables: {schema}, {resume_text}
#   Instruction: expert resume parser, extract structured data,
#                return JSON matching the provided schema exactly,
#                null for missing fields, no extra fields, no markdown fences.

RESUME_PARSER_PROMPT: str = ""

# ---------------------------------------------------------------------------
# Agent 2 — JD Analyzer
# ---------------------------------------------------------------------------

# TODO: Define JD_ANALYZER_PROMPT
#   Template variables: {schema}, {jd_text}
#   Instruction: expert job description analyst, decompose JD into structured
#                components, return JSON matching schema.

JD_ANALYZER_PROMPT: str = ""

# ---------------------------------------------------------------------------
# Agent 3 — Skill Gap Analyzer (fuzzy matching only)
# ---------------------------------------------------------------------------

# TODO: Define SKILL_GAP_FUZZY_PROMPT
#   Template variables: {candidate_skills}, {required_skills}
#   Instruction: identify semantically equivalent skills across the two lists
#                (e.g. "React" == "React.js"), return JSON list of matched pairs.
#                Exact matching is handled deterministically before this prompt runs.

SKILL_GAP_FUZZY_PROMPT: str = ""

# ---------------------------------------------------------------------------
# Agent 4 — ATS Keyword Optimizer
# ---------------------------------------------------------------------------

# TODO: Define ATS_OPTIMIZER_PROMPT
#   Template variables: {schema}, {jd_text}, {candidate_skills}
#   Instruction: extract ATS-critical keywords and phrases from the JD,
#                assign a relevance weight (0.0–1.0) to each,
#                flag whether each keyword is already present in the candidate's
#                profile, return JSON matching schema.

ATS_OPTIMIZER_PROMPT: str = ""

# ---------------------------------------------------------------------------
# Agent 5 — Resume Tailor
# ---------------------------------------------------------------------------

# TODO: Define RESUME_TAILOR_PROMPT
#   Template variables: {schema}, {resume_json}, {jd_json},
#                       {skill_gap_json}, {ats_keywords}
#   Instruction: expert resume writer, rewrite summary and experience bullets
#                to align with the JD and embed ATS keywords naturally,
#                return JSON matching schema, preserve truthfulness.

RESUME_TAILOR_PROMPT: str = ""
