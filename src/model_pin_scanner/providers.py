"""Pluggable model providers for the regress command.

Each provider turns a CompletionRequest into output text. HTTP providers talk to the
vendor APIs with the standard library only, through an injectable transport so tests
never touch the network.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

# (url, headers, body, timeout) -> (status, response body)
Transport = Callable[[str, Mapping[str, str], bytes, float], tuple[int, bytes]]

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504, 529})


class ProviderError(RuntimeError):
    """A provider could not produce a completion."""


@dataclass(frozen=True)
class CompletionRequest:
    model: str
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    prompt_id: str = ""


class Provider(Protocol):
    name: str

    def complete(self, request: CompletionRequest) -> str: ...


def urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https endpoints
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except urllib.error.URLError as exc:
        raise ProviderError(f"network error: {exc.reason}") from exc


class _HTTPProvider:
    name = "http"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        transport: Transport = urllib_transport,
        timeout: float = 120.0,
        retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ProviderError(f"{self.name}: API key is empty")
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._timeout = timeout
        self._retries = retries
        self._sleep = sleep

    def _post(self, url: str, headers: Mapping[str, str], payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        all_headers = {"content-type": "application/json", **headers}
        for attempt in range(self._retries + 1):
            status, raw = self._transport(url, all_headers, body, self._timeout)
            if status in RETRY_STATUSES and attempt < self._retries:
                self._sleep(2.0**attempt)
                continue
            break
        if not 200 <= status < 300:
            snippet = raw[:300].decode("utf-8", errors="replace")
            raise ProviderError(f"{self.name}: HTTP {status}: {snippet}")
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            raise ProviderError(f"{self.name}: response was not JSON") from exc
        if not isinstance(doc, dict):
            raise ProviderError(f"{self.name}: unexpected response shape")
        return doc


class OpenAIProvider(_HTTPProvider):
    """Chat Completions API. No temperature is sent: reasoning models reject it."""

    name = "openai"

    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1", **kw: object) -> None:
        super().__init__(api_key, base_url, **kw)  # type: ignore[arg-type]

    def complete(self, request: CompletionRequest) -> str:
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})
        doc = self._post(
            f"{self._base}/chat/completions",
            {"authorization": f"Bearer {self._key}"},
            {"model": request.model, "messages": messages, "max_completion_tokens": request.max_tokens},
        )
        try:
            content = doc["choices"][0]["message"]["content"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("openai: response had no choices[0].message.content") from exc
        return content if isinstance(content, str) else ""


class AnthropicProvider(_HTTPProvider):
    """Messages API."""

    name = "anthropic"
    API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com", **kw: object) -> None:
        super().__init__(api_key, base_url, **kw)  # type: ignore[arg-type]

    def complete(self, request: CompletionRequest) -> str:
        payload: dict[str, object] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            payload["system"] = request.system
        doc = self._post(
            f"{self._base}/v1/messages",
            {"x-api-key": self._key, "anthropic-version": self.API_VERSION},
            payload,
        )
        blocks = doc.get("content")
        if not isinstance(blocks, list):
            raise ProviderError("anthropic: response had no content list")
        return "".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text")


class GoogleProvider(_HTTPProvider):
    """Gemini API generateContent."""

    name = "google"

    def __init__(
        self, api_key: str, base_url: str = "https://generativelanguage.googleapis.com/v1beta", **kw: object
    ) -> None:
        super().__init__(api_key, base_url, **kw)  # type: ignore[arg-type]

    def complete(self, request: CompletionRequest) -> str:
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {"maxOutputTokens": request.max_tokens},
        }
        if request.system:
            payload["systemInstruction"] = {"parts": [{"text": request.system}]}
        doc = self._post(
            f"{self._base}/models/{quote(request.model, safe='.-_')}:generateContent",
            {"x-goog-api-key": self._key},
            payload,
        )
        try:
            parts = doc["candidates"][0]["content"]["parts"]  # type: ignore[index]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("google: response had no candidates[0].content.parts") from exc
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))


class MockProvider:
    """Canned responses: {model: {prompt_id: text}}. Used for tests, demos and dry runs."""

    name = "mock"

    def __init__(self, responses: Mapping[str, Mapping[str, str]]) -> None:
        self._responses = responses

    def complete(self, request: CompletionRequest) -> str:
        by_prompt = self._responses.get(request.model)
        if by_prompt is None:
            raise ProviderError(f"mock: no responses for model {request.model}")
        if request.prompt_id not in by_prompt:
            raise ProviderError(f"mock: no response for prompt {request.prompt_id!r} on {request.model}")
        return by_prompt[request.prompt_id]


_ENV_KEYS = {
    "openai": ("OPENAI_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
    "google": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
}
_BASE_URL_ENV = {"openai": "OPENAI_BASE_URL", "anthropic": "ANTHROPIC_BASE_URL", "google": "GEMINI_BASE_URL"}
_CLASSES: dict[str, type[_HTTPProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "google": GoogleProvider,
}


def guess_provider(model: str) -> str:
    m = model.lower()
    if m.startswith("claude-"):
        return "anthropic"
    if m.startswith("gemini-"):
        return "google"
    if m.startswith(("gpt-", "chatgpt-")) or re.match(r"^o\d", m) or m.startswith("ft:"):
        return "openai"
    raise ProviderError(f"cannot tell which provider serves {model!r}; pass --provider")


def from_env(name: str, env: Mapping[str, str] | None = None, transport: Transport = urllib_transport) -> _HTTPProvider:
    """Build a real provider from environment variables. Raises if the key is missing."""
    env = os.environ if env is None else env
    if name not in _CLASSES:
        raise ProviderError(f"unknown provider {name!r}")
    key = next((env[k] for k in _ENV_KEYS[name] if env.get(k)), "")
    if not key:
        raise ProviderError(f"{name}: set {' or '.join(_ENV_KEYS[name])} to make real calls")
    kwargs: dict[str, object] = {"transport": transport}
    base = env.get(_BASE_URL_ENV[name])
    if base:
        if not base.startswith("https://"):
            raise ProviderError(f"{_BASE_URL_ENV[name]} must be an https URL")
        kwargs["base_url"] = base
    return _CLASSES[name](key, **kwargs)  # type: ignore[arg-type]
