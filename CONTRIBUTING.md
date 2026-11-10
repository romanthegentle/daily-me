# Contributing

Thanks for helping. Bug reports, ideas and pull requests are all welcome.

## Set up

```bash
git clone https://github.com/romanthegentle/daily-me.git
cd daily-me
python -m venv .venv
source .venv/bin/activate        # on Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
ruff check .
ruff format .
pytest
```

The tests use a fake Claude client, so they're free and need no API key.

## Ground rules

- **Sources first.** Every article must link the pages it relies on. Changes that make it easier for the paper to state something without a source won't be merged.
- **Summaries, not copies.** The paper writes in its own words and links out. Don't add features that reproduce articles in full.
- **The reader's data stays theirs.** Profiles, editions and history stay on the reader's machine or in their own repository settings.

## Good first issues

- More output formats: EPUB for e-readers, or a podcast-style audio edition.
- One-click "more like this / less like this" links that update the profile.
- Support for more delivery channels, such as Telegram or Slack.
