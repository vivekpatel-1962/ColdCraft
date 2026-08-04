"""Stage 7 (send) contracts.

Sending is split into two calls on purpose: `SendEnvelope` is exactly what WOULD
go out — rendered, inspected, and shown to the human — and only a separate,
explicitly-confirmed call actually transmits it. Nothing in this project ever
sends as a side effect of generating.
"""
from typing import Optional

from pydantic import BaseModel, Field


class GmailStatus(BaseModel):
    authorized: bool
    address: Optional[str] = Field(
        default=None, description="The Gmail account that completed the OAuth flow"
    )
    credentials_present: bool = Field(description="Is the OAuth client secret file on disk?")
    detail: str = ""


class Attachment(BaseModel):
    filename: str
    size_bytes: int
    path: str


class SendEnvelope(BaseModel):
    """The exact message that would be transmitted. Rendered, never sent."""
    email_id: int
    from_address: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = Field(
        default=None,
        description="Set when the sending account differs from the email in the resume "
                    "signature, so replies land where the signature says they will.",
    )
    to: Optional[str] = None
    subject: str
    body: str
    attachment: Optional[Attachment] = None
    warnings: list[str] = Field(
        default_factory=list,
        description="Things a human should look at before confirming (unset recipient, "
                    "verifier verdict, signature/sender mismatch, missing resume).",
    )
    blockers: list[str] = Field(
        default_factory=list, description="Reasons this cannot be sent at all yet"
    )
    already_sent_at: Optional[str] = None

    @property
    def sendable(self) -> bool:
        return not self.blockers


class SendResult(BaseModel):
    email_id: int
    sent: bool
    to: str
    from_address: str
    subject: str
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    attachment: Optional[str] = None
    sent_at: Optional[str] = None
    dry_run: bool = False
