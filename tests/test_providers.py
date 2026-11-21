import json

import pytest

from model_pin_scanner.providers import (
    AnthropicProvider,
    CompletionRequest,
    GoogleProvider,
    MockProvider,
    OpenAIProvider,
    ProviderError,
    from_env,
    guess_provider,
)


class FakeTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "headers": dict(headers), "body": json.loads(body)})
        status, doc = self.responses.pop(0)
        return status, json.dumps(doc).encode() if not isinstance(doc, bytes) else doc


REQ = CompletionRequest("m", "Hello?", system="Be brief.", max_tokens=50, prompt_id="p1")


def test_openai_request_and_parse():
    t = FakeTransport((200, {"choices": [{"message": {"content": "Hi."}}]}))
    out = OpenAIProvider("sk-test", transport=t).complete(REQ)
    assert out == "Hi."
    call = t.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["authorization"] == "Bearer sk-test"
    assert call["body"] == {
        "model": "m",
        "messages": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hello?"}],
        "max_completion_tokens": 50,
    }


def test_anthropic_request_and_parse():
    t = FakeTransport(
        (200, {"content": [{"type": "text", "text": "A"}, {"type": "thinking"}, {"type": "text", "text": "B"}]})
    )
    assert AnthropicProvider("k", transport=t).complete(REQ) == "AB"
    call = t.calls[0]
    assert call["url"] == "https://api.anthropic.com/v1/messages"
    assert call["headers"]["x-api-key"] == "k"
    assert call["headers"]["anthropic-version"] == "2023-06-01"
    assert call["body"]["system"] == "Be brief." and call["body"]["max_tokens"] == 50


def test_google_request_and_parse():
    t = FakeTransport((200, {"candidates": [{"content": {"parts": [{"text": "G1"}, {"text": "G2"}]}}]}))
    req = CompletionRequest("gemini-2.5-flash", "Hi", None, 10)
    assert GoogleProvider("g", transport=t).complete(req) == "G1G2"
    call = t.calls[0]
    assert call["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    assert call["headers"]["x-goog-api-key"] == "g"
    assert "systemInstruction" not in call["body"]


def test_retries_then_succeeds():
    t = FakeTransport((429, {}), (503, {}), (200, {"choices": [{"message": {"content": "ok"}}]}))
    waits = []
    p = OpenAIProvider("k", transport=t, sleep=waits.append)
    assert p.complete(REQ) == "ok"
    assert waits == [1.0, 2.0]


def test_http_error_is_reported_without_key():
    t = FakeTransport((401, {"error": "bad key"}))
    with pytest.raises(ProviderError, match="HTTP 401") as exc:
        OpenAIProvider("sk-secret", transport=t).complete(REQ)
    assert "sk-secret" not in str(exc.value)


def test_malformed_response():
    with pytest.raises(ProviderError, match="choices"):
        OpenAIProvider("k", transport=FakeTransport((200, {"x": 1}))).complete(REQ)
    with pytest.raises(ProviderError, match="not JSON"):
        OpenAIProvider("k", transport=FakeTransport((200, b"<html>"))).complete(REQ)


def test_mock_provider():
    p = MockProvider({"m": {"p1": "canned"}})
    assert p.complete(REQ) == "canned"
    with pytest.raises(ProviderError):
        p.complete(CompletionRequest("other", "x", prompt_id="p1"))
    with pytest.raises(ProviderError):
        p.complete(CompletionRequest("m", "x", prompt_id="p2"))


@pytest.mark.parametrize(
    "model,provider",
    [
        ("gpt-4o-2024-08-06", "openai"),
        ("o3-2025-04-16", "openai"),
        ("claude-sonnet-5-5", "anthropic"),
        ("gemini-2.5-flash", "google"),
    ],
)
def test_guess_provider(model, provider):
    assert guess_provider(model) == provider


def test_guess_provider_unknown():
    with pytest.raises(ProviderError, match="--provider"):
        guess_provider("llama-3")


def test_from_env():
    t = FakeTransport((200, {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}))
    p = from_env("google", {"GOOGLE_API_KEY": "gk"}, transport=t)
    assert isinstance(p, GoogleProvider)
    p.complete(CompletionRequest("gemini-2.5-flash", "hi"))
    assert t.calls[0]["headers"]["x-goog-api-key"] == "gk"


def test_from_env_missing_key():
    with pytest.raises(ProviderError, match="ANTHROPIC_API_KEY"):
        from_env("anthropic", {})


def test_from_env_base_url():
    p = from_env("openai", {"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": "https://proxy.example/v1"})
    assert p._base == "https://proxy.example/v1"
    with pytest.raises(ProviderError, match="https"):
        from_env("openai", {"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": "http://proxy.example/v1"})
