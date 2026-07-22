"""Stage 4 output: the email plan.

The plan is the writer's entire world. The writer (stage 5) sees ONLY this plan
plus the specific claims/facts it references — never the full profiles — so the
plan is where all the judgment happens: one angle, a few bridges, a tone, and the
guardrails (banned phrases, and what was deliberately excluded).
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Tone(str, Enum):
    peer_technical = "peer_technical"   # engineer-to-engineer, specific, no fluff
    warm_direct = "warm_direct"         # friendly but brief
    concise_formal = "concise_formal"   # measured, professional


class RecipientType(str, Enum):
    """Who reads it decides how much jargon survives and what they care about."""
    recruiter = "recruiter"  # HR/talent: role fit, clarity, no deep jargon
    engineer = "engineer"    # technical peer: specifics land, respect their time
    founder = "founder"      # outcome/business framing over implementation
    unknown = "unknown"


class Bridge(BaseModel):
    claim_id: str = Field(description="Candidate claim ID this bridge uses")
    fact_id: str = Field(description="Company fact ID this bridge connects to")
    point: str = Field(description="The single connection to make in the email, one line")


class EmailPlan(BaseModel):
    angle: str = Field(
        description="The ONE thesis — the single strongest reason to reach out. Everything serves this."
    )
    value_to_them: str = Field(
        description="One line, from the READER's side: what this company gets. Not what the "
                    "candidate wants. If you cannot state a concrete gain, the angle is wrong."
    )
    target_role: Optional[str] = Field(
        default=None,
        description="The company's open role this maps to, copied from a hiring fact. When set, "
                    "the email is an application and must name the role.",
    )
    proof_point: str = Field(
        description="The single strongest piece of evidence, stated as an OUTCOME rather than a "
                    "technique. Prefer a quantified claim. This is what the email leads with."
    )
    recipient_type: RecipientType = Field(
        default=RecipientType.unknown,
        description="Who reads it — sets jargon level and what they care about.",
    )
    bridges: list[Bridge] = Field(
        description="2-3 claim->fact bridges that build the angle. Each references real IDs."
    )
    tone: Tone
    opening_hook: str = Field(
        description="The first line. Must earn its place: a specific point of relevance or insight. "
                    "NEVER a fact the company already knows about itself, never flattery."
    )
    call_to_action: str = Field(description="The single, low-friction ask.")
    banned_phrases: list[str] = Field(
        default_factory=list,
        description="AI-tell / flattery phrases the writer must avoid (e.g. 'cutting-edge', 'passionate').",
    )
    excluded_notable: list[str] = Field(
        default_factory=list,
        description="Strong candidate claims deliberately left OUT to keep one angle, each with a short why.",
    )
    word_target: int = Field(default=120, ge=90, le=140, description="Target email length, 90-140 words.")
