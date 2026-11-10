"""Builds an edition: reporters in parallel, de-duplication, weather and the front page."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic

from .feeds import recent_items
from .frontpage import edit_front_page
from .history import History, normalize_url
from .llm import Claude
from .models import Article, Edition, Section
from .profile import Profile, SectionSpec
from .research import SERENDIPITY, report
from .weather import forecast

log = logging.getLogger("dailyme")

# Errors that would hit every section the same way: stop and say so.
FATAL = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.NotFoundError,
    anthropic.BadRequestError,
)


def reader_now(profile: Profile) -> datetime:
    try:
        zone = ZoneInfo(profile.reader.location.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        zone = ZoneInfo("UTC")
    return datetime.now(zone)


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.8


def _primary(article: Article) -> str:
    return normalize_url(article.sources[0].url) if article.sources else ""


def drop_repeats(sections: list[Section], seen: set[str]) -> None:
    """Drop stories from earlier editions and the same story filed by two reporters."""
    kept_urls: set[str] = set()
    kept_headlines: list[str] = []
    for section in sections:
        kept: list[Article] = []
        for article in section.articles:
            url = _primary(article)
            if article.kind != "follow_up" and url in seen:
                continue
            if url in kept_urls or any(_similar(article.headline, h) for h in kept_headlines):
                continue
            kept.append(article)
            kept_urls.add(url)
            kept_headlines.append(article.headline)
        section.articles = kept


def build_edition(
    profile: Profile, claude: Claude, history: History, *, now: datetime | None = None
) -> Edition:
    now = now or reader_now(profile)
    since = now - timedelta(hours=profile.settings.window_hours)
    today = now.date()
    specs = [*profile.sections, *([SERENDIPITY] if profile.serendipity else [])]
    headlines = history.recent_headlines(today)

    def file_section(spec: SectionSpec) -> Section:
        leads = recent_items(spec.feeds, since) if spec.feeds else []
        try:
            section = report(
                claude, profile, spec, now=now, since=since, history=headlines, leads=leads
            )
        except FATAL:
            raise
        except anthropic.APIError as error:
            log.warning("%s: %s", spec.name, error)
            return Section(name=spec.name, note="This section couldn't be written today.")
        log.info(
            "%s: %d articles, %d briefs", spec.name, len(section.articles), len(section.briefs)
        )
        return section

    log.info("Sending %d reporters out for %s.", len(specs), today.isoformat())
    with ThreadPoolExecutor(max_workers=profile.settings.parallel_sections) as pool:
        sections = list(pool.map(file_section, specs))

    drop_repeats(sections, history.seen_urls(today))
    edition = Edition(
        paper_name=profile.paper.name,
        tagline=profile.paper.tagline,
        reader=profile.reader.name,
        date=today.isoformat(),
        number=history.number_for(today),
        sections=sections,
        weather=forecast(profile.reader.location),
        generated_by=f"{claude.model} via the Claude API",
    )
    edition.front = edit_front_page(claude, profile, edition)
    edition.cost_usd = claude.usage.cost(claude.model)
    return edition
