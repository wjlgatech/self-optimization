"""Anthropic API client via stdlib urllib.request.

Uses claude-haiku-4-5-20251001 for cost-efficient internal analysis.
Falls back gracefully when no API key is available.
"""

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
API_VERSION = "2023-06-01"


class LLMProvider:
    """Anthropic API client for intelligent analysis tasks."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.available = bool(self.api_key)
        self.model = DEFAULT_MODEL

    def analyze(self, prompt: str, context: str = "", max_tokens: int = 1024) -> str:
        """Send an analysis request to the Anthropic API.

        Returns text response on success, empty string on failure
        (caller should fall back to rule-based analysis).
        """
        if not self.available:
            return ""

        user_content = prompt
        if context:
            user_content = f"Context:\n{context}\n\nTask:\n{prompt}"

        messages: List[Dict[str, str]] = [{"role": "user", "content": user_content}]
        return self._call_api(messages, max_tokens)

    def _call_api(self, messages: List[Dict[str, str]], max_tokens: int = 1024) -> str:
        """Make a POST request to the Anthropic Messages API."""
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        }

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data: Dict[str, Any] = json.loads(resp.read().decode("utf-8"))
                content = data.get("content", [])
                if content and isinstance(content, list):
                    return str(content[0].get("text", ""))
                return ""
        except urllib.error.HTTPError as e:
            logger.error("Anthropic API HTTP error %d: %s", e.code, e.reason)
            return ""
        except urllib.error.URLError as e:
            logger.error("Anthropic API URL error: %s", e.reason)
            return ""
        except (json.JSONDecodeError, OSError, TimeoutError) as e:
            logger.error("Anthropic API error: %s", e)
            return ""

    def format_request(
        self, messages: List[Dict[str, str]], max_tokens: int = 1024
    ) -> Dict[str, Any]:
        """Format a request payload without sending it (useful for testing)."""
        return {
            "url": API_URL,
            "headers": {
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
                "content-type": "application/json",
            },
            "body": {
                "model": self.model,
                "max_tokens": max_tokens,
                "messages": messages,
            },
        }
