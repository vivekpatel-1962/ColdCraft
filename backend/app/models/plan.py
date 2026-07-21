"""Stage 4 output: the email plan.

The plan is the writer's entire world. The writer (stage 5) sees ONLY this plan
plus the specific claims/facts it references — never the full profiles — so the
plan is where all the judgment happens: one angle, a few bridges, a tone, and the
guardrails (banned phrases, and what was deliberately excluded).
"""
from enum import Enum

from pydantic import BaseModel, Field


class Tone(str, Enum):
    peer_technical = "peer_technical"   # engineer-to-engineer, specific, no fluff
    warm_direct = "warm_direct"         # friendly but brief
    concise_formal = "concise_formal"   # measured, professional


class Bridge(BaseModel):
    claim_id: str = Field(description="Candidate claim ID this bridge uses")
    fact_id: str = Field(description="Company fact ID this bridge connects to")
    point: str = Field(description="The single connection to make in the email, one line")


class EmailPlan(BaseModel):
    angle: str = Field(
        description="The ONE thesis — the single strongest reason to reach out. Everything serves this."
    )
    bridges: list[Bridge] = Field(
        description="2-3 claim->fact bridges that build the angle. Each references real IDs."
    )
    tone: Tone
    opening_hook: str = Field(
        description="What to open with — grounded in a specific company fact, never flattery or adjectives about them."
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
