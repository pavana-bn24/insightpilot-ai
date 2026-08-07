"""Provider selection factory.

Configuration is environment-only:

    LLM_PROVIDER=gemini|openai|groq|none      (default: gemini)
    GEMINI_API_KEY / GEMINI_MODEL
    OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
    GROQ_API_KEY / GROQ_BASE_URL / GROQ_MODEL
"""
from __future__ import annotations

import os
from typing import Optional

from backend.utils.llm.base import LLMProvider
from backend.utils.llm.gemini import GeminiProvider
from backend.utils.llm.openai_compat import OpenAICompatProvider


def build_provider(provider: Optional[str] = None) -> LLMProvider:
    """Instantiate the configured provider (or a no-op fallback).

    Args:
        provider: override for the ``LLM_PROVIDER`` env var.

    Returns:
        A provider instance. If its key is missing, ``available`` is False and
        the pipeline falls back to deterministic planning.
    """
    choice = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
    if choice == "openai":
        return OpenAICompatProvider("openai")
    if choice == "groq":
        return OpenAICompatProvider("groq")
    if choice == "none":
        return _NoopProvider()
    # Default: Gemini (spec requirement)
    return GeminiProvider()


class _NoopProvider(LLMProvider):
    """Deliberately offline provider used when LLM_PROVIDER=none."""

    name = "none"

    @property
    def available(self) -> bool:
        return False

    def chat_json(self, messages):  # type: ignore[override]
        return None


def provider_status() -> dict:
    """Health info about the configured provider for the /api/health endpoint."""
    prov = build_provider()
    return {
        "provider": prov.name,
        "llm_available": prov.available,
        "llm_mode": "llm" if prov.available else "deterministic",
    }


current_provider = build_provider()
