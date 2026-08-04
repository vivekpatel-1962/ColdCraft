"""Deterministic recruiter-language pass.

The writer prompt tells the model to translate engineer-only terms when the reader
is a recruiter. It usually does — but "usually" is the problem: across runs the
same email would sometimes ship with `SSIM frame de-duplication` intact and get a
REVISE from the jargon check. A prompt is a request; this is a guarantee.

So the translation happens twice, on purpose: the model does it well (rephrasing
the whole sentence), and this pass catches whatever slipped through. It only runs
for `recipient_type == recruiter` — an engineer reading "skipping near-identical
frames" instead of "SSIM de-duplication" learns less about the candidate, so the
real terms stay for technical readers.

The table is deliberately noun-phrase-for-noun-phrase: no attempt at clever
grammar, because a wrong rewrite is worse than an untranslated term. The verifier
still runs afterwards on the rewritten text, so grounding and readability are
re-checked, not assumed.
"""
import logging
import re

log = logging.getLogger("coldmail.plain_language")

# Every replacement must itself be free of DEEP_JARGON terms, or the verifier's
# jargon check would keep firing on our own output. test_plain_language locks that in.
TRANSLATIONS: dict[str, str] = {
    # Longest, most specific phrasings first — applied in length order below.
    "ssim frame de-duplication": "skipping near-identical frames",
    "ssim frame deduplication": "skipping near-identical frames",
    "frame de-duplication": "skipping near-identical frames",
    "frame deduplication": "skipping near-identical frames",
    "ssim de-duplication": "skipping near-identical frames",
    "async job queue": "a background job system",
    "pm2 workers": "background workers",
    "vector database": "a searchable knowledge store",
    "multi-tenant clients": "separate client organisations",
    "dynamic model routing": "automatic model selection",
    "model routing": "automatic model selection",
    "schema-validated json": "validated, structured data",
    "schema-validated": "validated",
    "de-duplication": "duplicate removal",
    "deduplication": "duplicate removal",
    "dedup": "duplicate removal",
    "multi-tenant": "multi-client",
    "quantization": "model compression",
    "orchestration": "coordination",
    "kubernetes": "cloud container tooling",
    "idempotent": "safe to retry",
    "middleware": "connecting services",
    "throughput": "how much it handles per hour",
    "embeddings": "meaning-based search",
    "sharding": "splitting data across servers",
    "protobuf": "a compact data format",
    "webhook": "automatic service-to-service updates",
    "termux": "scheduled automation on Android",
    "ssim": "image-similarity scoring",
    "grpc": "service-to-service APIs",
    "cron": "scheduled jobs",
    "k8s": "cloud container tooling",
    "pm2": "background worker",
}

# Longest first so "frame de-duplication" wins over "de-duplication".
_ORDERED = sorted(TRANSLATIONS.items(), key=lambda kv: len(kv[0]), reverse=True)

# Contact tokens are data, not prose — a repo called `dedup-tools` must survive.
_PROTECTED = re.compile(r"\S+@\S+|https?://\S+|(?:www\.|github\.com/|linkedin\.com/)\S+")


def _starts_sentence(text: str, index: int) -> bool:
    """Is the match at index the first word of a sentence?

    Case must come from POSITION, not from the matched text: acronyms are upper
    case wherever they sit, so keying off the match itself turned "We used SSIM
    frame de-duplication" into "We used Skipping near-identical frames".
    """
    before = text[:index].rstrip()
    return not before or before[-1] in ".!?:\n"


def simplify(text: str) -> tuple[str, list[str]]:
    """Returns (rewritten text, human-readable list of what changed)."""
    if not text:
        return text, []

    # Mask URLs/emails so substitutions can't corrupt a link or an address.
    masked: list[str] = []

    def _hide(m: re.Match) -> str:
        masked.append(m.group(0))
        return f"\x00{len(masked) - 1}\x00"

    out = _PROTECTED.sub(_hide, text)

    edits: list[str] = []
    for term, plain in _ORDERED:
        pattern = re.compile(rf"(?<![\w-]){re.escape(term)}(?![\w-])", re.IGNORECASE)

        def _sub(m: re.Match) -> str:
            if _starts_sentence(m.string, m.start()):
                return plain[:1].upper() + plain[1:]
            return plain

        out, n = pattern.subn(_sub, out)
        if n:
            edits.append(f"{term} -> {plain}" + (f" (x{n})" if n > 1 else ""))

    out = re.sub(r"\x00(\d+)\x00", lambda m: masked[int(m.group(1))], out)
    return out, edits


def simplify_for_recruiter(text: str, is_recruiter: bool) -> tuple[str, list[str]]:
    """The gate: engineers and founders keep the real vocabulary."""
    if not is_recruiter:
        return text, []
    out, edits = simplify(text)
    if edits:
        log.info("plain-language pass rewrote %d engineer term(s): %s", len(edits), "; ".join(edits))
    return out, edits
