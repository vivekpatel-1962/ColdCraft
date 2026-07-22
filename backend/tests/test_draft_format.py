"""Regression tests for the draft-formatting failure.

A draft shipped as one unbroken block containing literal backslash-n sequences and
the verifier reported it clean. These lock in both halves of the fix: the writer
repairs the artifact, and the verifier refuses to call it clean.

Run: python -m tests.test_draft_format
"""
from app.models import EmailDraft
from app.pipeline.verifier import _format_issues
from app.pipeline.writer import _clean_body

BS = chr(92)  # a real backslash, built unambiguously

# The exact shape that shipped: literal backslash-n, no greeting, no sign-off.
BAD_BODY = (
    "Nanonets' Data Extraction Agent returning clean markdown and structured JSON via "
    "API targets the same core pipeline challenges I solved at OPTERA. I engineered a "
    "production vision-LLM pipeline using FastAPI and Google Gemini 2.5 Flash to extract "
    "handwritten logs and meter photos into JSON across approximately 10 multi-tenant "
    "clients. To reduce inference costs on scaling OCR-3 pipelines, I implemented image "
    "preprocessing, SSIM frame de-duplication, and dynamic Gemini model routing based on "
    "image quality. Additionally, I built an async GCP backend with PM2 workers and "
    "FastAPI to reliably serve these multi-tenant extraction jobs."
    + BS + "n" + BS + "n" +
    "Open to a brief 10-minute technical chat next Tuesday?"
    + BS + "n" + BS + "n" + "Vivek Patel"
)

GOOD_BODY = """Hi there,

Nanonets' Data Extraction Agent returns structured JSON from documents through an API. That is the same problem I spent my internship on at OPTERA.

I built a production vision-LLM pipeline with FastAPI and Gemini. It extracts handwritten depot logs and meter photos into schema-validated JSON for around ten multi-tenant clients. I also cut the inference bill using image preprocessing, SSIM frame de-duplication, and model routing based on image quality.

Worth a ten-minute call next week to compare notes on routing and deduplication approaches for document pipelines at scale?

Best,
Vivek Patel"""


def _draft(body: str) -> EmailDraft:
    return EmailDraft(subject="Vision-LLM extraction pipelines", body=body, opening_line="x")


def test_literal_escapes_detected():
    issues = _format_issues(_draft(BAD_BODY))
    assert any("escape" in i for i in issues), f"escape artifact not flagged: {issues}"
    assert any("greeting" in i for i in issues), "missing greeting not flagged"
    assert any("sign-off" in i for i in issues), "missing sign-off not flagged"
    print(f"  bad draft -> {len(issues)} issue(s) flagged (was: passed clean)")
    for i in issues:
        print(f"    ! {i}")


def test_clean_body_repairs_escapes():
    fixed = _clean_body(BAD_BODY)
    assert BS + "n" not in fixed, "literal backslash-n survived the repair"
    assert "\n\n" in fixed, "repair did not produce real paragraph breaks"
    print(f"  repaired -> {fixed.count(chr(10) + chr(10))} real paragraph break(s), no artifacts")


def test_good_draft_is_clean():
    issues = _format_issues(_draft(GOOD_BODY))
    assert issues == [], f"well-formed draft wrongly flagged: {issues}"
    wc = len(GOOD_BODY.split())
    assert 90 <= wc <= 140, f"fixture should sit in range, got {wc}"
    print(f"  good draft -> clean, {wc} words")


if __name__ == "__main__":
    for fn in (test_literal_escapes_detected, test_clean_body_repairs_escapes, test_good_draft_is_clean):
        print(f"{fn.__name__}:")
        fn()
    print("\nall draft-format regression tests passed")
