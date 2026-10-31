"""
Gemini Provider - Google Gemini API implementation (google-genai SDK)
"""
import os
import time
from typing import List, Dict, Any, Optional

from google import genai
from google.genai import types

from .base_provider import BaseLLMProvider
from ..logger import setup_logger


logger = setup_logger(__name__)

_RETRYABLE_STATUS = {429, 503}
_MAX_ATTEMPTS = 3
_BACKOFF_SECONDS = (5, 15, 30)
# Lite first: separate free-tier daily quota from gemini-3.8-flash (often 20 req/day).
_FALLBACK_MODELS = ("gemini-3.5-flash", "gemini-3.8-flash")


class GeminiProvider(BaseLLMProvider):
    """Google Gemini LLM provider"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """
        Initialize Gemini provider.

        Args:
            api_key: Google API key. If None, reads from GOOGLE_API_KEY env var
            model: Model name to use. If None, uses default model

        Raises:
            ValueError: If API key is not provided and not in environment
        """
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError(
                "Google API key must be provided or set in GOOGLE_API_KEY environment variable"
            )

        super().__init__(api_key=api_key, model=model or self.default_model)

        self.client = genai.Client(api_key=self.api_key)
        logger.info(f"Gemini provider initialized with model: {self.model}")

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def default_model(self) -> str:
        return "gemini-3.5-flash-lite"

    def generate(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2000,
        temperature: float = 1.0,
        **kwargs
    ) -> str:
        """
        Generate a response using Gemini API.

        Args:
            messages: List of message dicts with 'role' and 'content' keys
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional Gemini-specific parameters

        Returns:
            Generated text response

        Raises:
            Exception: If API call fails
        """
        prompt = self._convert_messages_to_gemini_format(messages)
        config = types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            temperature=temperature,
        )

        last_error: Optional[Exception] = None
        for model_name in self._models_to_try():
            for attempt in range(_MAX_ATTEMPTS):
                try:
                    logger.debug(
                        f"Calling Gemini model={model_name} with {len(messages)} messages"
                        + (f" (attempt {attempt + 1}/{_MAX_ATTEMPTS})" if attempt else "")
                    )
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=config,
                    )
                    text = self._extract_text(response)
                    if text:
                        if model_name != self.model:
                            logger.info(f"Gemini succeeded using fallback model: {model_name}")
                        return text
                    raise Exception(self._empty_response_message(response))

                except Exception as e:
                    last_error = e
                    if self._is_model_unavailable(e):
                        logger.warning(
                            f"Gemini model {model_name} is not available ({e}); trying next model..."
                        )
                        break
                    if self._is_quota_exhausted(e):
                        logger.warning(
                            f"Gemini daily quota exhausted for {model_name}; "
                            "trying next model (no point retrying today)..."
                        )
                        break
                    if self._is_retryable(e) and attempt < _MAX_ATTEMPTS - 1:
                        wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                        logger.warning(
                            f"Gemini transient error on {model_name}: {e}; "
                            f"retrying in {wait}s..."
                        )
                        time.sleep(wait)
                        continue
                    logger.warning(f"Gemini failed on {model_name}: {e}")
                    break

        logger.error(f"Gemini API error after retries and fallbacks: {last_error}", exc_info=True)
        if last_error:
            raise last_error
        raise Exception("Gemini API call failed")

    def generate_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_tokens: int = 2000,
        max_iterations: int = 8,
        tool_handler: Optional[callable] = None,
        **kwargs
    ) -> str:
        """
        Generate a response with tool calling support.

        Args:
            messages: List of message dicts
            tools: List of tool definitions
            max_tokens: Maximum tokens in response
            max_iterations: Maximum tool use iterations
            tool_handler: Function to handle tool calls
            **kwargs: Additional Gemini-specific parameters

        Returns:
            Generated text response after tool interactions

        Raises:
            Exception: If generation fails
        """
        try:
            logger.debug(f"Calling Gemini API with tools, max_iterations={max_iterations}")
            return self.generate(messages, max_tokens=max_tokens, **kwargs)
        except Exception as e:
            logger.error(f"Gemini API error with tools: {str(e)}", exc_info=True)
            raise

    def _extract_text(self, response: Any) -> str:
        """Return response text if present."""
        if response is None:
            return ""
        text = getattr(response, "text", None)
        if text:
            return text.strip()
        return ""

    def _empty_response_message(self, response: Any) -> str:
        """Build a clear error when the model returns no usable text."""
        block_reason = None
        finish_reason = None
        try:
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                candidate = candidates[0]
                finish_reason = getattr(candidate, "finish_reason", None)
                safety = getattr(candidate, "safety_ratings", None)
                if safety:
                    block_reason = str(safety)
        except Exception:
            pass
        parts = ["No response text from Gemini"]
        if finish_reason is not None:
            parts.append(f"finish_reason={finish_reason}")
        if block_reason:
            parts.append(f"safety={block_reason}")
        prompt_feedback = getattr(response, "prompt_feedback", None)
        if prompt_feedback is not None:
            parts.append(f"prompt_feedback={prompt_feedback}")
        return "; ".join(parts)

    def _models_to_try(self):
        """Primary model first, then fallbacks when demand or availability blocks the call."""
        seen = set()
        for name in (self.model, *_FALLBACK_MODELS):
            if name and name not in seen:
                seen.add(name)
                yield name

    def _is_model_unavailable(self, error: Exception) -> bool:
        """True when this model name should be skipped (deprecated / not found)."""
        status = getattr(error, "status_code", None)
        if status == 404:
            return True
        message = str(error).lower()
        return "404" in message or "not_found" in message or "no longer available" in message

    def _is_quota_exhausted(self, error: Exception) -> bool:
        """Daily/per-model free-tier quota — switch model, do not backoff-retry."""
        message = str(error).lower()
        return (
            "quota exceeded" in message
            or "free_tier" in message
            or "limit exceeded" in message
            or "exceeded your current quota" in message
            or ("resource_exhausted" in message and "please retry in" in message)
        )

    def _is_retryable(self, error: Exception) -> bool:
        """True for short-lived rate limits and 503 overload only."""
        if self._is_model_unavailable(error) or self._is_quota_exhausted(error):
            return False
        message = str(error).lower()
        if "503" in message or "unavailable" in message or "high demand" in message:
            return True
        # Short RPM throttle (not daily quota)
        if "429" in message and "quota" not in message and "free_tier" not in message:
            return True
        status = getattr(error, "status_code", None)
        return status == 503

    def _convert_messages_to_gemini_format(self, messages: List[Dict[str, str]]) -> str:
        """
        Convert standard message format to a single prompt string.

        Args:
            messages: List of message dicts

        Returns:
            Formatted prompt string for Gemini
        """
        prompt_parts = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        return "\n\n".join(prompt_parts)
