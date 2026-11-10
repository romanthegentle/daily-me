from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dailyme.cli import main
from dailyme.deliver import EmailSettings, build_message, subject_for
from dailyme.profile import Profile, example_profile_text, load_profile

ROOT = Path(__file__).resolve().parents[1]


def test_example_profile_loads_and_matches_the_root_copy(tmp_path):
    (tmp_path / "profile.yaml").write_text(example_profile_text(), encoding="utf-8")
    profile = load_profile(tmp_path / "profile.yaml")
    assert profile.reader.name == "Ada"
    assert len(profile.sections) == 3 and profile.serendipity
    assert (ROOT / "profile.example.yaml").read_text(encoding="utf-8") == example_profile_text()


def test_profile_from_environment(monkeypatch):
    monkeypatch.setenv(
        "DAILYME_PROFILE", "sections:\n  - name: Football\n    interests: [Arsenal]\n"
    )
    assert load_profile().sections[0].name == "Football"


def test_profile_needs_a_section():
    with pytest.raises(ValidationError):
        Profile.model_validate({"sections": []})


def test_demo_init_schema_and_render(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path / "demo")]) == 0
    sample_json = next((tmp_path / "demo").glob("*.json"))
    assert next((tmp_path / "demo").glob("*.html")).stat().st_size > 5000

    target = tmp_path / "profile.yaml"
    assert main(["init", "--path", str(target)]) == 0
    assert main(["init", "--path", str(target)]) == 1  # won't overwrite without --force

    capsys.readouterr()
    assert main(["schema"]) == 0
    assert json.loads(capsys.readouterr().out)["title"] == "Edition"

    state = tmp_path / "state"
    assert (
        main(["render", str(sample_json), "--out", str(tmp_path / "out"), "--state", str(state)])
        == 0
    )
    assert json.loads((state / "history.json").read_text(encoding="utf-8"))["editions"] == 1
    # Rendering the same day again keeps its number; the history sets it, not the JSON.
    assert (
        main(["render", str(sample_json), "--out", str(tmp_path / "out"), "--state", str(state)])
        == 0
    )
    rendered = json.loads(next((tmp_path / "out").glob("*.json")).read_text(encoding="utf-8"))
    assert rendered["number"] == 1


def test_email_settings(edition):
    with pytest.raises(ValueError):
        EmailSettings.from_env({})
    settings = EmailSettings.from_env(
        {
            "DAILYME_SMTP_HOST": "smtp.example.com",
            "DAILYME_SMTP_PORT": "465",
            "DAILYME_SMTP_USER": "me@example.com",
            "DAILYME_EMAIL_TO": "me@example.com, kindle@example.com",
        }
    )
    assert settings.use_ssl and settings.sender == "me@example.com"
    assert settings.recipients == ["me@example.com", "kindle@example.com"]

    subject = subject_for(edition, "{paper} · {weekday} {day} {month}")
    assert subject == "The Daily Me · Tuesday 10 November"
    message = build_message(edition, settings, subject=subject, html="<p>hi</p>", text="hi")
    assert message["To"] == "me@example.com, kindle@example.com"
    assert message.get_body(("html",)).get_content().strip() == "<p>hi</p>"
