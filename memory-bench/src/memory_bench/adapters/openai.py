from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any

from memory_bench.adapters.base import ChatAdapter
from memory_bench.strategies.base import Message

ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(:-([^}]*))?}")


def _resolve_env_expr(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        env_key = match.group(1)
        fallback = match.group(3) or ""
        return os.getenv(env_key, fallback)

    return ENV_PATTERN.sub(repl, value)


class OpenAICompatibleAdapter(ChatAdapter):
    name = "openai"

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "OpenAICompatibleAdapter":
        raw_base_url = str(config.get("base_url", "https://api.openai.com/v1"))
        raw_model = str(config.get("model", "gpt-4o-mini"))
        api_key_env = str(config.get("api_key_env", "OPENAI_API_KEY"))

        base_url = _resolve_env_expr(raw_base_url)
        model = _resolve_env_expr(raw_model)
        api_key = os.getenv(api_key_env, "")
        if not api_key:
            raise ValueError(f"missing api key env: {api_key_env}")

        timeout = int(config.get("timeout", 60))
        return cls(base_url=base_url, api_key=api_key, model=model, timeout=timeout)

    def generate(self, messages: list[Message], *, metadata: dict[str, Any] | None = None) -> str:
        _ = metadata
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        body = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"openai adapter http error: {exc.code} {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"openai adapter connection error: {exc.reason}") from exc

        parsed = json.loads(raw)
        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError("openai adapter response missing choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
            return "".join(text_parts)
        raise RuntimeError("openai adapter response missing text content")
