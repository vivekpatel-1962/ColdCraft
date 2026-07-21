"""Provider adapter: every pipeline stage calls complete_json() and gets back a
validated Pydantic object.

Routing policy:
- Primary provider is Gemini (free tier). Flash for judgment-shaped stages,
  Flash-Lite for extraction-shaped ones. resume_analyzer runs on Flash despite
  being extraction: it's a one-time call whose quality compounds forever.
- On quota exhaustion (429), extraction stages may fall back to the optional
  OpenAI-compatible provider from .env. Judgment stages (matcher/planner/writer)
  raise QuotaExhausted instead — a silently weaker-model email to a recruiter is
  worse than a delayed one; Gemini's daily quota resets at midnight Pacific.
- Every response is validated against the stage's schema; one automatic retry
  with the validation error injected before giving up.
"""
import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app import config

log = logging.getLogger("coldmail.llm")

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


class QuotaExhausted(LLMError):
    """Raised when the primary provider is out of quota and the stage's policy
    forbids falling back. Caller should queue and retry after quota reset."""


def _gemini_model_for(stage: str) -> str:
    if stage in config.JUDGMENT_STAGES or stage == "resume_analyzer":
        return config.GEMINI_MODEL_JUDGMENT
    return config.GEMINI_MODEL_EXTRACTION


def _call_gemini_with_key(
    api_key: str, stage: str, system: str, user: str, schema: type[T]
) -> T:
    """One key's attempt at a stage, with the schema-validation retry. Quota (429)
    errors propagate up so the key rotator can move to the next key."""
    from google import genai
    from google.genai import types as gtypes

    client = genai.Client(api_key=api_key)
    model = _gemini_model_for(stage)

    def once(extra_user: str = "") -> T:
        resp = client.models.generate_content(
            model=model,
            contents=user + extra_user,
            config=gtypes.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        parsed = resp.parsed
        if isinstance(parsed, schema):
            return parsed
        # Fall back to manual parse if the SDK returned raw text/dict
        return schema.model_validate_json(resp.text)

    try:
        return once()
    except ValidationError as e:
        log.warning("stage=%s validation failed, retrying once: %s", stage, e)
        return once(
            "\n\nYour previous response failed schema validation with this error, "
            f"fix it and return only valid JSON:\n{e}"
        )


def _call_gemini(stage: str, system: str, user: str, schema: type[T]) -> T:
    """Try the configured Gemini keys in rotation. Uses the last known-good key
    first; on a per-key quota (429) it rotates to the next. Raises the quota error
    only when EVERY key is exhausted, so complete_json() then applies stage policy."""
    from . import keyring

    keys = config.GEMINI_API_KEYS
    if not keys:
        raise LLMError(
            "No Gemini key configured - copy .env.example to .env and set "
            "GEMINI_API_KEYS (comma-separated) or GEMINI_API_KEY"
        )

    order = keyring.rotation_order(len(keys))
    last_quota_error: Exception | None = None
    for i in order:
        try:
            result = _call_gemini_with_key(keys[i], stage, system, user, schema)
            keyring.remember(i)
            log.info("stage=%s provider=gemini key=#%d model=%s ok", stage, i, _gemini_model_for(stage))
            return result
        except Exception as e:
            if not _is_quota_error(e):
                raise
            last_quota_error = e
            log.warning("stage=%s gemini key #%d quota-exhausted, rotating (%d keys total)",
                        stage, i, len(keys))
            continue

    # Every key is out of quota — re-raise so complete_json applies the stage policy.
    assert last_quota_error is not None
    raise last_quota_error


def _call_fallback(stage: str, system: str, user: str, schema: type[T]) -> T:
    """OpenAI-compatible fallback (e.g. Groq). Schema is enforced by prompt +
    validation since json_schema support varies across free providers."""
    if not (config.FALLBACK_API_KEY and config.FALLBACK_BASE_URL and config.FALLBACK_MODEL):
        raise LLMError("No fallback provider configured (FALLBACK_* in .env)")

    schema_json = json.dumps(schema.model_json_schema(), indent=None)

    def once(extra: str = "") -> T:
        r = httpx.post(
            f"{config.FALLBACK_BASE_URL.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {config.FALLBACK_API_KEY}"},
            json={
                "model": config.FALLBACK_MODEL,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system
                        + "\n\nRespond with ONLY a JSON object matching this JSON Schema:\n"
                        + schema_json},
                    {"role": "user", "content": user + extra},
                ],
            },
            timeout=120,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return schema.model_validate_json(text)

    try:
        return once()
    except ValidationError as e:
        log.warning("stage=%s fallback validation failed, retrying once: %s", stage, e)
        return once(f"\n\nPrevious response failed schema validation: {e}\nReturn only valid JSON.")


def _is_quota_error(e: Exception) -> bool:
    from google.genai import errors as gerrors

    return isinstance(e, gerrors.APIError) and getattr(e, "code", None) == 429


def complete_json(stage: str, system: str, user: str, schema: type[T]) -> T:
    """Run one pipeline stage. Returns a validated instance of `schema`.

    Raises QuotaExhausted when quota is gone and the stage must not degrade.
    """
    try:
        return _call_gemini(stage, system, user, schema)  # logs its own success (with key index)
    except Exception as e:
        if not _is_quota_error(e):
            raise
        if stage in config.JUDGMENT_STAGES:
            raise QuotaExhausted(
                f"Gemini quota exhausted on judgment stage '{stage}'. "
                "Waiting for the daily reset (midnight Pacific) beats a weaker-model email."
            ) from e
        log.warning("stage=%s gemini quota exhausted, using fallback provider", stage)
        result = _call_fallback(stage, system, user, schema)
        log.info("stage=%s provider=fallback model=%s ok", stage, config.FALLBACK_MODEL)
        return result
