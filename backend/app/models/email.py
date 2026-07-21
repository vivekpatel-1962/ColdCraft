"""Stage 5-6 outputs: the draft and the verifier report.

The draft is produced closed-world (writer sees only the plan + selected evidence).
The verifier then audits it against the FULL ledgers — grounding, style, length,
and opener repetition — and issues a verdict.
"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---- Stage 5: writer ----

class EmailDraft(BaseModel):
    subject: str = Field(description="Concrete, specific, <= 8 words. No clickbait.")
    body: str = Field(description="The email body, 90-140 words, signed with the candidate's name.")
    opening_line: str = Field(
        description="The exact first sentence of the body, verbatim — used for the repetition check."
    )


# ---- Stage 6: verifier ----

class ClaimCheck(BaseModel):
    sentence: str = Field(description="A factual sentence from the body")
    supported: bool
    evidence_id: Optional[str] = Field(
        default=None, description="The claim (C..) or fact (F..) ID that supports it, if any"
    )
    issue: Optional[str] = Field(default=None, description="If unsupported, what's wrong")


class VerifierLLM(BaseModel):
    """The LLM-judged portion. Deterministic checks are added in Python."""
    grounded: bool = Field(description="True only if no factual sentence is unsupported")
    claim_checks: list[ClaimCheck]
    ai_tells: list[str] = Field(
        default_factory=list, description="Phrases that read as AI-generated or as flattery"
    )
    notes: str = Field(description="One or two lines of actionable feedback")


class Verdict(str, Enum):
    passed = "pass"
    revise = "revise"
    fail = "fail"


class VerifierReport(BaseModel):
    verdict: Verdict
    grounded: bool
    claim_checks: list[ClaimCheck]
    ai_tells: list[str] = Field(default_factory=list)
    banned_hits: list[str] = Field(default_factory=list, description="Banned phrases found (deterministic)")
    word_count: int
    within_word_target: bool
    opener_repetition: Optional[str] = Field(
        default=None, description="Set if the opener is too similar to a past email's opener"
    )
    notes: str = ""
