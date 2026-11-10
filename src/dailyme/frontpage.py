"""The editor: picks the front page and writes the morning note."""

from __future__ import annotations

import json

import anthropic

from .llm import Claude
from .models import Edition, FrontPage
from .profile import Profile

SCHEMA = {
    "type": "object",
    "properties": {
        "greeting": {"type": "string"},
        "lead_id": {"type": "string"},
        "top_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["greeting", "lead_id", "top_ids"],
    "additionalProperties": False,
}

PROMPT = """\
You are the editor of {paper}, a newspaper with one reader: {name}.
About the reader: {about}

Today's stories:
{listing}

Choose the front page:
- lead_id: the story that matters most to this reader today.
- top_ids: up to three more front-page stories, most important first. Spread them across \
sections when you can.
- greeting: two or three sentences that open today's paper for {name}. Say what today is about, \
in plain words. Calm and specific; no hype, and don't list every story."""


def auto_front_page(edition: Edition, greeting: str = "") -> FrontPage:
    """A front page by importance alone, used when the editor can't be reached."""
    ranked = sorted(edition.articles(), key=lambda a: a.importance, reverse=True)
    if not ranked:
        return FrontPage(greeting=greeting)
    return FrontPage(greeting=greeting, lead_id=ranked[0].id, top_ids=[a.id for a in ranked[1:4]])


def edit_front_page(claude: Claude, profile: Profile, edition: Edition) -> FrontPage:
    articles = edition.articles()
    if not articles:
        return FrontPage(greeting="A quiet day: nothing new on your beats. Back tomorrow.")
    listing = "\n".join(
        f"- id={a.id} | {a.section} | importance {a.importance} | {a.headline}: {a.dek}"
        for a in articles
    )
    prompt = PROMPT.format(
        paper=profile.paper.name,
        name=profile.reader.name,
        about=profile.reader.about.strip() or "not given",
        listing=listing,
    )
    data: dict = {}
    try:
        response = claude.create(
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if response.stop_reason != "refusal":
            text = next((b.text for b in response.content if getattr(b, "type", "") == "text"), "")
            data = json.loads(text) if text else {}
    except (anthropic.APIError, json.JSONDecodeError):
        data = {}

    ids = {a.id for a in articles}
    greeting = str(data.get("greeting", "")).strip()
    lead_id = data.get("lead_id")
    if lead_id not in ids:
        return auto_front_page(edition, greeting)
    top_ids = [i for i in data.get("top_ids", []) if i in ids and i != lead_id][:3]
    return FrontPage(greeting=greeting, lead_id=lead_id, top_ids=top_ids)
