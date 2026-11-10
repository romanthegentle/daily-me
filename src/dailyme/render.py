"""Lays an edition out as a newspaper page, an email and Markdown, and prints PDFs."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jinja2 import Environment, PackageLoader

from . import REPO_URL, __version__
from .models import Edition
from .research import BUBBLE


def domain(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def safe_url(url: str) -> str:
    """Only http and https links make it onto the page."""
    return url if urlparse(url).scheme in ("http", "https") else "#"


def dateline(iso_date: str) -> str:
    day = date.fromisoformat(iso_date)
    return f"{day:%A}, {day.day} {day:%B %Y}"


def weather_line(edition: Edition) -> str:
    weather = edition.weather
    if weather is None:
        return ""
    line = f"{weather.place}: {weather.summary}"
    if weather.high_c is not None:
        line += f", {round(weather.high_c)}°C"
        if weather.low_c is not None:
            line += f" / {round(weather.low_c)}°C"
    return line


def _environment() -> Environment:
    env = Environment(
        loader=PackageLoader("dailyme", "templates"),
        autoescape=lambda name: bool(name) and name.endswith(".html.j2"),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(domain=domain, safe_url=safe_url, dateline=dateline)
    return env


def _context(edition: Edition, *, full_front: bool) -> dict[str, Any]:
    """Template data. With `full_front`, front-page stories are printed in full on the front
    and left out of their sections (email, Markdown). Otherwise the front carries teasers
    and the stories continue inside (the newspaper page)."""
    lead = edition.lead()
    if full_front:
        hidden = edition.front_page_ids()
    else:
        hidden = {lead.id} if lead is not None else set()
    sections = [
        {
            "section": section,
            "articles": [a for a in section.articles if a.id not in hidden],
            "bubble": section.name == BUBBLE,
        }
        for section in edition.sections
    ]
    return {
        "e": edition,
        "lead": lead,
        "top": edition.top(),
        "sections": sections,
        "weather": weather_line(edition),
        "source_count": len({s.url for a in edition.articles() for s in a.sources}),
        "repo_url": REPO_URL,
        "version": __version__,
    }


def _render(template: str, edition: Edition, *, full_front: bool) -> str:
    context = _context(edition, full_front=full_front)
    return _environment().get_template(template).render(**context)


def render_html(edition: Edition) -> str:
    return _render("paper.html.j2", edition, full_front=False)


def render_email(edition: Edition) -> str:
    return _render("email.html.j2", edition, full_front=True)


def render_markdown(edition: Edition) -> str:
    return _render("edition.md.j2", edition, full_front=True)


def write_edition(edition: Edition, out_dir: str | Path) -> dict[str, Path]:
    """Save the edition as JSON, HTML and Markdown, named after its date."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": out / f"{edition.date}.json",
        "html": out / f"{edition.date}.html",
        "markdown": out / f"{edition.date}.md",
    }
    paths["json"].write_text(edition.model_dump_json(indent=2), encoding="utf-8")
    paths["html"].write_text(render_html(edition), encoding="utf-8")
    paths["markdown"].write_text(render_markdown(edition), encoding="utf-8")
    return paths


_BROWSER_NAMES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "chrome",
    "msedge",
    "microsoft-edge",
)
_BROWSER_PATHS = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def find_browser() -> str | None:
    """A Chrome-family browser for printing, from $DAILYME_BROWSER or the usual places."""
    configured = os.environ.get("DAILYME_BROWSER")
    if configured:
        return configured
    for name in _BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return next((path for path in _BROWSER_PATHS if Path(path).exists()), None)


def _headless(arguments: list[str]) -> bool:
    browser = find_browser()
    if browser is None:
        return False
    command = [browser, "--headless=new", "--disable-gpu", "--virtual-time-budget=8000", *arguments]
    if os.environ.get("CI"):
        command.insert(1, "--no-sandbox")
    try:
        subprocess.run(command, check=False, capture_output=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return True


def print_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Print the newspaper page to PDF with a headless Chrome or Edge."""
    pdf_path = pdf_path.resolve()
    printed = _headless(
        [
            "--no-pdf-header-footer",
            "--print-to-pdf-no-header",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
    )
    return printed and pdf_path.exists() and pdf_path.stat().st_size > 0


def screenshot(html_path: Path, png_path: Path, *, width: int = 1280, height: int = 1800) -> bool:
    """A PNG of the top of the page, for previews."""
    png_path = png_path.resolve()
    taken = _headless(
        [
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--screenshot={png_path}",
            html_path.resolve().as_uri(),
        ]
    )
    return taken and png_path.exists() and png_path.stat().st_size > 0
