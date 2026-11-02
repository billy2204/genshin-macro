import queue

import pytest

from genshin_macro.controller import Controller
from genshin_macro.hotkeys import HotkeyManager
from genshin_macro.model import Config, KeyRef
from genshin_macro.recorder import Recorder


class FakePlayer:
    def __init__(self):
        self.toggled = []
        self.stopped = 0
        self.running_id = None

    def toggle(self, macro):
        self.toggled.append(macro.id)
        self.running_id = None if self.running_id == macro.id else macro.id

    def stop(self):
        self.stopped += 1
        self.running_id = None


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def _make(config=None):
    saved = []
    clock = Clock()
    fg = {"app": False}
    is_fg = lambda: fg["app"]
    player = FakePlayer()
    events = queue.Queue()
    ctl = Controller(
        config or Config(),
        saved.append,
        Recorder(clock, is_fg),
        HotkeyManager(is_fg),
        player,
        events,
        label_for=lambda s, e: f"K{s}",
    )
    return ctl, player, saved, clock, fg, events


F8 = KeyRef(66, False, "F8")
F9 = KeyRef(67, False, "F9")


def test_add_assigns_sequential_names_and_saves():
    ctl, _, saved, *_ = _make()
    a = ctl.add_spam()
    b = ctl.add_recorded()
    assert (a.name, b.name) == ("Macro 1", "Macro 2")
    assert [m.id for m in ctl.macros] == [a.id, b.id]
    assert len(saved) == 2


def test_duplicate_hotkey_rejected():
    ctl, *_ = _make()
    a = ctl.add_spam()
    b = ctl.add_spam()
    ctl.update(a.id, hotkey=F8)
    with pytest.raises(ValueError):
        ctl.update(b.id, hotkey=F8)
    assert ctl.get(b.id).hotkey is None


def test_hotkey_toggles_player():
    ctl, player, *_ = _make()
    a = ctl.add_spam()
    ctl.update(a.id, hotkey=F8, key=KeyRef(33, False, "F"))
    ctl.on_key(66, False, True)
    ctl.on_key(66, False, False)
    assert player.toggled == [a.id]


def test_delete_unbinds_hotkey_and_stops_player():
    ctl, player, *_ = _make()
    a = ctl.add_spam()
    ctl.update(a.id, hotkey=F8)
    player.running_id = a.id
    ctl.delete(a.id)
    ctl.on_key(66, False, True)
    assert player.toggled == []
    assert player.stopped == 1
    assert ctl.macros == []


def test_hotkey_during_recording_stops_recording_not_player():
    ctl, player, saved, clock, fg, events = _make()
    r = ctl.add_recorded()
    ctl.update(r.id, hotkey=F9)
    ctl.start_recording(r.id)
    assert ctl.recording_id == r.id
    clock.t = 1.0
    ctl.on_key(18, False, True)
    clock.t = 1.2
    ctl.on_key(18, False, False)
    clock.t = 1.5
    ctl.on_mouse("left", True)
    clock.t = 1.6
    ctl.on_mouse("left", False)
    clock.t = 2.0
    ctl.on_key(67, False, True)  # F9 = this macro's hotkey → stop recording
    ctl.on_key(67, False, False)
    assert ctl.recording_id is None
    assert player.toggled == []
    stored = ctl.get(r.id).events
    assert [(e.t, e.type, e.code) for e in stored] == [
        (0, "key_down", 18),
        (200, "key_up", 18),
        (500, "mouse_down", "left"),
        (600, "mouse_up", "left"),
    ]
    assert saved  # persisted
    # F9 down was pressed-and-released after stop: not in the recording
    assert all(e.code != 67 for e in stored)


def test_start_recording_stops_running_player():
    ctl, player, *_ = _make()
    r = ctl.add_recorded()
    player.running_id = "other"
    ctl.start_recording(r.id)
    assert player.stopped == 1


