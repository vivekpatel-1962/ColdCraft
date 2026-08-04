"""Tests for the deterministic recruiter plain-language pass.

The manektech run kept coming back REVISE because the writer left engineer-only
terms in an email addressed to hr@ — model variance, not a prompt bug. These lock
in the guarantee that replaced it, and the invariant that makes it work: the
translation table's own output must never trip the verifier's jargon check.

Run: python -m tests.test_plain_language
"""
from app.models import EmailDraft, EmailPlan, RecipientType
from app.pipeline.plain_language import TRANSLATIONS, simplify, simplify_for_recruiter
from app.pipeline.verifier import DEEP_JARGON, _jargon_issues

# The real shape of the flagged manektech draft: three engineer-only terms.
ENGINEER_BODY = (
    "Hi there,\n\n"
    "I built a production vision-LLM pipeline that extracts handwritten depot logs into "
    "schema-validated JSON across roughly ten multi-tenant clients.\n\n"
    "I cut the inference bill with SSIM frame de-duplication and dynamic model routing, "
    "and ran the whole thing on PM2 workers with cron scheduling.\n\n"
    "Best,\nVivek Patel"
)


def _plan(recipient: RecipientType) -> EmailPlan:
    """A minimal plan — only recipient_type matters to the jargon check."""
    return EmailPlan.model_construct(recipient_type=recipient, target_role=None)


def test_replacements_are_themselves_jargon_free():
    """The invariant the whole pass rests on: if a replacement contained a term
    from DEEP_JARGON, the verifier would flag our own rewrite and the loop would
    never close."""
    offenders = [
        (term, plain, j)
        for term, plain in TRANSLATIONS.items()
        for j in DEEP_JARGON
        if j in plain.lower()
    ]
    assert not offenders, f"replacement text contains jargon: {offenders}"
    print(f"  {len(TRANSLATIONS)} replacements, none containing a DEEP_JARGON term")


def test_recruiter_draft_loses_the_jargon():
    out, edits = simplify_for_recruiter(ENGINEER_BODY, is_recruiter=True)
    low = out.lower()
    leftover = [j for j in DEEP_JARGON if j in low]
    assert not leftover, f"still jargon after the pass: {leftover}"
    assert edits, "pass reported no edits on a draft full of jargon"

    draft = EmailDraft(subject="s", body=out, opening_line="x")
    assert _jargon_issues(draft, _plan(RecipientType.recruiter)) == []
    print(f"  {len(edits)} term(s) translated -> verifier jargon check clean")
    for e in edits:
        print(f"    {e}")


def test_untranslated_draft_still_fails_the_check():
    """Guards the test above from being vacuous — the fixture really is a REVISE
    without the pass."""
    draft = EmailDraft(subject="s", body=ENGINEER_BODY, opening_line="x")
    issues = _jargon_issues(draft, _plan(RecipientType.recruiter))
    assert issues, "fixture no longer trips the jargon check — it proves nothing"
    print(f"  untouched fixture -> {issues[0][:70]}...")


def test_engineer_keeps_the_real_terms():
    """Translating for an engineer would cost information, so the gate matters."""
    out, edits = simplify_for_recruiter(ENGINEER_BODY, is_recruiter=False)
    assert out == ENGINEER_BODY and edits == []
    assert _jargon_issues(
        EmailDraft(subject="s", body=out, opening_line="x"), _plan(RecipientType.engineer)
    ) == []
    print("  engineer recipient -> body untouched, check does not fire")


def test_urls_and_emails_survive():
    text = ("See github.com/vivekpatel-1962/dedup-tools and mail me at "
            "cron.person@example.com about de-duplication.")
    out, _ = simplify(text)
    assert "github.com/vivekpatel-1962/dedup-tools" in out, out
    assert "cron.person@example.com" in out, out
    assert "duplicate removal" in out, out
    print("  repo path 'dedup-tools' and address 'cron.person@' preserved; prose rewritten")


def test_case_follows_position_not_the_matched_text():
    """Acronyms are upper case wherever they sit, so case has to come from where
    the match is — otherwise mid-sentence SSIM yields a stray capital."""
    out, _ = simplify("Deduplication cut the bill. We used SSIM too.")
    assert out == "Duplicate removal cut the bill. We used image-similarity scoring too.", out
    print(f"  {out!r}")


def test_pass_is_idempotent():
    once, _ = simplify(ENGINEER_BODY)
    twice, edits = simplify(once)
    assert once == twice and edits == [], "second pass changed the text"
    print("  running it twice is a no-op")


def test_longest_match_wins():
    out, _ = simplify("We used SSIM frame de-duplication.")
    assert out == "We used skipping near-identical frames.", out
    assert "image-similarity scoring" not in out, "short 'ssim' rule fired inside the long phrase"
    print(f"  {out!r}")


if __name__ == "__main__":
    tests = [
        test_replacements_are_themselves_jargon_free,
        test_untranslated_draft_still_fails_the_check,
        test_recruiter_draft_loses_the_jargon,
        test_engineer_keeps_the_real_terms,
        test_urls_and_emails_survive,
        test_case_follows_position_not_the_matched_text,
        test_pass_is_idempotent,
        test_longest_match_wins,
    ]
    for fn in tests:
        print(f"{fn.__name__}:")
        fn()
    print(f"\nall {len(tests)} plain-language tests passed")
