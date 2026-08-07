"""OpenAI-compatible provider (OpenAI and Groq share the same chat API)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from backend.utils.llm.base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    def __init__(self, provider: str) -> None:
        self.name = provider
        self.api_key: Optional[str] = os.getenv(f"{provider.upper()}_API_KEY", "").strip() or None
        self.base_url: str = (
            os.getenv(f"{provider.upper()}_BASE_URL", self._default_base(provider))
            .rstrip("/")
        )
        self.model: str = os.getenv(f"{provider.upper()}_MODEL", self._default_model(provider))
        self.temperature: float = 0.2
        self.timeout: float = 45.0

    @staticmethod
    def _default_base(provider: str) -> str:
        if provider == "groq":
            return "https://api.groq.com/openai/v1"
        return "https://api.openai.com/v1"

    @staticmethod
    def _default_model(provider: str) -> str:
        if provider == "groq":
            return "llama-3.3-70b-versatile"
        return "gpt-4o-mini"

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self._http() is not None

    def chat_json(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
        }
        try:
            http = self._http()
            resp = http.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_json(data["choices"][0]["message"]["content"])
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[{self.name.capitalize()}Provider] request failed: {exc}")
            return None
