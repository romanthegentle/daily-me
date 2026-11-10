"""The shape of an edition: sections, articles, briefs and the front page."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

KINDS = ("news", "analysis", "follow_up", "release", "research", "opinion", "feature")
Kind = Literal["news", "analysis", "follow_up", "release", "research", "opinion", "feature"]


class Source(BaseModel):
    """A page an article relies on."""

    url: str
    title: str = ""
    publisher: str = ""


class Article(BaseModel):
    id: str = ""
    section: str = ""
    headline: str
    dek: str = Field(default="", description="One-sentence subheadline.")
    body: list[str] = Field(default_factory=list, description="Short paragraphs.")
    why_it_matters: str = Field(default="", description="Why this matters to this reader.")
    importance: int = Field(default=5, ge=1, le=10)
    kind: Kind = "news"
    published: str = Field(default="", description="Publication date, YYYY-MM-DD.")
    sources: list[Source] = Field(default_factory=list)


class Brief(BaseModel):
    """A one-line item with a link."""

    text: str
    url: str
    publisher: str = ""


class Section(BaseModel):
    name: str
    note: str = Field(default="", description="Shown when there's little to report.")
    articles: list[Article] = Field(default_factory=list)
    briefs: list[Brief] = Field(default_factory=list)


class Weather(BaseModel):
    place: str
    summary: str
    high_c: float | None = None
    low_c: float | None = None


class FrontPage(BaseModel):
    greeting: str = ""
    lead_id: str | None = None
    top_ids: list[str] = Field(default_factory=list)


class Edition(BaseModel):
    paper_name: str = "The Daily Me"
    tagline: str = ""
    reader: str = ""
    date: str = Field(description="Edition date, YYYY-MM-DD.")
    number: int = 1
    front: FrontPage = Field(default_factory=FrontPage)
    sections: list[Section] = Field(default_factory=list)
    weather: Weather | None = None
    generated_by: str = ""
    cost_usd: float | None = None

    def articles(self) -> list[Article]:
        return [article for section in self.sections for article in section.articles]

    def find(self, article_id: str | None) -> Article | None:
        if not article_id:
            return None
        return next((a for a in self.articles() if a.id == article_id), None)

    def lead(self) -> Article | None:
        """The front-page lead: the editor's pick, else the most important story."""
        chosen = self.find(self.front.lead_id)
        if chosen is not None:
            return chosen
        articles = self.articles()
        return max(articles, key=lambda a: a.importance) if articles else None

    def top(self) -> list[Article]:
        """The other front-page stories, in the editor's order."""
        lead = self.lead()
        picked: list[Article] = []
        for article_id in self.front.top_ids:
            article = self.find(article_id)
            if article is not None and article is not lead and article not in picked:
                picked.append(article)
        return picked

    def front_page_ids(self) -> set[str]:
        ids = {a.id for a in self.top()}
        lead = self.lead()
        if lead is not None:
            ids.add(lead.id)
        return ids
