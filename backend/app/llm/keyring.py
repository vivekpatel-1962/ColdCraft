"""Rotation over multiple Gemini API keys.

Gemini's free-tier quota is per-key per-day, so N keys ≈ N× the daily budget.
A stage call tries keys starting from the last known-good one; on a 429 it
rotates to the next. The cursor is persisted to a tiny file so the *next* process
(each CLI run is fresh) resumes at the last working key instead of wasting a
request re-hitting one that's already exhausted for the day.

The cursor file holds only an integer index — never a key.
"""
import logging

from app import config

log = logging.getLogger("coldmail.llm")

_CURSOR_PATH = config.DATABASE_PATH.parent / ".gemini_key_cursor"

# Keys known to be out of quota *in this process*. Without this, every stage
# re-probes a key that 429'd seconds earlier — one wasted request and ~2s per
# stage per dead key, which gets expensive once you rotate over many keys.
_exhausted: set[int] = set()


def _read_cursor() -> int:
    try:
        return max(0, int(_CURSOR_PATH.read_text().strip()))
    except Exception:
        return 0


def mark_exhausted(index: int) -> None:
    _exhausted.add(index)


def clear_exhausted() -> None:
    """Call when starting fresh work that may span a quota reset."""
    _exhausted.clear()


def exhausted_count() -> int:
    return len(_exhausted)


def remember(index: int) -> None:
    """Persist the key index that just succeeded, so later runs start there."""
    try:
        _CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CURSOR_PATH.write_text(str(index))
    except Exception as e:  # cursor is an optimization, never fatal
        log.debug("could not persist key cursor: %s", e)


def rotation_order(n: int) -> list[int]:
    """Indices [0..n-1] rotated to start at the persisted cursor, with keys already
    known-exhausted in this process moved out of the way.

    If every key is marked exhausted we still return the full order: the daily
    reset may have landed since, and failing loudly beats refusing to try.
    """
    if n <= 0:
        return []
    start = _read_cursor() % n
    order = [(start + k) % n for k in range(n)]
    live = [i for i in order if i not in _exhausted]
    return live or order
