"""Optional RSS and Atom feeds, used as extra leads for a section."""

from __future__ import annotations

import urllib.request
from datetime import datetime, timezone
from typing import Any

import feedparser

from . import USER_AGENT


def recent_items(
    urls: list[str], since: datetime, *, limit: int = 12, timeout: float = 15.0
) -> list[dict[str, Any]]:
    """Items published after `since` across the feeds, newest first."""
    since_utc = since.astimezone(timezone.utc)
    items: list[dict[str, Any]] = []
    for url in urls:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
        except Exception:  # noqa: BLE001 - a dead feed shouldn't stop the paper
            continue
        for entry in feedparser.parse(payload).entries:
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            link = entry.get("link", "")
            if not stamp or not link:
                continue
            when = datetime(*stamp[:6], tzinfo=timezone.utc)
            if when >= since_utc:
                title = " ".join(entry.get("title", "").split())
                items.append({"title": title, "url": link, "when": when})
    items.sort(key=lambda item: item["when"], reverse=True)
    return items[:limit]
