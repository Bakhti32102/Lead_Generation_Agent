"""
Unified LLM client.
Supports: OpenAI, Anthropic, Google Gemini, Groq.
All providers share a common interface.
"""

from __future__ import annotations

import json
import logging
import time
import random
from typing import Any, Dict, List, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Configurable LLM client with a unified chat interface."""

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = (provider or settings.llm.provider).lower()
        self.model = model or settings.llm.model
        self.api_key = api_key or settings.llm.api_key
        self._client: Any = None

        if not self.api_key:
            logger.warning("LLM API key is not configured. LLM calls will fail.")
            return

        self._init_client()

    def _init_client(self) -> None:
        """Lazy-init the provider-specific client."""
        if self.provider in ("openai",):
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
        elif self.provider in ("anthropic",):
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key)
        elif self.provider in ("gemini", "google", "google-generativeai"):
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self._client = genai
        elif self.provider in ("groq",):
            from groq import Groq
            self._client = Groq(api_key=self.api_key)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and self._client is not None

    # Maximum number of retries for transient 429 / rate-limit errors.
    # Bounded to avoid hammering the provider.  Each retry doubles the
    # base delay plus jitter, so total wait is well under 60 seconds.
    MAX_RETRIES = 3

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        """Send chat messages and return the assistant response text.

        Retries up to MAX_RETRIES times on rate-limit (429) errors with
        bounded exponential backoff and jitter.  Other errors propagate
        immediately.
        """
        if not self.is_configured:
            raise RuntimeError("LLM client is not configured. Check LLM_API_KEY.")

        last_exc: Optional[Exception] = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if self.provider in ("openai",):
                    return self._chat_openai(messages, temperature, max_tokens)
                elif self.provider in ("anthropic",):
                    return self._chat_anthropic(messages, temperature, max_tokens)
                elif self.provider in ("gemini", "google", "google-generativeai"):
                    return self._chat_gemini(messages, temperature, max_tokens)
                elif self.provider in ("groq",):
                    return self._chat_groq(messages, temperature, max_tokens)
                else:
                    raise ValueError(f"Unsupported provider: {self.provider}")
            except Exception as e:
                last_exc = e
                if self._is_rate_limit(e) and attempt < self.MAX_RETRIES:
                    delay = self._backoff_delay(attempt, e)
                    logger.warning(
                        f"LLM rate limit ({self.provider}/{self.model}), "
                        f"attempt {attempt + 1}/{self.MAX_RETRIES}, "
                        f"retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    continue
                # Non-retryable error or retries exhausted
                logger.error(f"LLM call failed ({self.provider}/{self.model}): {e}")
                raise
        # Should not reach here, but safety:
        raise last_exc  # type: ignore[misc]

    @staticmethod
    def _is_rate_limit(exc: Exception) -> bool:
        """Check whether an exception represents a rate-limit (429) error."""
        msg = str(exc).lower()
        # Groq 429: "Rate limit reached"
        # OpenAI 429: "rate_limit_exceeded" or "429"
        # Anthropic 429: "rate_limit_error"
        # Generic: "429", "too many requests", "rate limit"
        return (
            "429" in msg
            or "rate limit" in msg
            or "too many requests" in msg
            or "rate_limit" in msg
            or "tpm" in msg
        )

    @staticmethod
    def _backoff_delay(attempt: int, exc: Exception) -> float:
        """Compute bounded exponential backoff delay with jitter.

        Base delay doubles each attempt: 2s, 4s, 8s.
        Jitter adds ±25% randomization to avoid thundering herd.
        Capped at 30s total.
        """
        base = 2 ** (attempt + 1)  # 2, 4, 8
        jitter = base * 0.25 * (2 * random.random() - 1)  # ±25%
        delay = min(base + jitter, 30.0)

        # If the provider specifies a retry-after, honour it
        msg = str(exc).lower()
        # Groq sometimes includes: "Please retry after X seconds"
        import re
        match = re.search(r"retry after (\d+\.?\d*)", msg)
        if match:
            provider_delay = float(match.group(1))
            delay = min(max(delay, provider_delay), 30.0)

        return delay

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        """Convenience method: system + user prompt → response text."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens)

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> Any:
        """Generate a JSON-structured response. Returns parsed dict/list."""
        response_text = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._parse_json(response_text)

    def _parse_json(self, text: str) -> Any:
        """Robustly extract JSON from LLM response text."""
        text = text.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Try extracting JSON from markdown code blocks
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        elif "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        # Try finding JSON-like content between first { or [ and last } or ]
        for open_ch, close_ch in [("{", "}"), ("[", "]")]:
            if open_ch in text and close_ch in text:
                start = text.index(open_ch)
                end = text.rindex(close_ch) + 1
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}...")

    # ---- Provider-specific implementations ----
    # These raise raw provider exceptions.  The retry logic in chat()
    # catches 429 / rate-limit errors and retries with backoff.

    def _chat_openai(
        self, messages: List[Dict], temperature: float, max_tokens: int
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""

    def _chat_anthropic(
        self, messages: List[Dict], temperature: float, max_tokens: int
    ) -> str:
        # Anthropic requires system as separate param
        system_msg = ""
        user_msgs = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_msgs.append(m)

        response = self._client.messages.create(
            model=self.model,
            system=system_msg,
            messages=user_msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content[0].text if response.content else ""

    def _chat_gemini(
        self, messages: List[Dict], temperature: float, max_tokens: int
    ) -> str:
        model = self._client.GenerativeModel(self.model)

        # Build conversation history
        history = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            history.append({"role": role, "parts": [m["content"]]})

        chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
        response = chat.send_message(
            history[-1]["parts"][0] if history else "",
            generation_config=self._client.types.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return response.text or ""

    def _chat_groq(
        self, messages: List[Dict], temperature: float, max_tokens: int
    ) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Module-level singleton (lazy init)
# ---------------------------------------------------------------------------
_llm_client: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    """Get or create the global LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
