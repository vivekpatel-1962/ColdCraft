"""Stage 3 output: ranked overlaps between candidate claims and company facts.

Each overlap bridges one claim ID to one fact ID with a rubric score — the raw
material the planner turns into a single email angle. One evidence-based fit
score for the whole match (not three separate scores — deliberate).
"""
from enum import Enum

from pydantic import BaseModel, Field


class OverlapKind(str, Enum):
    skill_match = "skill_match"                    # shared concrete skill/technology
    domain_match = "domain_match"                  # same problem domain (OCR, voice AI, ...)
    achievement_relevance = "achievement_relevance"  # candidate outcome maps to a company need
    stack_match = "stack_match"                    # same tools/infrastructure


class Overlap(BaseModel):
    claim_id: str = Field(description="CandidateProfile claim ID, e.g. C3")
    fact_id: str = Field(description="CompanyProfile fact ID, e.g. F5")
    kind: OverlapKind
    score: float = Field(ge=0.0, le=1.0, description="Rubric relevance, 0.0-1.0")
    rationale: str = Field(description="One line: why this claim and this fact connect")


class RankedOverlaps(BaseModel):
    overlaps: list[Overlap] = Field(description="Overlaps, strongest first")
    fit_score: int = Field(ge=0, le=100, description="Overall evidence-based fit, 0-100")
    fit_summary: str = Field(description="One neutral sentence explaining the score. No flattery.")
