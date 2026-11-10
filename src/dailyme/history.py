"""What earlier editions covered, so the paper doesn't repeat itself."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from .models import Edition

KEEP_DAYS = 45
_TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src", "cmpid", "ocid", "smid"}


def normalize_url(url: str) -> str:
    """Strip tracking parameters, fragments and cosmetic differences so URLs compare equal."""
    parts = urlparse(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_KEYS
    ]
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    return urlunparse(("https", host, path, "", urlencode(query), ""))


class History:
    """A small JSON file with recent stories and the edition count."""

    FILE = "history.json"

    def __init__(self, path: Path, data: dict[str, Any] | None = None) -> None:
        self.path = path
        self.data: dict[str, Any] = data or {"editions": 0, "stories": []}

    @classmethod
    def load(cls, state_dir: str | Path) -> History:
        path = Path(state_dir) / cls.FILE
        if path.exists():
            return cls(path, json.loads(path.read_text(encoding="utf-8")))
        return cls(path)

    def number_for(self, day: date) -> int:
        """The edition number for `day`. Re-running a day keeps its number."""
        if self.data.get("last_date") == day.isoformat():
            return int(self.data.get("editions", 1))
        return int(self.data.get("editions", 0)) + 1

    def _stories_since(self, day: date, days: int) -> list[dict[str, Any]]:
        cutoff = (day - timedelta(days=days)).isoformat()
        return [
            story
            for story in self.data.get("stories", [])
            if cutoff <= story.get("date", "") < day.isoformat()
        ]

    def recent_headlines(self, day: date, days: int = 7) -> list[str]:
        return [
            f"- {story['headline']} ({story['section']}, {story['date']})"
            for story in self._stories_since(day, days)
        ]

    def seen_urls(self, day: date, days: int = 14) -> set[str]:
        return {
            normalize_url(url)
            for story in self._stories_since(day, days)
            for url in story.get("urls", [])
        }

    def record(self, edition: Edition) -> None:
        stories = [s for s in self.data.get("stories", []) if s.get("date") != edition.date]
        for article in edition.articles():
            stories.append(
                {
                    "date": edition.date,
                    "section": article.section,
                    "headline": article.headline,
                    "urls": [source.url for source in article.sources],
                }
            )
        cutoff = (date.fromisoformat(edition.date) - timedelta(days=KEEP_DAYS)).isoformat()
        self.data["stories"] = [s for s in stories if s.get("date", "") >= cutoff]
        self.data["editions"] = max(int(self.data.get("editions", 0)), edition.number)
        self.data["last_date"] = edition.date

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
