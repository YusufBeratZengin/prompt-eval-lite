"""Model providers. HTTP uses urllib only; API keys come from environment variables."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


class ProviderError(RuntimeError):
    """A model call failed (network, HTTP status, malformed response, configuration)."""


class Provider(ABC):
    name = "provider"

    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> str:
        """Return the model's text reply."""

    @property
    def label(self) -> str:
        return self.name


class MockProvider(Provider):
    """Deterministic provider for tests and demos.

    ``rules`` are checked in order against the prompt. A rule has ``match`` (substring)
    or ``regex``, and either ``reply`` or ``replies`` (cycled per call, which makes
    flaky behaviour reproducible). Without a matching rule, ``default`` is returned,
    or ``mock: <prompt>`` when no default is set.
    """

    name = "mock"

    def __init__(
        self,
        rules: list[dict[str, Any]] | None = None,
        default: str | None = None,
        model: str = "mock",
    ) -> None:
        self.rules = rules or []
        self.default = default
        self.model = model
        self._calls: list[int] = [0] * len(self.rules)
        for rule in self.rules:
            if "reply" not in rule and "replies" not in rule:
                raise ProviderError("mock rule needs 'reply' or 'replies'")
            if "match" not in rule and "regex" not in rule:
                raise ProviderError("mock rule needs 'match' or 'regex'")

    def complete(self, prompt: str, system: str | None = None) -> str:
        for i, rule in enumerate(self.rules):
            hit = (
                rule["match"] in prompt
                if "match" in rule
                else re.search(rule["regex"], prompt) is not None
            )
            if not hit:
                continue
            if "replies" in rule:
                replies = rule["replies"]
                reply = replies[self._calls[i] % len(replies)]
            else:
                reply = rule["reply"]
            self._calls[i] += 1
            return str(reply)
        return self.default if self.default is not None else f"mock: {prompt}"


class _HttpProvider(Provider):
    def __init__(self, base_url: str, model: str, timeout: float, temperature: float | None):
        parsed = urlparse(base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ProviderError(f"base_url must be an http(s) URL: {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    def _post(self, path: str, payload: dict[str, Any], headers: dict[str, str]) -> Any:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:200]
            raise ProviderError(f"HTTP {exc.code} from {self.name}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise ProviderError(f"cannot reach {self.name} at {self.base_url}: {exc}") from exc
        except ValueError as exc:
            raise ProviderError(f"invalid JSON from {self.name}: {exc}") from exc

    @property
    def label(self) -> str:
        return f"{self.name}:{self.model}"


class OpenAICompatProvider(_HttpProvider):
    """Any server exposing ``POST {base_url}/chat/completions`` (OpenAI, vLLM, LM Studio...)."""

    name = "openai"

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_OPENAI_URL,
        api_key_env: str = "OPENAI_API_KEY",
        timeout: float = 60.0,
        temperature: float | None = 0.0,
    ) -> None:
        super().__init__(base_url, model, timeout, temperature)
        self.api_key_env = api_key_env

    def complete(self, prompt: str, system: str | None = None) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key and urlparse(self.base_url).hostname == "api.openai.com":
            raise ProviderError(f"environment variable {self.api_key_env} is not set")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        body = self._post("/chat/completions", payload, headers)
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("unexpected response shape from chat/completions") from exc
        return str(content or "")


class OllamaProvider(_HttpProvider):
    """Ollama's native ``POST /api/generate`` (non-streaming)."""

    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout: float = 120.0,
        temperature: float | None = 0.0,
    ) -> None:
        super().__init__(base_url, model, timeout, temperature)

    def complete(self, prompt: str, system: str | None = None) -> str:
        payload: dict[str, Any] = {"model": self.model, "prompt": prompt, "stream": False}
        if system:
            payload["system"] = system
        if self.temperature is not None:
            payload["options"] = {"temperature": self.temperature}
        body = self._post("/api/generate", payload, {})
        if not isinstance(body, dict) or "response" not in body:
            raise ProviderError("unexpected response shape from /api/generate")
        return str(body["response"])


def make_provider(config: dict[str, Any]) -> Provider:
    """Build a provider from a config mapping: ``{"type": "mock|openai|ollama", ...}``."""
    cfg = dict(config)
    kind = str(cfg.pop("type", "mock"))
    try:
        if kind == "mock":
            return MockProvider(
                rules=cfg.get("rules"), default=cfg.get("default"), model=cfg.get("model", "mock")
            )
        if kind in ("openai", "openai-compatible"):
            if "model" not in cfg:
                raise ProviderError("openai provider needs 'model'")
            return OpenAICompatProvider(
                **_only(cfg, "model base_url api_key_env timeout temperature")
            )
        if kind == "ollama":
            if "model" not in cfg:
                raise ProviderError("ollama provider needs 'model'")
            return OllamaProvider(**_only(cfg, "model base_url timeout temperature"))
    except TypeError as exc:
        raise ProviderError(f"invalid provider options: {exc}") from exc
    raise ProviderError(f"unknown provider type: {kind!r} (use mock, openai or ollama)")


def _only(cfg: dict[str, Any], names: str) -> dict[str, Any]:
    allowed = names.split()
    return {k: v for k, v in cfg.items() if k in allowed}
