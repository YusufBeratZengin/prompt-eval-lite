from __future__ import annotations

import pytest

from conftest import FakeLLM
from prompt_eval_lite import (
    MockProvider,
    OllamaProvider,
    OpenAICompatProvider,
    ProviderError,
    make_provider,
)


def test_mock_default_echo() -> None:
    assert MockProvider().complete("hi") == "mock: hi"
    assert MockProvider(default="x").complete("hi") == "x"


def test_mock_rules_match_regex_and_cycle() -> None:
    p = MockProvider(
        rules=[
            {"match": "alpha", "reply": "A"},
            {"regex": r"b\w+", "replies": ["one", "two"]},
        ]
    )
    assert p.complete("alpha") == "A"
    assert [p.complete("beta"), p.complete("beta"), p.complete("beta")] == ["one", "two", "one"]


def test_mock_rule_validation() -> None:
    with pytest.raises(ProviderError):
        MockProvider(rules=[{"match": "x"}])
    with pytest.raises(ProviderError):
        MockProvider(rules=[{"reply": "x"}])


def test_openai_compat(fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEL_TEST_KEY", "sk-test-placeholder")
    p = OpenAICompatProvider(model="m", base_url=fake_llm.url, api_key_env="PEL_TEST_KEY")
    assert p.complete("hello", system="be brief") == "echo: hello"
    req = fake_llm.requests[0]
    assert req["path"] == "/chat/completions"
    assert req["auth"] == "Bearer sk-test-placeholder"
    assert req["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert req["body"]["model"] == "m"
    assert p.label == "openai:m"


def test_openai_without_key_sends_no_auth(
    fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    OpenAICompatProvider(model="m", base_url=fake_llm.url).complete("x")
    assert fake_llm.requests[0]["auth"] is None


def test_openai_hosted_requires_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        OpenAICompatProvider(model="m").complete("x")  # raises before any request is made


def test_ollama(fake_llm: FakeLLM) -> None:
    p = OllamaProvider(model="llama", base_url=fake_llm.url, temperature=0.2)
    assert p.complete("hey", system="sys") == "ollama: hey"
    body = fake_llm.requests[0]["body"]
    assert fake_llm.requests[0]["path"] == "/api/generate"
    assert body["stream"] is False
    assert body["system"] == "sys"
    assert body["options"] == {"temperature": 0.2}


@pytest.mark.parametrize("mode", ["http500", "badjson", "badshape"])
def test_http_failures(fake_llm: FakeLLM, mode: str) -> None:
    fake_llm.mode = mode
    with pytest.raises(ProviderError):
        OpenAICompatProvider(model="m", base_url=fake_llm.url).complete("x")
    with pytest.raises(ProviderError):
        OllamaProvider(model="m", base_url=fake_llm.url).complete("x")


def test_unreachable_server_is_provider_error(fake_llm: FakeLLM) -> None:
    url = fake_llm.url
    assert fake_llm.server is not None
    fake_llm.server.shutdown()
    fake_llm.server.server_close()
    with pytest.raises(ProviderError, match="cannot reach"):
        OllamaProvider(model="m", base_url=url, timeout=2).complete("x")


def test_base_url_scheme_is_validated() -> None:
    with pytest.raises(ProviderError):
        OllamaProvider(model="m", base_url="file:///etc/passwd")
    with pytest.raises(ProviderError):
        OpenAICompatProvider(model="m", base_url="not a url")


def test_make_provider() -> None:
    assert isinstance(make_provider({}), MockProvider)
    assert isinstance(make_provider({"type": "openai", "model": "m"}), OpenAICompatProvider)
    assert isinstance(make_provider({"type": "ollama", "model": "m"}), OllamaProvider)
    with pytest.raises(ProviderError, match="needs 'model'"):
        make_provider({"type": "openai"})
    with pytest.raises(ProviderError, match="needs 'model'"):
        make_provider({"type": "ollama"})
    with pytest.raises(ProviderError, match="unknown provider"):
        make_provider({"type": "nope"})
