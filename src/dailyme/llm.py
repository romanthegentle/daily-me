"""A thin layer over the Claude API: model options, refusal fallbacks and a cost meter."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import anthropic

DEFAULT_MODEL = "claude-opus-5-5"

# List prices in US dollars per million tokens (input, output). Used only for the
# cost estimate printed after each run. Check https://claude.com/pricing for current prices.
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
WEB_SEARCH_PRICE = 0.01  # dollars per search ($10 per 1,000)

# Models that take the newer web search and fetch tools, with dynamic filtering.
DYNAMIC_WEB_TOOLS = {
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4-8",
    "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-sonnet-5-5",
    "claude-sonnet-5",
    "claude-sonnet-4-6",
}

# Models that accept server-side refusal fallbacks: if a request is declined, the API
# re-runs it on a recommended model instead of returning the refusal.
FALLBACK_MODELS = {"claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
FALLBACK_BETA = "server-side-fallback-2026-07-01"


def web_tools(
    model: str,
    *,
    searches: int,
    fetches: int,
    user_location: dict[str, str] | None = None,
    blocked_domains: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Web search and web fetch tool definitions for `model`."""
    dynamic = model in DYNAMIC_WEB_TOOLS
    search: dict[str, Any] = {
        "type": "web_search_20260209" if dynamic else "web_search_20250305",
        "name": "web_search",
        "max_uses": searches,
    }
    if user_location:
        search["user_location"] = user_location
    if blocked_domains:
        search["blocked_domains"] = list(blocked_domains)
    tools = [search]
    if fetches > 0:
        fetch: dict[str, Any] = {
            "type": "web_fetch_20260209" if dynamic else "web_fetch_20250910",
            "name": "web_fetch",
            "max_uses": fetches,
            "max_content_tokens": 8000,
        }
        if blocked_domains:
            fetch["blocked_domains"] = list(blocked_domains)
        tools.append(fetch)
    return tools


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


@dataclass
class Usage:
    """Running totals across every API call in a run."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    web_searches: int = 0
    web_fetches: int = 0

    def add(self, usage: Any) -> None:
        if usage is None:
            return
        self.calls += 1
        self.input_tokens += _int(getattr(usage, "input_tokens", 0))
        self.output_tokens += _int(getattr(usage, "output_tokens", 0))
        self.cache_read_tokens += _int(getattr(usage, "cache_read_input_tokens", 0))
        self.cache_write_tokens += _int(getattr(usage, "cache_creation_input_tokens", 0))
        server = getattr(usage, "server_tool_use", None)
        if server is not None:
            self.web_searches += _int(getattr(server, "web_search_requests", 0))
            self.web_fetches += _int(getattr(server, "web_fetch_requests", 0))

    def cost(self, model: str) -> float | None:
        """Estimated cost in dollars, at `model`'s list prices."""
        if model not in PRICES:
            return None
        price_in, price_out = PRICES[model]
        tokens = (
            self.input_tokens * price_in
            + self.cache_write_tokens * price_in * 1.25
            + self.cache_read_tokens * price_in * 0.1
            + self.output_tokens * price_out
        ) / 1_000_000
        return round(tokens + self.web_searches * WEB_SEARCH_PRICE, 4)

    def summary(self, model: str) -> str:
        cost = self.cost(model)
        price = f"about ${cost:.2f}" if cost is not None else "cost unknown for this model"
        tokens_in = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        return (
            f"{self.calls} API calls, {tokens_in:,} input and "
            f"{self.output_tokens:,} output tokens, "
            f"{self.web_searches} searches and {self.web_fetches} page reads: {price}"
        )


class Claude:
    """Sends Messages API requests with the paper's model settings and meters the cost."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        effort: str = "medium",
        *,
        fallbacks: bool = True,
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        self.fallbacks = fallbacks and model in FALLBACK_MODELS
        self.client = client if client is not None else anthropic.Anthropic()
        self.usage = Usage()
        self._lock = threading.Lock()

    def create(self, **params: Any) -> Any:
        output_config = {"effort": self.effort, **params.pop("output_config", {})}
        request = {
            "model": self.model,
            "max_tokens": 16000,
            "output_config": output_config,
            **params,
        }
        if self.fallbacks:
            response = self.client.beta.messages.create(
                betas=[FALLBACK_BETA], fallbacks="default", **request
            )
        else:
            response = self.client.messages.create(**request)
        with self._lock:
            self.usage.add(getattr(response, "usage", None))
        return response
