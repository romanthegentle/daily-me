"""Shared fixtures, and a fake Claude client so the tests never call the API."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from dailyme.models import Article, Brief, Edition, FrontPage, Section, Source, Weather
from dailyme.profile import Location, Profile, Reader, SectionSpec


def usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=1000,
        output_tokens=200,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
        server_tool_use=SimpleNamespace(web_search_requests=2, web_fetch_requests=1),
    )


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def tool_use(name: str, payload: dict[str, Any]) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", name=name, input=payload, id="toolu_test")


def reply(stop_reason: str, *content: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=list(content), usage=usage())


class FakeMessages:
    def __init__(self, handler: Callable[[dict[str, Any]], SimpleNamespace]) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> SimpleNamespace:
        # Snapshot the conversation: the caller keeps appending to the same list.
        kwargs = {**kwargs, "messages": list(kwargs.get("messages", []))}
        self.calls.append(kwargs)
        return self.handler(kwargs)


class FakeClient:
    """Stands in for anthropic.Anthropic: both messages and beta.messages hit `handler`."""

    def __init__(self, handler: Callable[[dict[str, Any]], SimpleNamespace]) -> None:
        self.messages = FakeMessages(handler)
        self.beta = SimpleNamespace(messages=self.messages)


@pytest.fixture
def profile() -> Profile:
    return Profile(
        reader=Reader(
            name="Ada",
            about="Data scientist in Lagos.",
            location=Location(name="Lagos", country="NG", timezone="Africa/Lagos"),
        ),
        sections=[
            SectionSpec(name="AI & Machine Learning", interests=["new models"]),
            SectionSpec(name="African Tech", interests=["startup funding"]),
        ],
    )


def _article(article_id: str, section: str, headline: str, importance: int, url: str) -> Article:
    return Article(
        id=article_id,
        section=section,
        headline=headline,
        dek="A one-line dek.",
        body=["First paragraph.", "Second paragraph."],
        why_it_matters="Because it touches your work.",
        importance=importance,
        published="2026-11-09",
        sources=[Source(url=url, title="A source", publisher="Example News")],
    )


@pytest.fixture
def edition() -> Edition:
    return Edition(
        date="2026-11-10",
        reader="Ada",
        number=3,
        front=FrontPage(greeting="Good morning, Ada.", lead_id="ai-1", top_ids=["africa-1"]),
        sections=[
            Section(
                name="AI",
                articles=[
                    _article("ai-1", "AI", "Lead story", 9, "https://example.com/a"),
                    _article("ai-2", "AI", "Second AI story", 5, "https://example.com/b"),
                ],
                briefs=[Brief(text="A short brief.", url="https://example.com/c", publisher="Ex")],
            ),
            Section(
                name="African Tech",
                articles=[
                    _article(
                        "africa-1", "African Tech", "Funding round", 7, "https://example.org/d"
                    )
                ],
            ),
            Section(name="Science", note="A quiet day on this beat."),
            Section(
                name="Outside your bubble",
                articles=[
                    _article(
                        "outside-1",
                        "Outside your bubble",
                        "Whales sing",
                        6,
                        "https://example.net/e",
                    )
                ],
            ),
        ],
        weather=Weather(place="Lagos", summary="Thunderstorms", high_c=31.2, low_c=24.4),
        generated_by="tests",
    )
