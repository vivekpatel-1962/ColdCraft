"""Stage 0: intake — resolve whatever the user has into (website, recipient).

Three ways in:
  - a company website        -> scrape it, no recipient known yet
  - a contact email address   -> derive the domain, scrape that, recipient known
  - a "we're hiring" poster   -> vision-extract BOTH the website and the recipient,
                                 plus the role/requirements, which are the highest
                                 signal input the pipeline can get (it's a job posting)
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class IntakeSource(str, Enum):
    website = "website"
    email = "email"
    poster = "poster"


class HiringPoster(BaseModel):
    """What a recruitment graphic actually contains. Extracted by a vision call."""
    company_name: str = Field(description="Company name exactly as printed")
    website: Optional[str] = Field(
        default=None, description="Company website if printed, e.g. 'www.company.com'"
    )
    contact_email: Optional[str] = Field(
        default=None, description="Application/contact email if printed, e.g. 'hr@company.com'"
    )
    role_title: Optional[str] = Field(default=None, description="The role being advertised")
    job_type: Optional[str] = Field(default=None, description="Internship / full-time / contract")
    location: Optional[str] = Field(default=None, description="Location as printed")
    responsibilities: list[str] = Field(
        default_factory=list, description="'What you'll do' bullets, verbatim"
    )
    requirements: list[str] = Field(
        default_factory=list, description="'Who can apply' / qualification bullets, verbatim"
    )
    about_company: Optional[str] = Field(
        default=None, description="Any 'about the company' blurb printed on the poster"
    )

    def as_context(self) -> str:
        """Render as a text block the company-intel stage can treat as a source."""
        lines = [f"Company: {self.company_name}"]
        for label, val in (("Role", self.role_title), ("Job type", self.job_type),
                           ("Location", self.location), ("About", self.about_company)):
            if val:
                lines.append(f"{label}: {val}")
        if self.responsibilities:
            lines.append("Responsibilities:\n" + "\n".join(f"- {r}" for r in self.responsibilities))
        if self.requirements:
            lines.append("Requirements:\n" + "\n".join(f"- {r}" for r in self.requirements))
        return "\n".join(lines)


class IntakeResult(BaseModel):
    source: IntakeSource
    company_url: Optional[str] = Field(default=None, description="Normalized URL to scrape")
    recipient_email: Optional[str] = Field(default=None, description="Where the email would be sent")
    poster: Optional[HiringPoster] = None
    notes: list[str] = Field(default_factory=list, description="How each field was derived")
