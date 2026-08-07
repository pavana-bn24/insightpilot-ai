"""LLM provider abstraction.

InsightPilot delegates planning and insight phrasing to an LLM provider, but
NEVER arithmetic. The default provider is Google Gemini; OpenAI and Groq are
supported through a shared OpenAI-compatible interface. Every provider exposes
the same minimal ``chat_json`` contract, so the rest of the system is provider
agnostic. With no API key configured, providers fall back to None and the
pipeline runs in deterministic mode.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


class LLMProvider(ABC):
    """Base class for an LLM chat provider."""

    name: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool:
        ...

    @abstractmethod
    def chat_json(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        """Send a conversation and return a parsed JSON object (or None)."""

    def _parse_json(self, raw: Optional[str]) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None

    def _http(self) -> Optional[Any]:
        return httpx if httpx is not None else None
