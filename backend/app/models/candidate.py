"""Stage 1 output: the candidate claims ledger.

Every downstream stage (matcher, planner, writer) references claims by ID.
The writer may only use claims it was explicitly given — this is the
hallucination-control backbone.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    project = "project"
    experience = "experience"
    achievement = "achievement"
    skill = "skill"
    education = "education"
    interest = "interest"


class ClaimStrength(str, Enum):
    quantified = "quantified"  # carries a number/metric ("cut latency 40%")
    concrete = "concrete"      # specific but unquantified ("built the deploy pipeline")
    vague = "vague"            # generic ("worked on backend systems")


class Claim(BaseModel):
    id: str = Field(description="Stable ID like C1, C2 — referenced by all downstream stages")
    type: ClaimType
    name: str = Field(description="Short name, e.g. 'Realtime fleet dashboard' or 'python'")
    summary: str = Field(description="One-sentence factual statement of the claim")
    skills: list[str] = Field(default_factory=list, description="Lowercase skill tags involved")
    achievement: Optional[str] = Field(
        default=None, description="Outcome/impact statement if the resume states one"
    )
    evidence_span: str = Field(
        description="Short quote or location from the resume text supporting this claim"
    )
    strength: ClaimStrength
    period: Optional[str] = Field(
        default=None, description="When, as written in the resume, e.g. '2024-2025' or 'Jun 2025'"
    )


class CandidateProfile(BaseModel):
    full_name: str
    headline: str = Field(description="One-line professional identity, e.g. 'CS undergrad, full-stack + ML'")
    contact_email: Optional[str] = None
    claims: list[Claim]
    primary_skills: list[str] = Field(
        default_factory=list,
        description="5-10 lowercase skills the candidate is strongest in, ordered by depth",
    )
