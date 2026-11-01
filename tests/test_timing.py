import random

from genshin_macro.model import InputEvent
from genshin_macro.timing import (
    jitter_for,
    loop_gap_ms,
    schedule,
    spam_gap_ms,
    spam_hold_ms,
)


class MaxRng:
    """Stub rng whose uniform(a, b) always returns b."""

    def uniform(self, a, b):
        return b


def _events():
    return [
        InputEvent(t=0, type="key_down", code=18),
        InputEvent(t=100, type="key_up", code=18),
        InputEvent(t=250, type="mouse_down", code="left"),
    ]


def test_schedule_zero_random_preserves_gaps():
    sched = schedule(_events(), 0, random.Random(0))
    assert [s for s, _ in sched] == [0, 100, 150]
    assert [e.type for _, e in sched] == ["key_down", "key_up", "mouse_down"]


def test_down_jitter_within_R_and_up_within_R_over_3():
    rng = random.Random(1)
    downs = [jitter_for("key_down", 90, rng) for _ in range(500)]
    ups = [jitter_for("mouse_up", 90, rng) for _ in range(500)]
    assert all(0 <= j <= 90 for j in downs)
    assert all(0 <= j <= 30 for j in ups)
    assert max(downs) > 60  # actually spreads over the range
    assert max(ups) > 20


def test_schedule_adds_jitter_per_event_type():
    sched = schedule(_events(), 90, MaxRng())
    assert [s for s, _ in sched] == [90, 130, 240]


def test_spam_and_loop_formulas():
    rng = MaxRng()
    assert spam_hold_ms(90, rng) == 70
    assert spam_gap_ms(80, 90, rng) == 170
    assert loop_gap_ms(90, rng) == 290
