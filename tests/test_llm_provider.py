"""Tests for LLMProvider — tests formatting, config, error handling (no API mocking)."""

from llm_provider import API_URL, API_VERSION, DEFAULT_MODEL, LLMProvider


class TestLLMProviderInit:
    def test_no_key_means_unavailable(self):
        provider = LLMProvider(api_key="")
        assert provider.available is False

    def test_key_provided_means_available(self):
        provider = LLMProvider(api_key="sk-test-key")
        assert provider.available is True

    def test_default_model(self):
        provider = LLMProvider()
        assert provider.model == DEFAULT_MODEL


class TestRequestFormatting:
    def test_format_request_structure(self):
        provider = LLMProvider(api_key="sk-test-key")
        req = provider.format_request([{"role": "user", "content": "hello"}], max_tokens=256)
        assert req["url"] == API_URL
        assert req["headers"]["x-api-key"] == "sk-test-key"
        assert req["headers"]["anthropic-version"] == API_VERSION
        assert req["headers"]["content-type"] == "application/json"
        assert req["body"]["model"] == DEFAULT_MODEL
        assert req["body"]["max_tokens"] == 256
        assert len(req["body"]["messages"]) == 1

    def test_format_request_preserves_messages(self):
        provider = LLMProvider(api_key="sk-test")
        messages = [
            {"role": "user", "content": "question"},
        ]
        req = provider.format_request(messages)
        assert req["body"]["messages"] == messages


class TestAnalyze:
    def test_analyze_returns_empty_when_unavailable(self):
        provider = LLMProvider(api_key="")
        result = provider.analyze("test prompt", "test context")
        assert result == ""

    def test_call_api_with_bad_key_returns_empty(self):
        """Calling API with invalid key should fail gracefully."""
        provider = LLMProvider(api_key="sk-invalid-key")
        result = provider._call_api([{"role": "user", "content": "hi"}], max_tokens=10)
        assert result == ""
