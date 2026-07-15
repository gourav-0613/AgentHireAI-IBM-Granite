"""
config/settings.py

Centralised application configuration.

All environment variables, IBM Watsonx model identifiers, and inference
hyperparameters are defined here.  No other module should read os.environ
directly — always import from this module.

Usage:
    from config.settings import settings
    url = settings.watsonx_url
"""

from __future__ import annotations

import os
from typing import Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment — load .env before reading any variable
# ---------------------------------------------------------------------------

load_dotenv()


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class Settings:
    """
    Centralised, immutable-at-runtime configuration for AgentHireAI.

    All values are resolved once at import time from environment variables
    (or their defaults).  Access the pre-built singleton via::

        from config.settings import settings

    Attributes
    ----------
    watsonx_api_key : str
        IBM Cloud API key.  Read from ``IBM_WATSONX_API_KEY``.
    watsonx_url : str
        Watsonx.ai endpoint URL.  Read from ``IBM_WATSONX_URL``.
        Defaults to the Dallas production endpoint.
    watsonx_project_id : str
        Watson Studio project ID.  Read from ``IBM_WATSONX_PROJECT_ID``.
    model_extraction : str
        Granite model used for structured-extraction tasks (Agents 1 & 2).
    model_generation : str
        Granite model used for generation/tailoring tasks (Agents 3–5).
    max_tokens_extraction : int
        ``max_new_tokens`` cap for extraction calls.
    max_tokens_generation : int
        ``max_new_tokens`` cap for generation calls.
    temperature_extraction : float
        Sampling temperature for extraction (low → deterministic).
    temperature_generation : float
        Sampling temperature for generation (higher → creative).
    pdf_max_size_mb : int
        Maximum allowed PDF upload size in megabytes.
    """

    # ------------------------------------------------------------------
    # IBM Watsonx credentials
    # ------------------------------------------------------------------

    watsonx_api_key: str = os.getenv("IBM_WATSONX_API_KEY", "")
    watsonx_url: str = os.getenv(
        "IBM_WATSONX_URL",
        "https://us-south.ml.cloud.ibm.com",
    )
    watsonx_project_id: str = os.getenv("IBM_WATSONX_PROJECT_ID", "")

    # ------------------------------------------------------------------
    # Model identifiers
    # ------------------------------------------------------------------

    model_extraction: str = os.getenv(
        "WATSONX_MODEL_EXTRACTION",
        "ibm/granite-3-8b-instruct",
    )
    model_generation: str = os.getenv(
        "WATSONX_MODEL_GENERATION",
        "ibm/granite-20b-multilingual",
    )

    # ------------------------------------------------------------------
    # Inference hyperparameters
    # ------------------------------------------------------------------

    max_tokens_extraction: int = int(
        os.getenv("WATSONX_MAX_TOKENS_EXTRACTION", "1500")
    )
    max_tokens_generation: int = int(
        os.getenv("WATSONX_MAX_TOKENS_GENERATION", "3000")
    )
    temperature_extraction: float = float(
        os.getenv("WATSONX_TEMPERATURE_EXTRACTION", "0.1")
    )
    temperature_generation: float = float(
        os.getenv("WATSONX_TEMPERATURE_GENERATION", "0.7")
    )

    # ------------------------------------------------------------------
    # Application limits
    # ------------------------------------------------------------------

    pdf_max_size_mb: int = int(os.getenv("PDF_MAX_SIZE_MB", "5"))

    # ------------------------------------------------------------------
    # Retry policy (used by watsonx_client)
    # ------------------------------------------------------------------

    max_retries: int = int(os.getenv("WATSONX_MAX_RETRIES", "3"))
    retry_backoff_base: float = float(
        os.getenv("WATSONX_RETRY_BACKOFF_BASE", "2.0")
    )

    def is_configured(self) -> bool:
        """Return True if the three mandatory credentials are all non-empty."""
        return bool(
            self.watsonx_api_key
            and self.watsonx_url
            and self.watsonx_project_id
        )

    def __repr__(self) -> str:  # pragma: no cover
        key_preview = (
            self.watsonx_api_key[:6] + "***"
            if self.watsonx_api_key
            else "<not set>"
        )
        return (
            f"Settings("
            f"url={self.watsonx_url!r}, "
            f"project_id={self.watsonx_project_id!r}, "
            f"api_key={key_preview!r}"
            f")"
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

settings = Settings()