def test_capture_takes_next_key_and_skips_hotkey():
    ctl, player, *_ = _make()
    a = ctl.add_spam()
    ctl.update(a.id, hotkey=F8)
    got = []
    ctl.begin_capture(got.append)
    ctl.on_key(66, False, True)
    ctl.on_key(66, False, False)
    assert got == [KeyRef(66, False, "K66")]
    assert player.toggled == []
    # capture is one-shot: next press acts as a hotkey again
    ctl.on_key(66, False, True)
    assert player.toggled == [a.id]


def test_save_called_on_update_and_random_ms():
    ctl, _, saved, *_ = _make()
    a = ctl.add_spam()
    n = len(saved)
    ctl.update(a.id, name="Skip", interval_ms=0)
    assert ctl.get(a.id).name == "Skip"
    assert ctl.get(a.id).interval_ms == 1
    ctl.set_random_ms(-3)
    assert ctl.random_ms == 0
    assert len(saved) == n + 2


def test_update_rejects_non_field_attributes():
    ctl, *_ = _make()
    a = ctl.add_spam()
    with pytest.raises(AttributeError):
        ctl.update(a.id, kind="recorded")
    assert a.kind == "spam"


def test_events_queue_receives_recording_state():
    ctl, _, _, _, _, events = _make()
    r = ctl.add_recorded()
    ctl.start_recording(r.id)
    ctl.stop_recording()
    items = []
    while not events.empty():
        items.append(events.get_nowait())
    assert ("recording", r.id) in items and ("recording", None) in items


F10 = KeyRef(68, False, "F10")


def test_record_hotkey_toggles_recording_of_selected_macro():
    ctl, player, saved, clock, fg, events = _make()
    r = ctl.add_recorded()
    ctl.set_record_hotkey(F10)
    ctl.selected_id = r.id
    ctl.on_key(68, False, True)
    ctl.on_key(68, False, False)
    assert ctl.recording_id == r.id
    clock.t = 1.0
    ctl.on_key(18, False, True)
    clock.t = 1.1
    ctl.on_key(18, False, False)
    clock.t = 2.0
    ctl.on_key(68, False, True)
    ctl.on_key(68, False, False)
    assert ctl.recording_id is None
    assert [(e.type, e.code) for e in ctl.get(r.id).events] == [("key_down", 18), ("key_up", 18)]
    assert player.toggled == []


def test_record_hotkey_ignored_when_selected_is_spam_or_none():
    ctl, *_ = _make()
    s = ctl.add_spam()
    ctl.set_record_hotkey(F10)
    ctl.on_key(68, False, True)
    ctl.on_key(68, False, False)
    assert ctl.recording_id is None
    ctl.selected_id = s.id
    ctl.on_key(68, False, True)
    assert ctl.recording_id is None


def test_record_hotkey_conflicts_with_macro_hotkey_both_directions():
    ctl, *_ = _make()
    a = ctl.add_spam()
    ctl.update(a.id, hotkey=F8)
    with pytest.raises(ValueError):
        ctl.set_record_hotkey(F8)
    ctl.set_record_hotkey(F10)
    with pytest.raises(ValueError):
        ctl.update(a.id, hotkey=F10)
    assert ctl.record_hotkey == F10


def test_set_overlay_persists():
    ctl, _, saved, *_ = _make()
    ctl.set_overlay(False)
    assert ctl.overlay is False and saved


def test_describe_event_uses_labels():
    ctl, *_ = _make()
    from genshin_macro.model import InputEvent

    assert ctl.describe_event(InputEvent(0, "key_down", 30)) == (0, "Nhấn", "K30")
    assert ctl.describe_event(InputEvent(120, "key_up", 30)) == (120, "Nhả", "K30")
    assert ctl.describe_event(InputEvent(200, "mouse_down", "left")) == (200, "Nhấn", "Chuột trái")
    assert ctl.describe_event(InputEvent(250, "mouse_up", "right")) == (250, "Nhả", "Chuột phải")
