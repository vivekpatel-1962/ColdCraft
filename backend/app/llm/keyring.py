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


def _read_cursor() -> int:
    try:
        return max(0, int(_CURSOR_PATH.read_text().strip()))
    except Exception:
        return 0


def remember(index: int) -> None:
    """Persist the key index that just succeeded, so later runs start there."""
    try:
        _CURSOR_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CURSOR_PATH.write_text(str(index))
    except Exception as e:  # cursor is an optimization, never fatal
        log.debug("could not persist key cursor: %s", e)


def rotation_order(n: int) -> list[int]:
    """Indices [0..n-1] rotated to start at the persisted cursor."""
    if n <= 0:
        return []
    start = _read_cursor() % n
    return [(start + k) % n for k in range(n)]
