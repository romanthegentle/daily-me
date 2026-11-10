from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from conftest import FakeClient, reply, text, tool_use

from dailyme.history import History
from dailyme.llm import Claude, web_tools
from dailyme.pipeline import build_edition
from dailyme.research import BUBBLE, SUBMIT_SECTION, slugify

NOW = datetime(2026, 11, 10, 6, 30, tzinfo=ZoneInfo("Africa/Lagos"))


def beat(kwargs: dict) -> str:
    return re.search(r"Your beat: (.+?)\.\n", kwargs["messages"][0]["content"]).group(1)


def filing(section: str) -> dict:
    slug = slugify(section)
    good = {
        "headline": f"{section} story",
        "dek": "Something happened.",
        "body": ["It happened.", "Here is why."],
        "why_it_matters": "It matters to Ada.",
        "importance": 7,
        "kind": "news",
        "published": "2026-11-09",
        "sources": [
            {"title": "Report", "url": f"https://news.example/{slug}", "publisher": "Example"}
        ],
    }
    unsourced = {**good, "headline": f"{section} rumour", "sources": []}
    unsafe = {
        **good,
        "headline": f"{section} trick",
        "sources": [{"title": "x", "url": "javascript:alert(1)", "publisher": "x"}],
    }
    return {
        "articles": [good, unsourced, unsafe],
        "briefs": [
            {
                "text": f"{section} brief.",
                "url": f"https://news.example/{slug}/brief",
                "publisher": "Ex",
            }
        ],
        "note": "",
    }


def newsroom(kwargs: dict):
    """Each reporter pauses once mid-research, then files. The editor picks the front page."""
    if any(tool.get("name") == "submit_section" for tool in kwargs.get("tools", [])):
        if len(kwargs["messages"]) == 1:
            return reply("pause_turn", text("Searching the web..."))
        return reply("tool_use", tool_use("submit_section", filing(beat(kwargs))))
    lead = "ai-machine-learning-1"
    return reply(
        "end_turn",
        text(
            json.dumps(
                {"greeting": "Good morning.", "lead_id": lead, "top_ids": ["african-tech-1"]}
            )
        ),
    )


def test_builds_a_full_edition(profile, tmp_path: Path):
    client = FakeClient(newsroom)
    claude = Claude("claude-opus-5-5", client=client)
    edition = build_edition(profile, claude, History.load(tmp_path), now=NOW)

    assert [s.name for s in edition.sections] == ["AI & Machine Learning", "African Tech", BUBBLE]
    for section in edition.sections:
        # The unsourced story and the one with a javascript: link are dropped.
        assert [a.headline for a in section.articles] == [f"{section.name} story"]
    assert edition.sections[0].briefs[0].text == "AI & Machine Learning brief."
    assert edition.sections[2].briefs == []  # "Outside your bubble" carries no briefs
    assert edition.lead().id == "ai-machine-learning-1"
    assert [a.id for a in edition.top()] == ["african-tech-1"]
    assert edition.front.greeting == "Good morning."
    assert edition.date == "2026-11-10" and edition.number == 1
    assert edition.cost_usd and edition.cost_usd > 0


def test_requests_use_fallbacks_and_current_tools(profile, tmp_path: Path):
    client = FakeClient(newsroom)
    build_edition(
        profile, Claude("claude-opus-5-5", client=client), History.load(tmp_path), now=NOW
    )

    reporter_call = client.messages.calls[0]
    assert reporter_call["fallbacks"] == "default"
    assert reporter_call["betas"] == ["server-side-fallback-2026-07-01"]
    assert reporter_call["output_config"] == {"effort": "medium"}
    assert reporter_call["cache_control"] == {"type": "ephemeral"}
    types = [tool.get("type") for tool in reporter_call["tools"]]
    assert "web_search_20260209" in types and "web_fetch_20260209" in types
    assert reporter_call["tools"][-1] is SUBMIT_SECTION
    location = reporter_call["tools"][0]["user_location"]
    assert location == {
        "type": "approximate",
        "city": "Lagos",
        "country": "NG",
        "timezone": "Africa/Lagos",
    }
    # A paused turn is sent back as-is, without an extra user message.
    paused = [c for c in client.messages.calls if len(c["messages"]) == 2]
    assert paused and all(c["messages"][-1]["role"] == "assistant" for c in paused)


def test_older_models_get_basic_tools_and_no_fallbacks():
    tools = web_tools("claude-haiku-5-5", searches=3, fetches=2)
    assert [t["type"] for t in tools] == ["web_search_20250305", "web_fetch_20250910"]
    assert Claude("claude-haiku-5-5", client=FakeClient(newsroom)).fallbacks is False


def test_stories_from_earlier_editions_are_skipped(profile, tmp_path: Path):
    history = History.load(tmp_path)
    history.data["stories"] = [
        {
            "date": "2026-11-09",
            "section": "African Tech",
            "headline": "Old news",
            "urls": ["https://www.news.example/african-tech/?utm_source=x"],
        }
    ]
    client = FakeClient(newsroom)
    edition = build_edition(profile, Claude(client=client), history, now=NOW)
    african = next(s for s in edition.sections if s.name == "African Tech")
    assert african.articles == []
    # Reporters are told what was already covered.
    assignment = client.messages.calls[0]["messages"][0]["content"]
    assert "- Old news (African Tech, 2026-11-09)" in assignment


def test_refusals_and_silent_reporters_leave_a_note(profile, tmp_path: Path):
    def handler(kwargs: dict):
        if not kwargs.get("tools"):
            return reply(
                "end_turn", text(json.dumps({"greeting": "", "lead_id": "x", "top_ids": []}))
            )
        if beat(kwargs) == "AI & Machine Learning":
            return reply("refusal")
        return reply("end_turn", text("I looked around but I'm not filing."))

    profile.serendipity = False
    client = FakeClient(handler)
    edition = build_edition(profile, Claude(client=client), History.load(tmp_path), now=NOW)
    notes = {s.name: s.note for s in edition.sections}
    assert notes["AI & Machine Learning"] == "This section couldn't be written today."
    assert notes["African Tech"] == "The reporter didn't file in time today."
    # The silent reporter was nudged with a user message after each turn.
    nudged = [c for c in client.messages.calls if c.get("tools") and len(c["messages"]) > 1]
    assert all(c["messages"][-1]["role"] == "user" for c in nudged)
    assert edition.articles() == []
