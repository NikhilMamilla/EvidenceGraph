"""
Phase 23/24 — Real LLM Provider Adapter (Mistral).

Mistral AI exposes an **OpenAI-compatible** Chat Completions API
(``https://api.mistral.ai/v1``), so this provider inherits the entire
prompt-building / JSON-parsing / reference-validation pipeline from
``ai_real_provider.RealLLMProvider`` and only swaps three things:

  * the credential source        — ``MISTRAL_API_KEY`` (or ``AI_API_KEY``)
  * the default base URL         — ``https://api.mistral.ai/v1``
  * the default model            — ``mistral-large-latest``

Selected when ``AI_ENABLED=true`` and ``AI_PROVIDER=mistral``.

Like every real provider it degrades to ``AI_UNAVAILABLE`` when no credential
is configured or the ``openai`` package is missing — it never fabricates a
result and the deterministic EvidenceGraph evaluator always retains final
authority (the AI layer can never upgrade a verdict to ``SUPPORTED``).
"""

from __future__ import annotations

import os

from app.services.ai_real_provider import RealLLMProvider

# Prompt versions are inherited from ai_real_provider (kept in one place).

DEFAULT_MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
# mistral-small-latest is available on the free tier; mistral-large-latest
# requires a paid subscription tier (403 tier_not_allowed otherwise).
DEFAULT_MISTRAL_MODEL = "mistral-small-latest"


class MistralLLMProvider(RealLLMProvider):
    """
    Real LLM provider for Mistral AI via its OpenAI-compatible endpoint.

    Requires:
    - AI_ENABLED=true
    - AI_PROVIDER=mistral
    - MISTRAL_API_KEY=<valid key>   (falls back to AI_API_KEY)

    Optional:
    - AI_MISTRAL_MODEL     (default: mistral-small-latest — free-tier friendly;
                            set mistral-large-latest on a paid tier for quality)
    - MISTRAL_BASE_URL     (default: https://api.mistral.ai/v1)
    - AI_TIMEOUT_SECONDS   (default: 30)
    - AI_MAX_OUTPUT_TOKENS (default: 2048)
    """

    provider_name = "REAL_LLM_MISTRAL"

    def __init__(self) -> None:
        super().__init__()
        self.api_key = os.getenv("MISTRAL_API_KEY", "") or os.getenv("AI_API_KEY", "")
        self.model = os.getenv("AI_MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL)
        self.base_url = os.getenv("MISTRAL_BASE_URL", DEFAULT_MISTRAL_BASE_URL)

    def _is_configured(self) -> bool:
        # Mistral API keys have no fixed prefix (unlike ``sk-`` / ``sk-ant-``),
        # so we only require a non-empty key that is not an Anthropic key.
        return bool(self.api_key) and not self.api_key.startswith("sk-ant-")
