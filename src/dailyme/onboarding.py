"""`dailyme init --from-text`: turn a description of the reader into a profile."""

from __future__ import annotations

import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .llm import Claude
from .profile import Location, Profile, Reader, SectionSpec, Sources

SCHEMA = {
    "type": "object",
    "properties": {
        "reader_name": {"type": "string"},
        "about": {"type": "string"},
        "location": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "country": {"type": "string"},
                "timezone": {"type": "string"},
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
            },
            "required": ["name", "country", "timezone", "latitude", "longitude"],
            "additionalProperties": False,
        },
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "interests": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                },
                "required": ["name", "interests", "notes"],
                "additionalProperties": False,
            },
        },
        "avoid": {"type": "array", "items": {"type": "string"}},
        "prefer_sources": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["reader_name", "about", "location", "sections", "avoid", "prefer_sources"],
    "additionalProperties": False,
}

PROMPT = """\
Below is a description of a person, often written by their AI assistant from memory. Turn it into \
a reader profile for a personal morning newspaper.

- reader_name: their first name, or "Reader" if it isn't given.
- about: two to four sentences in the third person: their work, what they're building or \
studying, and what they want from the news.
- location: city, two-letter country code and IANA time zone, or empty strings if unknown; the \
city's latitude and longitude, or 0 if unknown.
- sections: four to seven newspaper sections that fit their interests. Each has a short name, \
three to six specific interests, and notes (one sentence, or empty).
- avoid: topics they'd want left out, if any are mentioned or clearly implied.
- prefer_sources: publications they'd trust on these topics, as bare domains.

Leave out anything sensitive that a newspaper doesn't need, such as health, money, relationships \
or addresses.

<description>
{text}
</description>"""


def _zone(name: str) -> str:
    try:
        ZoneInfo(name)
        return name
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC"


def draft_profile(text: str, claude: Claude) -> Profile:
    response = claude.create(
        max_tokens=8000,
        messages=[{"role": "user", "content": PROMPT.format(text=text.strip())}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined to draft a profile from that text.")
    data = json.loads(next(b.text for b in response.content if getattr(b, "type", "") == "text"))
    where = data["location"]
    location = Location(
        name=where.get("name", ""),
        country=(where.get("country") or "")[:2].upper(),
        timezone=_zone(where.get("timezone") or "UTC"),
        latitude=where.get("latitude") or None,
        longitude=where.get("longitude") or None,
    )
    sections = [
        SectionSpec(name=s["name"], interests=s["interests"], notes=s.get("notes", ""))
        for s in data["sections"]
        if s.get("name")
    ] or [SectionSpec(name="Top stories", interests=["the day's most important news"])]
    return Profile(
        reader=Reader(name=data["reader_name"] or "Reader", about=data["about"], location=location),
        sections=sections,
        avoid=data.get("avoid", []),
        sources=Sources(prefer=data.get("prefer_sources", [])),
    )


def profile_yaml(profile: Profile) -> str:
    header = (
        "# The Daily Me: your reader profile, drafted by `dailyme init --from-text`.\n"
        "# Check it, change anything that's off, then run `dailyme run`.\n\n"
    )
    body = yaml.safe_dump(
        profile.model_dump(mode="json"), sort_keys=False, allow_unicode=True, width=100
    )
    return header + body
