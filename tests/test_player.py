import random
import threading

from genshin_macro.model import InputEvent, KeyRef, RecordedMacro, SpamMacro
from genshin_macro.player import Player, run_macro


class FakeOutput:
    def __init__(self):
        self.calls = []

    def key_down(self, scan, ext):
        self.calls.append(("key_down", scan, ext))

    def key_up(self, scan, ext):
        self.calls.append(("key_up", scan, ext))

    def mouse_down(self, button):
        self.calls.append(("mouse_down", button))

    def mouse_up(self, button):
        self.calls.append(("mouse_up", button))


class FakeSleep:
    """Records sleeps; sets `stop` after `stop_after` calls."""

    def __init__(self, stop, stop_after=None):
        self.stop = stop
        self.stop_after = stop_after
        self.slept = []

    def __call__(self, ms):
        self.slept.append(ms)
        if self.stop_after is not None and len(self.slept) >= self.stop_after:
            self.stop.set()


def _recorded(loop=False):
    return RecordedMacro(
        id="r1",
        name="combo",
        loop=loop,
        events=[
            InputEvent(0, "key_down", 18),
            InputEvent(100, "key_up", 18),
            InputEvent(200, "mouse_down", "left"),
            InputEvent(250, "mouse_up", "left"),
        ],
    )


def _run(macro, stop=None, stop_after=None, still_fg=lambda: True, random_ms=0):
    stop = stop or threading.Event()
    out = FakeOutput()
    sleep = FakeSleep(stop, stop_after)
    run_macro(macro, out, stop, random_ms, random.Random(0), sleep, still_fg)
    return out, sleep


def test_recorded_once_emits_all_events_in_order():
    out, sleep = _run(_recorded())
    assert out.calls == [
        ("key_down", 18, False),
        ("key_up", 18, False),
        ("mouse_down", "left"),
        ("mouse_up", "left"),
    ]
    assert sleep.slept == [0, 100, 100, 50]


def test_stop_releases_held_keys():
    # stop is set during the sleep after key_down (2nd sleep call)
    out, _ = _run(_recorded(), stop_after=2)
    assert out.calls == [("key_down", 18, False), ("key_up", 18, False)]


def test_foreground_change_stops_and_releases():
    calls = {"n": 0}

    def still_fg():
        calls["n"] += 1
        return calls["n"] <= 2  # checked before+after each sleep: lost before the 2nd event

    out, sleep = _run(_recorded(), still_fg=still_fg)
    assert out.calls == [("key_down", 18, False), ("key_up", 18, False)]
    assert sleep.slept == [0]


def test_spam_emits_down_up_pairs_until_stop():
    macro = SpamMacro(id="s1", name="spam", key=KeyRef(33, False, "F"), interval_ms=80)
    out, sleep = _run(macro, stop_after=4, random_ms=0)
    assert out.calls == [
        ("key_down", 33, False),
        ("key_up", 33, False),
        ("key_down", 33, False),
        ("key_up", 33, False),
    ]
    assert sleep.slept == [40, 80, 40, 80]


def test_spam_without_key_does_nothing():
    macro = SpamMacro(id="s1", name="spam", key=None)
    out, sleep = _run(macro)
    assert out.calls == [] and sleep.slept == []


def test_loop_repeats():
    # 4 sleeps per pass + 1 loop gap; stop during the second pass' last sleep
    out, sleep = _run(_recorded(loop=True), stop_after=9)
    downs = [c for c in out.calls if c[0] == "key_down"]
    assert len(downs) == 2
    assert sleep.slept[4] == 200  # loop gap with R=0
    ups = [c for c in out.calls if c[0].endswith("_up")]
    assert len(ups) == len([c for c in out.calls if c[0].endswith("_down")])


def test_player_toggle_same_id_stops_and_other_id_replaces():
    out = FakeOutput()
    states = []
    started = threading.Event()

    def sleep(ms):
        started.set()
        threading.Event().wait(0.005)

    p = Player(out, lambda: 0, lambda: 1, states.append, sleep=sleep)
    spam = SpamMacro(id="s1", name="spam", key=KeyRef(33, False, "F"))
    p.toggle(spam)
    assert started.wait(1.0)
    assert p.running_id == "s1"
    other = _recorded(loop=True)
    p.toggle(other)
    assert p.running_id == "r1"
    p.toggle(other)
    p.stop()
    assert p.running_id is None
    assert p.join(1.0)  # stop() no longer blocks; wait for the thread's finally
    assert states[0] == "s1" and states[-1] is None
    downs = [c for c in out.calls if c[0].endswith("_down")]
    ups = [c for c in out.calls if c[0].endswith("_up")]
    assert len(downs) == len(ups)


def test_foreground_lost_during_sleep_emits_nothing_more():
    # still_fg flips to False while sleeping before the 3rd event (mouse_down)
    state = {"n": 0}

    def still_fg():
        return state["n"] < 3

    stop = threading.Event()
    out = FakeOutput()

    def sleep(ms):
        state["n"] += 1  # 1st sleep -> n=1, 2nd -> 2, 3rd (before mouse_down) -> 3 => focus lost

    run_macro(_recorded(), out, stop, 0, random.Random(0), sleep, still_fg)
    assert out.calls == [("key_down", 18, False), ("key_up", 18, False)]


def test_stop_interrupts_long_sleep_and_releases_before_exit():
    import time

    out = FakeOutput()
    p = Player(out, lambda: 0, lambda: 1, lambda s: None)  # real (interruptible) sleep
    spam = SpamMacro(id="s1", name="spam", key=KeyRef(33, False, "F"), interval_ms=5000)
    p.start(spam)
    deadline = time.monotonic() + 1.0
    while not out.calls and time.monotonic() < deadline:
        time.sleep(0.005)
    assert out.calls[0] == ("key_down", 33, False)
    t0 = time.monotonic()
    p.stop()  # must return immediately, not block for the 40 ms hold / 5 s gap
    assert time.monotonic() - t0 < 0.2
    assert p.join(1.0) is True  # thread finished (sleep was interrupted)
    assert out.calls[-1] == ("key_up", 33, False)
