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


class EmailKind(str, Enum):
    application = "application"  # applying for a role: introduce yourself, attach resume, show range
    outreach = "outreach"        # cold outreach, no specific role: tighter, one angle


class Bridge(BaseModel):
    claim_id: str = Field(description="Candidate claim ID this bridge uses")
    fact_id: str = Field(description="Company fact ID this bridge connects to")
    point: str = Field(description="The single connection to make in the email, one line")


class EmailPlan(BaseModel):
    email_kind: EmailKind = Field(
        default=EmailKind.outreach,
        description="application when target_role is set (introduce the candidate, show range, "
                    "reference the attached resume); outreach otherwise (tighter, single angle).",
    )
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
    supporting_claims: list[str] = Field(
        default_factory=list,
        description="For an application: 1-3 ADDITIONAL claim IDs (beyond the bridges) to mention "
                    "briefly, to show range — pick ones that broaden the picture toward this company's "
                    "domain (e.g. a relevant project or a second skill area). Empty for tight outreach.",
    )
    tone: Tone
    opening_hook: str = Field(
        description="The first line. Must earn its place: a specific point of relevance or insight. "
                    "NEVER a fact the company already knows about itself, never flattery."
    )
    closing_note: str = Field(
        default="",
        description="A short, GROUNDED buildup for the close (applications only): what the candidate "
                    "would bring and why they genuinely want THIS role/company — anchored to a real "
                    "detail (the company's domain, the role, the candidate's trajectory). For a "
                    "student/intern a learning-and-growth angle is fine IF specific. It must feel "
                    "earned and confident, never pleading or generic. Do NOT use empty enthusiasm "
                    "('passionate', 'excited about the opportunity', 'fast learner'). Empty for outreach.",
    )
    call_to_action: str = Field(description="The single, low-friction ask.")
    banned_phrases: list[str] = Field(
        default_factory=list,
        description="AI-tell / flattery phrases the writer must avoid (e.g. 'cutting-edge', 'passionate').",
    )
    excluded_notable: list[str] = Field(
        default_factory=list,
        description="Strong candidate claims deliberately left OUT, each with a short why. For an "
                    "application this is smaller (breadth is wanted); for outreach it enforces focus.",
    )
    word_target: int = Field(
        default=120, ge=90, le=200,
        description="Target length. Outreach: 90-140. Application (intro + range + fit + resume "
                    "reference): 140-190 — a proper introduction needs the room.",
    )
