"""
Phase 22 — AI Configuration.

Environment-driven configuration for the AI semantic layer.
Safe defaults — AI is optional and never breaks core functionality.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AIConfig:
    """AI provider configuration from environment variables."""

    enabled: bool = False
    provider: str = "test"  # "test" | "openai" | "anthropic" | "mistral" | "disabled"
    model: str = "gpt-4o-mini"  # used by the OpenAI-compatible provider only
    timeout_seconds: int = 30
    max_input_tokens: int = 4096
    max_output_tokens: int = 2048
    temperature: float = 0.0

    @classmethod
    def from_env(cls) -> "AIConfig":
        return cls(
            enabled=os.getenv("AI_ENABLED", "false").lower() == "true",
            provider=os.getenv("AI_PROVIDER", "test"),
            model=os.getenv("AI_MODEL", "gpt-4o-mini"),
            timeout_seconds=int(os.getenv("AI_TIMEOUT_SECONDS", "30")),
            max_input_tokens=int(os.getenv("AI_MAX_INPUT_TOKENS", "4096")),
            max_output_tokens=int(os.getenv("AI_MAX_OUTPUT_TOKENS", "2048")),
            temperature=float(os.getenv("AI_TEMPERATURE", "0.0")),
        )


# Singleton config
_config: AIConfig | None = None


def get_ai_config() -> AIConfig:
    global _config
    if _config is None:
        _config = AIConfig.from_env()
    return _config


def get_ai_provider(config: AIConfig | None = None):
    """
    Return the AI provider instance selected by configuration.

    - provider == "anthropic"  -> AnthropicLLMProvider (native Claude SDK)
    - provider == "openai"     -> RealLLMProvider (OpenAI-compatible API)
    - provider == "mistral"    -> MistralLLMProvider (Mistral OpenAI-compatible API)
    - anything else / disabled -> TestAIProvider (deterministic, non-LLM)

    Real providers self-report ``AI_UNAVAILABLE`` when no credential is
    present, so a mis-set env never silently produces fabricated results.
    """
    config = config or get_ai_config()

    if config.enabled and config.provider == "anthropic":
        from app.services.ai_anthropic_provider import AnthropicLLMProvider

        return AnthropicLLMProvider()

    if config.enabled and config.provider == "mistral":
        from app.services.ai_mistral_provider import MistralLLMProvider

        return MistralLLMProvider()

    if config.enabled and config.provider == "openai":
        from app.services.ai_real_provider import RealLLMProvider

        return RealLLMProvider()

    from app.services.ai_test_provider import TestAIProvider

    return TestAIProvider()


def is_real_llm_configured(config: AIConfig | None = None) -> bool:
    """True only when a real LLM provider is selected AND has a usable credential."""
    config = config or get_ai_config()
    if not config.enabled or config.provider not in ("openai", "anthropic", "mistral"):
        return False
    provider = get_ai_provider(config)
    return bool(getattr(provider, "_is_configured", lambda: False)())
