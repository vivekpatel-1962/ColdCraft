"""Render a stored draft into the exact message that would be transmitted.

The whole point of this module is that `build_envelope()` is pure inspection —
it reads the DB, resolves the attachment, and reports every reason a human might
want to stop, without touching the network. `send()` is the only thing that
transmits, and it refuses unless the caller passes `confirm=True`.
"""
import base64
import json
import logging
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path
from typing import Optional

from app import config
from app.db import database
from app.models import CandidateProfile
from app.models.send import Attachment, SendEnvelope, SendResult
from app.send import gmail

log = logging.getLogger("coldmail.send")

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024  # Gmail's practical ceiling for this endpoint


class NotSendable(RuntimeError):
    """The envelope has blockers, or the caller didn't confirm."""


def _resume_attachment(profile_row) -> tuple[Optional[Attachment], list[str]]:
    """The PDF to attach: the path recorded at analyze time, else RESUME_PATH."""
    warnings: list[str] = []
    candidates: list[Path] = []

    recorded = profile_row["resume_path"] if "resume_path" in profile_row.keys() else None
    if recorded:
        candidates.append(Path(recorded))
    if config.RESUME_PATH:
        candidates.append(Path(config.RESUME_PATH))

    for path in candidates:
        if path.exists() and path.is_file():
            size = path.stat().st_size
            if size > MAX_ATTACHMENT_BYTES:
                warnings.append(f"{path.name} is {size / 1e6:.1f} MB — too large to attach")
                continue
            return Attachment(filename=path.name, size_bytes=size, path=str(path)), warnings

    if recorded:
        warnings.append(
            f"Resume not found at the path used when the profile was analyzed ({recorded}). "
            "Set RESUME_PATH in backend/.env to attach it."
        )
    else:
        warnings.append(
            "No resume file configured — set RESUME_PATH in backend/.env (or re-run "
            "scripts.analyze_resume, which now records the path) to attach it."
        )
    return None, warnings


def build_envelope(email_id: int, recipient_override: str | None = None) -> SendEnvelope:
    """Exactly what would go out. Reads only — never sends."""
    database.init_db()
    row = database.get_email(email_id)
    if row is None:
        raise NotSendable(f"No email #{email_id}")

    run = database.get_run_for_email(email_id)
    body = row["final_body"] or row["generated_body"] or ""
    subject = row["subject"] or ""
    to = recipient_override or row["recipient"] or (run["recipient_email"] if run else None)

    warnings: list[str] = []
    blockers: list[str] = []

    if row["final_body"]:
        warnings.append("Sending your edited version (final_body), not the generated draft.")

    # --- who it comes from ---
    from_address = gmail.authorized_address()
    if from_address is None:
        st = gmail.status()
        blockers.append(st.detail or "Gmail is not authorized — run: python -m scripts.gmail_auth")

    # --- who it goes to ---
    if not to:
        blockers.append(
            "No recipient on this run. Pass one explicitly, or re-run intake with "
            "--email so the address is resolved and stored."
        )
    elif "@" not in to or "." not in to.split("@")[-1]:
        blockers.append(f"Recipient {to!r} does not look like an email address.")

    if not subject.strip():
        blockers.append("Subject is empty.")
    if not body.strip():
        blockers.append("Body is empty.")

    # --- the candidate side: display name, reply-to, attachment ---
    from_name = None
    reply_to = None
    attachment = None
    profile_row = (
        database.get_candidate_profile_by_id(run["candidate_profile_id"]) if run else None
    )
    if profile_row is not None:
        profile = CandidateProfile.model_validate_json(profile_row["profile_json"])
        from_name = profile.full_name
        signature_email = (profile.contact.email if profile.contact else None) or getattr(
            profile, "contact_email", None
        )
        if signature_email and from_address and signature_email.lower() != from_address.lower():
            reply_to = signature_email
            warnings.append(
                f"Sending from {from_address} but the resume signature says {signature_email} — "
                f"Reply-To is set to {signature_email} so replies land there."
            )
        attachment, attach_warnings = _resume_attachment(profile_row)
        warnings.extend(attach_warnings)

    # --- what the verifier thought ---
    if run and run["verifier_json"]:
        report = json.loads(run["verifier_json"])
        verdict = report.get("verdict")
        if verdict == "fail":
            blockers.append(
                f"Verifier verdict is FAIL ({report.get('notes', '')!r}) — an ungrounded email "
                "should not go out. Fix it, or send with override_verdict."
            )
        elif verdict == "revise":
            issues = (report.get("format_issues") or []) + (report.get("ai_tells") or [])
            warnings.append(
                "Verifier verdict is REVISE"
                + (f": {'; '.join(issues[:3])}" if issues else "")
            )
    else:
        warnings.append("This draft was never verified.")

    # --- don't send the same email twice by accident ---
    already = row["sent_at"] if row["status"] == "sent" else None
    if already:
        blockers.append(f"Already sent at {already} to {row['recipient']}. Pass allow_resend to send again.")

    if attachment is None and not any("too large" in w for w in warnings):
        warnings.append("No resume will be attached.")

    return SendEnvelope(
        email_id=email_id,
        from_address=from_address,
        from_name=from_name,
        reply_to=reply_to,
        to=to,
        subject=subject,
        body=body,
        attachment=attachment,
        warnings=warnings,
        blockers=blockers,
        already_sent_at=already,
    )


