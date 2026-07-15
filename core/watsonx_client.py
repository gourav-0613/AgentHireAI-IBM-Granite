"""
core/watsonx_client.py

Singleton wrapper around the IBM Watson Machine Learning (Watsonx.ai) SDK.

Responsibilities:
    - Initialise a ``Model`` (ModelInference subclass) lazily on first call,
      using credentials sourced exclusively from ``config.settings``.
    - Expose a single ``generate()`` method consumed by all five agents.
    - Implement retry with exponential backoff for transient network errors.
    - Centralise request/response logging so individual agents stay clean.

All five agents import this singleton — no agent manages its own HTTP
connection::

    from core.watsonx_client import watsonx_client
    response_text = watsonx_client.generate(prompt=..., model_id=..., params=...)

The singleton is constructed lazily: the IBM SDK object is *not* created at
import time.  This allows the module to be imported freely during testing
without triggering credential validation.

Granite model responses follow the structure::

    response["results"][0]["generated_text"]
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from config.settings import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default generation parameters
# ---------------------------------------------------------------------------

#: Keys match the WML SDK's ``GenTextParamsMetaNames`` string constants.
#: Using string literals avoids importing the SDK at module level, which
#: would fail in test environments where the SDK's optional deps are absent.
_PARAM_MAX_NEW_TOKENS = "max_new_tokens"
_PARAM_MIN_NEW_TOKENS = "min_new_tokens"
_PARAM_TEMPERATURE = "temperature"
_PARAM_DECODING_METHOD = "decoding_method"
_PARAM_STOP_SEQUENCES = "stop_sequences"
_PARAM_REPETITION_PENALTY = "repetition_penalty"

_DECODING_GREEDY = "greedy"
_DECODING_SAMPLE = "sample"

_DEFAULT_PARAMS: dict[str, Any] = {
    _PARAM_DECODING_METHOD: _DECODING_GREEDY,
    _PARAM_MAX_NEW_TOKENS: 1024,
    _PARAM_MIN_NEW_TOKENS: 1,
    _PARAM_STOP_SEQUENCES: [],
    _PARAM_REPETITION_PENALTY: 1.1,
}


# ---------------------------------------------------------------------------
# WatsonxClient
# ---------------------------------------------------------------------------

class WatsonxClient:
    """
    Thin, singleton-pattern wrapper around the IBM WML ``Model`` class.

    The underlying SDK object is created lazily on the first ``generate``
    call so that importing this module in unit tests never triggers network
    or credential checks.

    Parameters
    ----------
    None — all configuration is read from ``config.settings.settings``.

    Raises
    ------
    RuntimeError
        Raised at first ``generate`` call if IBM credentials are not
        configured (i.e. ``settings.is_configured()`` returns False).
    """

    def __init__(self) -> None:
        # _models caches one Model instance per model_id to avoid re-auth
        self._models: dict[str, Any] = {}
        self._initialised: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Send *prompt* to Watsonx.ai and return the generated text string.

        Uses ``model_id`` (defaults to ``settings.model_generation``) and
        merges *params* with sensible defaults via ``_build_params``.

        Implements up to ``settings.max_retries`` attempts with exponential
        back-off on transient errors (connection timeouts, HTTP 5xx).

        Parameters
        ----------
        prompt : str
            The full prompt string to send to the model.
        model_id : str, optional
            Watsonx model identifier.  Defaults to
            ``settings.model_generation``.
        params : dict, optional
            Override or extend the default generation parameters.  Keys
            must be valid WML ``GenTextParamsMetaNames`` string values.

        Returns
        -------
        str
            The raw ``generated_text`` string from the first result.

        Raises
        ------
        RuntimeError
            If IBM Watsonx credentials are not configured, or if all retry
            attempts are exhausted without a successful response.
        ValueError
            If the API response is missing the expected
            ``results[0].generated_text`` field.
        """
        if not settings.is_configured():
            raise RuntimeError(
                "IBM Watsonx credentials are not configured.  "
                "Set IBM_WATSONX_API_KEY, IBM_WATSONX_URL, and "
                "IBM_WATSONX_PROJECT_ID in your environment or .env file."
            )

        resolved_model_id: str = model_id or settings.model_generation
        merged_params: dict[str, Any] = self._build_params(params or {})
        model = self._get_or_create_model(resolved_model_id, merged_params)

        last_exc: Optional[Exception] = None
        for attempt in range(1, settings.max_retries + 1):
            try:
                logger.debug(
                    "WatsonxClient.generate | model=%s | attempt=%d/%d | "
                    "prompt_chars=%d",
                    resolved_model_id,
                    attempt,
                    settings.max_retries,
                    len(prompt),
                )
                response: dict = model.generate(prompt=prompt, params=merged_params)
                generated_text = self._extract_text(response)
                logger.debug(
                    "WatsonxClient.generate | success | generated_chars=%d",
                    len(generated_text),
                )
                return generated_text

            except (RuntimeError, ValueError):
                # Non-retryable — re-raise immediately
                raise

            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < settings.max_retries:
                    wait = settings.retry_backoff_base ** (attempt - 1)
                    logger.warning(
                        "WatsonxClient.generate | transient error on attempt "
                        "%d/%d, retrying in %.1fs: %s",
                        attempt,
                        settings.max_retries,
                        wait,
                        exc,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "WatsonxClient.generate | all %d attempts failed: %s",
                        settings.max_retries,
                        exc,
                    )

        raise RuntimeError(
            f"Watsonx API call failed after {settings.max_retries} attempts.  "
            f"Last error: {last_exc}"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_or_create_model(
        self,
        model_id: str,
        params: dict[str, Any],
    ) -> Any:
        """
        Return a cached ``Model`` instance for *model_id*, creating one if
        it does not yet exist.

        Credentials are taken from ``config.settings`` at call time so that
        rotating credentials in tests (via environment patching) works
        correctly.

        Parameters
        ----------
        model_id : str
            Watsonx model identifier.
        params : dict
            Default generation params baked into the model object.

        Returns
        -------
        Model
            An initialised WML ``Model`` instance.
        """
        if model_id not in self._models:
            # Import lazily so the module can be imported without the full
            # WML dependency tree present (e.g. in unit-test environments).
            from ibm_watson_machine_learning.foundation_models import Model  # type: ignore[import]

            credentials: dict[str, str] = {
                "apikey": settings.watsonx_api_key,
                "url": settings.watsonx_url,
            }
            self._models[model_id] = Model(
                model_id=model_id,
                credentials=credentials,
                params=params,
                project_id=settings.watsonx_project_id,
            )
            logger.info(
                "WatsonxClient | initialised model %r for project %r",
                model_id,
                settings.watsonx_project_id,
            )

        return self._models[model_id]

    def _build_params(self, overrides: dict[str, Any]) -> dict[str, Any]:
        """
        Merge *overrides* with the module-level defaults.

        The caller's values take precedence over defaults.  This guarantees
        that ``max_new_tokens``, ``temperature``, ``decoding_method``, and
        ``stop_sequences`` are always present in the returned dict.

        Parameters
        ----------
        overrides : dict
            Caller-supplied generation parameters.

        Returns
        -------
        dict
            Merged parameter dict ready to pass to the WML SDK.
        """
        merged = dict(_DEFAULT_PARAMS)
        merged.update(overrides)
        return merged

    @staticmethod
    def _extract_text(response: dict) -> str:
        """
        Pull the generated text string out of the WML SDK response dict.

        Expected response shape::

            {
                "results": [
                    {
                        "generated_text": "<the text>",
                        "generated_token_count": <int>,
                        "stop_reason": "<reason>"
                    }
                ]
            }

        Parameters
        ----------
        response : dict
            Raw dict returned by ``Model.generate()``.

        Returns
        -------
        str
            The generated text content.

        Raises
        ------
        ValueError
            If the expected ``results[0].generated_text`` key path is absent.
        """
        try:
            return response["results"][0]["generated_text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(
                f"Unexpected Watsonx API response structure — "
                f"could not extract 'results[0].generated_text'.  "
                f"Raw response: {response!r}"
            ) from exc

    def flush_model_cache(self) -> None:
        """
        Clear the internal model cache.

        Useful in testing when credentials or settings change between test
        cases.  Not intended for production use.
        """
        self._models.clear()
        logger.debug("WatsonxClient | model cache flushed")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

watsonx_client = WatsonxClient()
