"""Timing jitter formulas. All values are milliseconds."""
from __future__ import annotations

from typing import Iterable

from .model import InputEvent

SPAM_HOLD_BASE_MS = 40
LOOP_GAP_BASE_MS = 200


def jitter_for(event_type: str, random_ms: int, rng) -> float:
    """Jitter before an event: U(0, R) for *_down, U(0, R/3) for *_up."""
    r = max(0, random_ms)
    if event_type.endswith("_up"):
        return rng.uniform(0, r / 3)
    return rng.uniform(0, r)


def schedule(events: Iterable[InputEvent], random_ms: int, rng) -> list[tuple[float, InputEvent]]:
    """Return (sleep_ms_before_event, event) pairs preserving recorded gaps plus jitter."""
    out: list[tuple[float, InputEvent]] = []
    prev_t = None
    for ev in events:
        base = 0 if prev_t is None else max(0, ev.t - prev_t)
        out.append((base + jitter_for(ev.type, random_ms, rng), ev))
        prev_t = ev.t
    return out


def spam_hold_ms(random_ms: int, rng) -> float:
    return SPAM_HOLD_BASE_MS + rng.uniform(0, max(0, random_ms) / 3)


def spam_gap_ms(interval_ms: int, random_ms: int, rng) -> float:
    return interval_ms + rng.uniform(0, max(0, random_ms))


def loop_gap_ms(random_ms: int, rng) -> float:
    return LOOP_GAP_BASE_MS + rng.uniform(0, max(0, random_ms))
