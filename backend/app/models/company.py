"""Stage 2 output: the company facts ledger.

Mirror of the candidate claims ledger on the company side. Every fact has a
stable ID, a source URL, and a supporting quote — so any sentence the writer
later produces about the company is traceable to a page the scraper actually saw.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FactCategory(str, Enum):
    product = "product"          # what they build / sell
    technology = "technology"    # concrete stack, tools, infra
    traction = "traction"        # funding, customers, scale, growth
    team = "team"                # people, size, notable hires
    mission = "mission"          # stated purpose / problem they attack
    hiring = "hiring"            # roles/teams they are hiring for
    engineering = "engineering"  # eng practices, culture-of-building signals from tech content
    recent = "recent"            # recent launches / news / posts


class Fact(BaseModel):
    id: str = Field(description="Stable ID like F1, F2 — referenced by matcher/planner/writer")
    category: FactCategory
    statement: str = Field(description="One neutral, factual sentence about the company")
    source_url: str = Field(description="The scraped page URL this fact was drawn from")
    quote: str = Field(
        description="Short verbatim fragment from that page supporting the statement"
    )


class ProfileTier(str, Enum):
    rich = "rich"      # enough pages + text for a confident ledger
    thin = "thin"      # some content, ledger is partial — flag downstream
    manual = "manual"  # scrape failed; a human must supply the facts


class PageManifestEntry(BaseModel):
    """One row of the scrape audit trail — what was fetched and how."""
    url: str
    priority: str = Field(description="Which bucket matched: job_posting/careers/about/...")
    status: str = Field(description="ok | thin | error")
    method: str = Field(description="static | jina | none")
    char_count: int
    error: Optional[str] = None


class CompanyProfile(BaseModel):
    name: str = Field(description="Company name as it presents itself")
    domain: str = Field(description="Bare domain, e.g. 'stripe.com'")
    one_liner: str = Field(
        description="One neutral sentence: what the company does. No adjectives, no flattery."
    )
    facts: list[Fact]
    tech_signals: list[str] = Field(
        default_factory=list,
        description="Concrete technologies/tools the pages name (lowercase), e.g. 'kubernetes', 'go'",
    )
    hiring_signals: list[str] = Field(
        default_factory=list,
        description="Roles or teams they are visibly hiring for, if present",
    )