def render_mime(env: SendEnvelope) -> EmailMessage:
    """SendEnvelope -> RFC-822. Plain text: a cold application email that arrives
    as marketing-shaped HTML reads as a blast, which is the opposite of the point."""
    msg = EmailMessage()
    msg["To"] = env.to
    msg["Subject"] = env.subject
    msg["From"] = formataddr((env.from_name, env.from_address)) if env.from_name else env.from_address
    if env.reply_to:
        msg["Reply-To"] = env.reply_to
    msg.set_content(env.body)

    if env.attachment:
        data = Path(env.attachment.path).read_bytes()
        maintype, subtype = (
            ("application", "pdf")
            if env.attachment.filename.lower().endswith(".pdf")
            else ("application", "octet-stream")
        )
        msg.add_attachment(
            data, maintype=maintype, subtype=subtype, filename=env.attachment.filename
        )
    return msg


def create_gmail_draft(email_id: int, recipient_override: str | None = None) -> dict:
    """Save the email to the user's Gmail Drafts folder — it does NOT send. This is
    the safe path: the human opens the draft in Gmail, does the final review, and
    sends it themselves. A draft can be incomplete, so the only hard requirement is
    Gmail authorization; the send-time blockers (verifier fail, already sent) are
    surfaced as warnings, not gates."""
    env = build_envelope(email_id, recipient_override=recipient_override)
    if env.from_address is None:
        raise NotSendable(
            next((b for b in env.blockers if "authoriz" in b.lower()),
                 "Gmail is not authorized — run: python -m scripts.gmail_auth")
        )

    msg = render_mime(env)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = gmail.create_draft_raw(raw)
    draft_id = resp.get("id")
    log.info("Created Gmail draft %s for email #%s (to %s)", draft_id, email_id, env.to)

    # A draft isn't a send, but recording it lets the UI show "in Gmail Drafts".
    database.update_email(email_id, status="gmail_draft")
    return {
        "email_id": email_id,
        "gmail_draft_id": draft_id,
        "from_address": env.from_address,
        "reply_to": env.reply_to,
        "to": env.to,
        "subject": env.subject,
        "attachment": env.attachment.filename if env.attachment else None,
        "warnings": env.warnings,
    }


def send(
    email_id: int,
    confirm: bool = False,
    recipient_override: str | None = None,
    override_verdict: bool = False,
    allow_resend: bool = False,
    dry_run: bool = False,
) -> SendResult:
    """Transmit. Refuses without an explicit `confirm=True` from a human decision —
    there is no code path that reaches Gmail without one."""
    env = build_envelope(email_id, recipient_override=recipient_override)

    blockers = list(env.blockers)
    if override_verdict:
        blockers = [b for b in blockers if not b.startswith("Verifier verdict is FAIL")]
    if allow_resend:
        blockers = [b for b in blockers if not b.startswith("Already sent")]
    if blockers:
        raise NotSendable("; ".join(blockers))
    if not confirm:
        raise NotSendable(
            "Refusing to send without explicit confirmation (confirm=true). "
            "Review the envelope from build_envelope() first."
        )

    msg = render_mime(env)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    if dry_run:
        log.info("DRY RUN — not sending. %d bytes to %s", len(msg.as_bytes()), env.to)
        return SendResult(
            email_id=email_id, sent=False, to=env.to, from_address=env.from_address,
            subject=env.subject,
            attachment=env.attachment.filename if env.attachment else None,
            dry_run=True,
        )

    resp = gmail.send_raw(raw)
    log.info("Sent email #%s to %s (gmail id %s)", email_id, env.to, resp.get("id"))

    database.mark_email_sent(
        email_id=email_id,
        recipient=env.to,
        subject=env.subject,
        body=env.body,
        message_id=resp.get("id"),
        thread_id=resp.get("threadId"),
        attachment_filename=env.attachment.filename if env.attachment else None,
    )
    sent_row = database.get_email(email_id)
    return SendResult(
        email_id=email_id, sent=True, to=env.to, from_address=env.from_address,
        subject=env.subject, message_id=resp.get("id"), thread_id=resp.get("threadId"),
        attachment=env.attachment.filename if env.attachment else None,
        sent_at=sent_row["sent_at"] if sent_row else None,
    )
