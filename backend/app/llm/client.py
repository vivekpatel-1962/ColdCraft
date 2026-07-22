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
import time
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app import config
from app.llm import telemetry

log = logging.getLogger("coldmail.llm")

T = TypeVar("T", bound=BaseModel)

# Upstream hiccups (model overloaded, gateway blips) — distinct from quota. These
# are temporary by definition, so retry with backoff rather than rotating keys:
# a 503 is model-side capacity, identical across every key.
TRANSIENT_CODES = {500, 502, 503, 504}
TRANSIENT_ATTEMPTS = 3
TRANSIENT_BACKOFF_SECONDS = 2.0


class LLMError(Exception):
    pass


class QuotaExhausted(LLMError):
    """Raised when the primary provider is out of quota and the stage's policy
    forbids falling back. Caller should queue and retry after quota reset."""


class ProviderUnavailable(LLMError):
    """The provider returned a transient 5xx and kept doing so across retries."""


def _gemini_model_for(stage: str) -> str:
    if stage in config.JUDGMENT_STAGES or stage in config.STRONG_EXTRACTION_STAGES:
        return config.GEMINI_MODEL_JUDGMENT
    return config.GEMINI_MODEL_EXTRACTION


def _call_gemini_with_key(
    api_key: str, stage: str, system: str, user: str, schema: type[T],
    images: list[tuple[bytes, str]] | None = None,
) -> T:
    """One key's attempt at a stage, with the schema-validation retry. Quota (429)
    errors propagate up so the key rotator can move to the next key.

    `images` is [(bytes, mime_type)] for multimodal stages (e.g. reading a hiring
    poster); text-only stages pass None and behave exactly as before.
    """
    from google import genai
    from google.genai import types as gtypes

    client = genai.Client(api_key=api_key)
    model = _gemini_model_for(stage)

    def once(extra_user: str = "") -> T:
        contents: list = [
            gtypes.Part.from_bytes(data=data, mime_type=mime) for data, mime in (images or [])
        ]
        contents.append(user + extra_user)
        resp = client.models.generate_content(
            model=model,
            contents=contents,
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


def _call_gemini(stage: str, system: str, user: str, schema: type[T],
                 images: list[tuple[bytes, str]] | None = None) -> T:
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
    model = _gemini_model_for(stage)
    last_quota_error: Exception | None = None
    counter: dict = {}
    rotations = 0
    started = time.monotonic()

    for i in order:
        try:
            result = _with_transient_retry(
                lambda: _call_gemini_with_key(keys[i], stage, system, user, schema, images),
                stage, counter,
            )
            keyring.remember(i)
            telemetry.record(telemetry.LLMCall(
                stage=stage, provider="gemini", model=model, key_index=i,
                duration_s=round(time.monotonic() - started, 2), ok=True,
                quota_rotations=rotations, transient_retries=counter.get("transient", 0),
                input_chars=len(system) + len(user),
            ))
            log.info("stage=%s provider=gemini key=#%d model=%s ok (%.1fs)",
                     stage, i, model, time.monotonic() - started)
            return result
        except Exception as e:
            if not _is_quota_error(e):
                telemetry.record(telemetry.LLMCall(
                    stage=stage, provider="gemini", model=model, key_index=i,
                    duration_s=round(time.monotonic() - started, 2), ok=False, error=str(e)[:300],
                    quota_rotations=rotations, transient_retries=counter.get("transient", 0),
                    input_chars=len(system) + len(user),
                ))
                raise
            last_quota_error = e
            rotations += 1
            keyring.mark_exhausted(i)  # don't re-probe this key for the rest of the run
            log.warning("stage=%s gemini key #%d quota-exhausted, rotating (%d/%d keys down)",
                        stage, i, keyring.exhausted_count(), len(keys))
            continue

    # Every key is out of quota — re-raise so complete_json applies the stage policy.
    assert last_quota_error is not None
    telemetry.record(telemetry.LLMCall(
        stage=stage, provider="gemini", model=model, key_index=None,
        duration_s=round(time.monotonic() - started, 2), ok=False,
        error="all keys quota-exhausted", quota_rotations=rotations,
        transient_retries=counter.get("transient", 0), input_chars=len(system) + len(user),
    ))
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


def _is_transient_error(e: Exception) -> bool:
    from google.genai import errors as gerrors

    return isinstance(e, gerrors.APIError) and getattr(e, "code", None) in TRANSIENT_CODES


def _with_transient_retry(fn, stage: str, counter: dict | None = None):
    """Retry a provider call through temporary 5xx blips with exponential backoff.
    Quota errors pass straight through — those are the key rotator's business."""
    delay = TRANSIENT_BACKOFF_SECONDS
    for attempt in range(1, TRANSIENT_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as e:
            if not _is_transient_error(e):
                raise
            if counter is not None:
                counter["transient"] = counter.get("transient", 0) + 1
            if attempt == TRANSIENT_ATTEMPTS:
                raise ProviderUnavailable(
                    f"Provider returned {getattr(e, 'code', '5xx')} for stage '{stage}' "
                    f"after {TRANSIENT_ATTEMPTS} attempts — model is overloaded, try again shortly."
                ) from e
            log.warning("stage=%s transient %s, retry %d/%d in %.0fs",
                        stage, getattr(e, "code", "5xx"), attempt, TRANSIENT_ATTEMPTS, delay)
            time.sleep(delay)
            delay *= 2


def complete_json(stage: str, system: str, user: str, schema: type[T],
                  images: list[tuple[bytes, str]] | None = None) -> T:
    """Run one pipeline stage. Returns a validated instance of `schema`.

    `images` enables multimodal stages ([(bytes, mime_type)]).
    Raises QuotaExhausted when quota is gone and the stage must not degrade.
    """
    try:
        return _call_gemini(stage, system, user, schema, images)  # logs its own success
    except Exception as e:
        if not _is_quota_error(e):
            raise
        if stage in config.JUDGMENT_STAGES:
            raise QuotaExhausted(
                f"Gemini quota exhausted on judgment stage '{stage}'. "
                "Waiting for the daily reset (midnight Pacific) beats a weaker-model email."
            ) from e
        if images:
            # The OpenAI-compatible fallback path is text-only; degrading a vision
            # extraction to a text model would silently drop the whole input.
            raise QuotaExhausted(
                f"Gemini quota exhausted on multimodal stage '{stage}' and the fallback "
                "provider is text-only. Retry after the daily reset."
            ) from e
        log.warning("stage=%s gemini quota exhausted, using fallback provider", stage)
        result = _call_fallback(stage, system, user, schema)
        log.info("stage=%s provider=fallback model=%s ok", stage, config.FALLBACK_MODEL)
        return result
