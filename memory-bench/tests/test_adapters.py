from __future__ import annotations

import os

import pytest

from memory_bench.adapters import create_adapter
from memory_bench.adapters.openai import _resolve_env_expr


def test_mock_adapter_enforces_basic_constraints() -> None:
    adapter = create_adapter("mock")
    messages = [
        {"role": "system", "content": "format=json_only forbidden_word=sorry max_items=1"},
        {"role": "user", "content": "destination=Kyoto traveler_name=Avery"},
    ]
    answer = adapter.generate(messages)

    assert answer.startswith("{")
    assert "sorry" not in answer.lower()


def test_runtime_adapter_uses_fallback() -> None:
    adapter = create_adapter("runtime")
    answer = adapter.generate([
        {"role": "user", "content": "project=atlas"},
    ])
    assert "atlas" in answer


def test_openai_adapter_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        create_adapter(
            "openai",
            {
                "base_url": "https://api.openai.com/v1",
                "api_key_env": "OPENAI_API_KEY",
                "model": "gpt-4o-mini",
            },
        )


def test_resolve_env_expr_with_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FOO_BASE", raising=False)
    assert _resolve_env_expr("${FOO_BASE:-https://example.com}") == "https://example.com"

    monkeypatch.setenv("FOO_BASE", "https://override.com")
    assert _resolve_env_expr("${FOO_BASE:-https://example.com}") == "https://override.com"


@pytest.mark.skipif(os.getenv("OPENAI_SMOKE") != "1", reason="set OPENAI_SMOKE=1 to enable")
def test_openai_smoke_real_call() -> None:
    adapter = create_adapter(
        "openai",
        {
            "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            "api_key_env": os.getenv("OPENAI_API_KEY_ENV", "OPENAI_API_KEY"),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "timeout": 60,
        },
    )

    answer = adapter.generate(
        [
            {"role": "system", "content": "Reply with exactly: pong"},
            {"role": "user", "content": "ping"},
        ]
    )
    assert isinstance(answer, str)
    assert answer.strip()
