"""Google Gemini provider (via the native REST API -- no SDK dependency)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from backend.utils.llm.base import LLMProvider

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("GEMINI_API_KEY", "").strip() or None
        self.model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip()
        self.temperature: float = 0.2
        self.timeout: float = 45.0

    @property
    def available(self) -> bool:
        return bool(self.api_key) and self._http() is not None

    def chat_json(self, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        # Collapse the message list into a single user prompt (planning prompts
        # are single-shot; history lives in the frontend conversation log).
        prompt = "\n\n".join(
            f"{'System' if m.get('role') == 'system' else 'User'}: {m['content']}"
            for m in messages
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "responseMimeType": "application/json",
            },
        }
        url = f"{_GEMINI_BASE}/models/{self.model}:generateContent?key={self.api_key}"
        try:
            http = self._http()
            resp = http.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return self._parse_json(text)
        except Exception as exc:  # pragma: no cover - network dependent
            print(f"[GeminiProvider] request failed: {exc}")
            return None
