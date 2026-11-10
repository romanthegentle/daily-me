from __future__ import annotations

from datetime import date

from dailyme.history import History, normalize_url


def test_normalize_url():
    messy = "HTTP://www.Example.com/story/?utm_source=x&id=7&fbclid=y#comments"
    assert normalize_url(messy) == "https://example.com/story?id=7"
    assert normalize_url("https://example.com/") == "https://example.com/"


def test_record_and_recall(edition, tmp_path):
    history = History.load(tmp_path)
    assert history.number_for(date(2026, 11, 10)) == 1
    history.record(edition)
    history.save()

    again = History.load(tmp_path)
    tomorrow = date(2026, 11, 11)
    assert again.number_for(tomorrow) == 4  # the fixture edition is No. 3
    assert again.number_for(date(2026, 11, 10)) == 3  # re-running a day keeps its number
    assert "https://example.com/a" in again.seen_urls(tomorrow)
    assert "- Lead story (AI, 2026-11-10)" in again.recent_headlines(tomorrow)
    # Today's own stories don't count as "seen" when re-running today.
    assert again.seen_urls(date(2026, 11, 10)) == set()


def test_old_stories_are_pruned(edition, tmp_path):
    history = History.load(tmp_path)
    history.data["stories"] = [
        {"date": "2026-08-01", "section": "x", "headline": "old", "urls": []}
    ]
    history.record(edition)
    assert all(story["date"] == "2026-11-10" for story in history.data["stories"])
