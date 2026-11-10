from __future__ import annotations

from dailyme.models import Source
from dailyme.render import render_email, render_html, render_markdown, safe_url, write_edition


def test_newspaper_page(edition):
    html = render_html(edition)
    assert "Good morning, Ada." in html
    assert "Lagos: Thunderstorms, 31°C / 24°C" in html
    assert "Why it matters to you." in html
    assert 'href="https://example.com/a"' in html
    assert "A quiet day on this beat." in html
    assert 'class="section bubble"' in html
    # The lead runs once, on the front. Other front-page stories are teasers that
    # continue in full inside their section.
    assert html.count(">Lead story<") == 1
    assert html.count(">Funding round<") == 2
    assert 'href="#africa-1"' in html and 'id="africa-1"' in html
    assert html.count(">Second AI story<") == 1


def test_untrusted_text_is_escaped_and_links_are_checked(edition):
    lead = edition.lead()
    lead.headline = "<script>alert(1)</script>"
    lead.sources.append(Source(url="javascript:alert(2)", publisher="Bad"))
    html = render_html(edition)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "javascript:" not in html
    assert safe_url("javascript:alert(2)") == "#"


def test_email_and_markdown(edition):
    email = render_email(edition)
    assert "Good morning, Ada." in email
    assert email.count("Funding round") == 1  # in full on the front, not repeated
    markdown = render_markdown(edition)
    assert "# The Daily Me" in markdown
    assert "### Lead story" in markdown
    assert "[Example News](https://example.com/a)" in markdown
    assert "- A short brief. ([Ex](https://example.com/c))" in markdown


def test_write_edition(edition, tmp_path):
    paths = write_edition(edition, tmp_path)
    assert sorted(p.name for p in paths.values()) == [
        "2026-11-10.html",
        "2026-11-10.json",
        "2026-11-10.md",
    ]
    assert all(p.exists() and p.stat().st_size > 0 for p in paths.values())
