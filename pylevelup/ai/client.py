from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp

from pylevelup.config import Settings, get_settings
from pylevelup.logger import get_logger

logger = get_logger(__name__)

GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"


class AIError(Exception):
    pass


class AIUnavailable(AIError):
    pass


@dataclass(frozen=True)
class AIResult:
    text: str
    provider: str
    model: str


class AIClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._timeout = aiohttp.ClientTimeout(total=settings.ai_request_timeout_seconds)

    def is_available(self) -> bool:
        return bool(self._settings.gemini_api_key or self._settings.deepseek_api_key)

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 800,
        prefer: str = "gemini",
    ) -> AIResult:
        order: list[str] = []
        if prefer == "gemini":
            order = ["gemini", "deepseek"]
        elif prefer == "deepseek":
            order = ["deepseek", "gemini"]
        else:
            order = ["gemini", "deepseek"]
        last_error: Exception | None = None
        for provider in order:
            try:
                if provider == "gemini" and self._settings.gemini_api_key:
                    return await self._call_gemini(prompt, system, temperature, max_tokens)
                if provider == "deepseek" and self._settings.deepseek_api_key:
                    return await self._call_deepseek(prompt, system, temperature, max_tokens)
            except AIError as exc:
                logger.warning("ai_provider_failed", provider=provider, error=str(exc))
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise AIUnavailable("no ai provider configured")

    async def _call_gemini(
        self, prompt: str, system: str | None, temperature: float, max_tokens: int
    ) -> AIResult:
        api_key = self._settings.gemini_api_key
        if not api_key:
            raise AIUnavailable("gemini key missing")
        url = GEMINI_ENDPOINT.format(model=self._settings.gemini_model)
        parts: list[dict[str, Any]] = []
        if system:
            parts.append({"text": system})
        parts.append({"text": prompt})
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            try:
                async with session.post(url, json=payload, headers=headers) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status != 200:
                        raise AIError(f"gemini http {resp.status}: {data}")
            except TimeoutError as exc:
                raise AIError(f"gemini timeout: {exc}") from exc
            except aiohttp.ClientError as exc:
                raise AIError(f"gemini network: {exc}") from exc
        candidates = data.get("candidates") if isinstance(data, dict) else None
        if not candidates:
            raise AIError(f"gemini no candidates: {data}")
        candidate_parts = candidates[0].get("content", {}).get("parts", [])
        if not candidate_parts:
            raise AIError(f"gemini empty parts: {data}")
        text = "".join(p.get("text", "") for p in candidate_parts).strip()
        if not text:
            raise AIError("gemini empty text")
        return AIResult(text=text, provider="gemini", model=self._settings.gemini_model)

    async def _call_deepseek(
        self, prompt: str, system: str | None, temperature: float, max_tokens: int
    ) -> AIResult:
        api_key = self._settings.deepseek_api_key
        if not api_key:
            raise AIUnavailable("deepseek key missing")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self._settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            try:
                async with session.post(DEEPSEEK_ENDPOINT, json=payload, headers=headers) as resp:
                    data = await resp.json(content_type=None)
                    if resp.status != 200:
                        raise AIError(f"deepseek http {resp.status}: {data}")
            except TimeoutError as exc:
                raise AIError(f"deepseek timeout: {exc}") from exc
            except aiohttp.ClientError as exc:
                raise AIError(f"deepseek network: {exc}") from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise AIError(f"deepseek no choices: {data}")
        text = choices[0].get("message", {}).get("content", "").strip()
        if not text:
            raise AIError("deepseek empty text")
        return AIResult(text=text, provider="deepseek", model=self._settings.deepseek_model)


_client: AIClient | None = None
_lock = asyncio.Lock()


async def get_ai_client() -> AIClient:
    global _client
    async with _lock:
        if _client is None:
            _client = AIClient(get_settings())
        return _client
