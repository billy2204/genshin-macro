from genshin_macro.recorder import Recorder


class FakeClock:
    def __init__(self, t=0.0):
        self.t = t

    def __call__(self):
        return self.t


class Foreground:
    def __init__(self):
        self.app = False

    def __call__(self):
        return self.app


def _make():
    clock, fg = FakeClock(), Foreground()
    return Recorder(clock, fg), clock, fg


def test_basic_sequence_relative_times():
    rec, clock, _ = _make()
    rec.start()
    clock.t = 1.000
    rec.feed("key_down", 30, False)
    clock.t = 1.250
    rec.feed("key_up", 30, False)
    events = rec.stop()
    assert [(e.t, e.type, e.code) for e in events] == [(0, "key_down", 30), (250, "key_up", 30)]
    assert rec.recording is False


def test_ignores_events_while_app_foreground():
    rec, clock, fg = _make()
    rec.start()
    fg.app = True
    rec.feed("key_down", 30, False)
    rec.feed("key_up", 30, False)
    fg.app = False
    clock.t = 2.0
    rec.feed("key_down", 31, False)
    clock.t = 2.1
    rec.feed("key_up", 31, False)
    events = rec.stop()
    assert [e.code for e in events] == [31, 31]
    assert events[0].t == 0


def test_collapses_auto_repeat():
    rec, clock, _ = _make()
    rec.start()
    for i in range(5):
        clock.t = 1.0 + i * 0.03
        rec.feed("key_down", 30, False)
    clock.t = 2.0
    rec.feed("key_up", 30, False)
    events = rec.stop()
    assert [e.type for e in events] == ["key_down", "key_up"]
    assert events[1].t == 1000


def test_drops_orphan_up_and_trailing_down():
    rec, clock, _ = _make()
    rec.start()
    rec.feed("key_up", 48, False)  # orphan up (B)
    clock.t = 0.5
    rec.feed("key_down", 30, False)
    clock.t = 0.6
    rec.feed("key_up", 30, False)
    clock.t = 0.7
    rec.feed("key_down", 46, False)  # C never released
    events = rec.stop()
    assert [(e.type, e.code) for e in events] == [("key_down", 30), ("key_up", 30)]


def test_mouse_buttons_recorded():
    rec, clock, _ = _make()
    rec.start()
    rec.feed("mouse_down", "left", False)
    clock.t = 0.05
    rec.feed("mouse_up", "left", False)
    clock.t = 0.10
    rec.feed("mouse_down", "right", False)
    clock.t = 0.20
    rec.feed("mouse_up", "right", False)
    events = rec.stop()
    assert [(e.t, e.type, e.code) for e in events] == [
        (0, "mouse_down", "left"),
        (50, "mouse_up", "left"),
        (100, "mouse_down", "right"),
        (200, "mouse_up", "right"),
    ]


def test_feed_ignored_when_not_recording():
    rec, _, _ = _make()
    rec.feed("key_down", 30, False)
    rec.feed("key_up", 30, False)
    assert rec.event_count == 0
    assert rec.stop() == []


def test_extended_flag_distinguishes_keys():
    rec, clock, _ = _make()
    rec.start()
    rec.feed("key_down", 29, False)  # left ctrl
    clock.t = 0.1
    rec.feed("key_down", 29, True)  # right ctrl, distinct key
    clock.t = 0.2
    rec.feed("key_up", 29, False)
    clock.t = 0.3
    rec.feed("key_up", 29, True)
    events = rec.stop()
    assert len(events) == 4
    assert events[1].ext is True


def test_ignores_events_once_foreground_window_changes():
    """Alt+Tab out of the game: hook sees Tab-up / Alt-up while the task switcher is
    foreground. Those must be ignored so Alt/Tab become trailing downs and get dropped."""
    clock, fg = FakeClock(), Foreground()
    hwnd = {"v": 100}  # 100 = game
    rec = Recorder(clock, fg, foreground_hwnd=lambda: hwnd["v"])
    rec.start()
    clock.t = 1.0
    rec.feed("key_down", 30, False)
    clock.t = 1.1
    rec.feed("key_up", 30, False)
    clock.t = 2.0
    rec.feed("key_down", 56, False)  # Alt
    clock.t = 2.05
    rec.feed("key_down", 15, False)  # Tab
    hwnd["v"] = 200  # task switcher now foreground
    clock.t = 2.2
    rec.feed("key_up", 15, False)
    clock.t = 2.3
    rec.feed("key_up", 56, False)
    clock.t = 3.0
    rec.feed("key_down", 31, False)  # typing in another window
    events = rec.stop()
    assert [(e.type, e.code) for e in events] == [("key_down", 30), ("key_up", 30)]
