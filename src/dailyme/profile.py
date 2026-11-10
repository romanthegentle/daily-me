"""The reader's profile: who they are and what the paper should cover."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

PROFILE_ENV = "DAILYME_PROFILE"


class Location(BaseModel):
    name: str = ""
    region: str = ""
    country: str = ""  # two-letter code, such as "NG"
    timezone: str = "UTC"
    latitude: float | None = None
    longitude: float | None = None


class Reader(BaseModel):
    name: str = "Reader"
    about: str = ""
    location: Location = Field(default_factory=Location)


class SectionSpec(BaseModel):
    name: str
    interests: list[str] = Field(default_factory=list)
    notes: str = ""
    feeds: list[str] = Field(default_factory=list)
    max_articles: int = Field(default=3, ge=0, le=8)
    max_briefs: int = Field(default=3, ge=0, le=10)


class Sources(BaseModel):
    prefer: list[str] = Field(default_factory=list)
    block: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    model: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    window_hours: int = Field(default=36, ge=6, le=24 * 7)
    searches_per_section: int = Field(default=5, ge=1, le=20)
    fetches_per_section: int = Field(default=4, ge=0, le=20)
    parallel_sections: int = Field(default=4, ge=1, le=10)
    fallbacks: bool = True


class Delivery(BaseModel):
    subject: str = "{paper} · {weekday} {day} {month}"
    pdf: bool = False
    attach_pdf: bool = False


class Paper(BaseModel):
    name: str = "The Daily Me"
    tagline: str = "All the news that fits me"


class Profile(BaseModel):
    paper: Paper = Field(default_factory=Paper)
    reader: Reader = Field(default_factory=Reader)
    sections: list[SectionSpec]
    serendipity: bool = True
    avoid: list[str] = Field(default_factory=list)
    sources: Sources = Field(default_factory=Sources)
    settings: Settings = Field(default_factory=Settings)
    delivery: Delivery = Field(default_factory=Delivery)

    @field_validator("sections")
    @classmethod
    def _needs_a_section(cls, sections: list[SectionSpec]) -> list[SectionSpec]:
        if not sections:
            raise ValueError("add at least one section")
        return sections


def load_profile(path: str | Path | None = None) -> Profile:
    """Load the profile from `path`, else from $DAILYME_PROFILE, else from ./profile.yaml."""
    env_text = os.environ.get(PROFILE_ENV, "")
    if path is None and env_text.strip():
        data = yaml.safe_load(env_text)
    else:
        file = Path(path) if path is not None else Path("profile.yaml")
        if not file.exists():
            raise FileNotFoundError(
                f"no profile at {file}. Run `dailyme init` to create one, "
                f"or put your profile in the {PROFILE_ENV} environment variable."
            )
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
    return Profile.model_validate(data or {})


def example_profile_text() -> str:
    return files("dailyme").joinpath("profile.example.yaml").read_text(encoding="utf-8")
