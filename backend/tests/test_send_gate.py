"""Tests for the send gate — the part where a mistake is not recoverable.

An email that goes to the wrong person, unfinished, or twice cannot be un-sent,
so the interesting assertions here are all about *refusing*: no confirmation, no
recipient, a FAIL verdict, an already-sent email. `gmail.send_raw` is replaced
with a tripwire that raises, so any test that accidentally reaches the network
fails loudly instead of mailing a stranger.

Run: python -m tests.test_send_gate
"""
import tempfile
from pathlib import Path

from app import config

# Point at a throwaway DB before anything opens the real one.
_TMP = Path(tempfile.mkdtemp(prefix="coldmail-send-test-"))
config.DATABASE_PATH = _TMP / "test.db"
config.RESUME_PATH = None

from app.db import database  # noqa: E402
from app.models import CandidateProfile, Claim, ClaimStrength, ClaimType, ContactInfo  # noqa: E402
from app.send import compose, gmail  # noqa: E402
from app.send.compose import NotSendable  # noqa: E402

SENDER = "sending.account@gmail.com"
RESUME_EMAIL = "on.my.resume@gmail.com"


class Tripwire(AssertionError):
    """Raised if anything in these tests reaches the real send path."""


def _tripwire(*a, **kw):
    raise Tripwire("send_raw was called — a test reached the network")


gmail.send_raw = _tripwire
gmail.authorized_address = lambda: SENDER


def _profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Vivek Patel",
        headline="CS undergrad, backend + applied ML",
        contact=ContactInfo(email=RESUME_EMAIL, phone="+91 90000 00000",
                            github="https://github.com/vivekpatel-1962"),
        claims=[Claim(id="C1", type=ClaimType.project, name="StudySavvy",
                      summary="Built a study planner.", evidence_span="StudySavvy",
                      strength=ClaimStrength.concrete)],
        primary_skills=["python", "fastapi"],
    )


def _seed(verdict: str = "pass", recipient: str | None = "hr@example.com",
          resume: Path | None = None) -> int:
    """A fresh run + draft; returns the email id."""
    database.init_db()
    profile_id = database.save_candidate_profile(
        "resume.pdf", "raw text", _profile().model_dump_json(),
        resume_path=str(resume) if resume else None,
    )
    company_id = database.upsert_company("example.com", "Example")
    cp_id = database.save_company_profile(company_id, '{"name": "Example"}', "rich", "[]")
    run_id = database.create_run(profile_id, cp_id, None, recipient)
    database.save_plan(run_id, "{}")
    email_id = database.save_draft(
        run_id, "{}", "Backend intern application", "Hi there,\n\nBody.\n\nBest,\nVivek Patel", "Hi there,"
    )
    database.save_verifier(run_id, f'{{"verdict": "{verdict}", "notes": "n", "format_issues": []}}')
    return email_id


def test_refuses_without_confirmation():
    """The whole design rests on this one: a clean, sendable email still does not
    go out unless a human said so."""
    email_id = _seed()
    env = compose.build_envelope(email_id)
    assert env.sendable, f"fixture should be sendable, blocked by: {env.blockers}"
    try:
        compose.send(email_id)  # confirm defaults to False
    except NotSendable as e:
        assert "confirm" in str(e).lower()
        print(f"  clean email, no confirmation -> refused ({e})")
        return
    raise AssertionError("send() transmitted without confirm=True")


def test_no_recipient_blocks():
    env = compose.build_envelope(_seed(recipient=None))
    assert any("recipient" in b.lower() for b in env.blockers), env.blockers
    assert not env.sendable
    print(f"  no recipient -> blocked ({env.blockers[0][:48]}...)")


def test_failed_verdict_blocks_until_overridden():
    email_id = _seed(verdict="fail")
    env = compose.build_envelope(email_id)
    assert any("FAIL" in b for b in env.blockers), env.blockers
    try:
        compose.send(email_id, confirm=True, dry_run=True)
        raise AssertionError("an ungrounded email was allowed through")
    except NotSendable:
        pass
    result = compose.send(email_id, confirm=True, dry_run=True, override_verdict=True)
    assert result.dry_run and not result.sent
    print("  verdict=fail -> blocked; explicit override_verdict -> allowed")


def test_revise_warns_but_does_not_block():
    env = compose.build_envelope(_seed(verdict="revise"))
    assert env.sendable, env.blockers
    assert any("REVISE" in w for w in env.warnings), env.warnings
    print("  verdict=revise -> warned, still the human's call")


def test_already_sent_blocks_resend():
    email_id = _seed()
    database.mark_email_sent(email_id, "hr@example.com", "s", "b", "msg1", "thr1", "resume.pdf")
    env = compose.build_envelope(email_id)
    assert any("Already sent" in b for b in env.blockers), env.blockers
    print("  already sent -> blocked (no accidental double-send)")


def test_sender_mismatch_sets_reply_to():
    """The sending Gmail account isn't the address in the resume signature, so
    replies must be steered back to the signature address."""
    env = compose.build_envelope(_seed())
    assert env.from_address == SENDER
    assert env.reply_to == RESUME_EMAIL, env.reply_to
    assert any(RESUME_EMAIL in w for w in env.warnings), env.warnings
    print(f"  from={env.from_address} reply-to={env.reply_to} (+ warned)")


def test_mime_carries_the_resume():
    pdf = _TMP / "Vivek_Patel_Resume.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake resume bytes")
    env = compose.build_envelope(_seed(resume=pdf))
    assert env.attachment and env.attachment.filename == pdf.name

    msg = compose.render_mime(env)
    assert msg.is_multipart(), "attachment did not produce a multipart message"
    parts = [p.get_filename() for p in msg.iter_attachments()]
    assert pdf.name in parts, parts
    assert msg["To"] == "hr@example.com"
    assert msg["Reply-To"] == RESUME_EMAIL
    assert "Vivek Patel" in msg["From"] and SENDER in msg["From"]
    attached = next(p for p in msg.iter_attachments() if p.get_filename() == pdf.name)
    assert attached.get_payload(decode=True) == pdf.read_bytes(), "attachment bytes differ"
    print(f"  multipart: body + {parts} ({env.attachment.size_bytes} bytes, byte-identical)")


def test_dry_run_does_not_record_a_send():
    email_id = _seed()
    result = compose.send(email_id, confirm=True, dry_run=True)
    assert result.dry_run and not result.sent
    row = database.get_email(email_id)
    assert row["status"] == "draft" and row["sent_at"] is None, "dry run mutated the email row"
    print("  dry run -> nothing transmitted, nothing recorded")


if __name__ == "__main__":
    tests = [
        test_refuses_without_confirmation,
        test_no_recipient_blocks,
        test_failed_verdict_blocks_until_overridden,
        test_revise_warns_but_does_not_block,
        test_already_sent_blocks_resend,
        test_sender_mismatch_sets_reply_to,
        test_mime_carries_the_resume,
        test_dry_run_does_not_record_a_send,
    ]
    for fn in tests:
        print(f"{fn.__name__}:")
        fn()
    print(f"\nall {len(tests)} send-gate tests passed (nothing was sent)")
