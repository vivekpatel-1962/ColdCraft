"""Per-call LLM telemetry.

The `runs.provider_log` column has existed since increment 1 but nothing wrote to
it. This is that writer: every complete_json() call appends a record (stage,
provider, model, which key, duration, retries, outcome), which the eval harness
and the API can drain to show exactly what each stage cost and where it failed.
"""
from dataclasses import asdict, dataclass, field


@dataclass
class LLMCall:
    stage: str
    provider: str
    model: str
    key_index: int | None = None
    duration_s: float = 0.0
    ok: bool = True
    error: str | None = None
    quota_rotations: int = 0   # times we rotated keys on a 429
    transient_retries: int = 0  # times we retried a 5xx
    input_chars: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


_calls: list[LLMCall] = []


def record(call: LLMCall) -> None:
    _calls.append(call)


def snapshot() -> list[LLMCall]:
    return list(_calls)


def drain() -> list[LLMCall]:
    """Return everything recorded so far and clear the buffer."""
    out = list(_calls)
    _calls.clear()
    return out


def reset() -> None:
    _calls.clear()
