"""Controller: ignore keys, event editing, save-as / load-from."""
import queue
from pathlib import Path

import pytest

from genshin_macro.controller import Controller
from genshin_macro.hotkeys import HotkeyManager
from genshin_macro.model import Config, InputEvent, KeyRef, RecordedMacro
from genshin_macro.recorder import Recorder


class FakePlayer:
    running_id = None

    def toggle(self, macro):
        pass

    def stop(self):
        pass


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def _make(tmp_path=None, config=None):
    saved = []
    clock = Clock()
    paths = []
    path = (tmp_path / "macros.json") if tmp_path else None
    ctl = Controller(
        config or Config(),
        saved.append,
        Recorder(clock, lambda: False),
        HotkeyManager(lambda: False),
        FakePlayer(),
        queue.Queue(),
        label_for=lambda s, e: f"K{s}",
        path=path,
        on_path_change=paths.append,
    )
    return ctl, saved, clock, paths


W, A, S, D = 17, 30, 31, 32


def test_new_recorded_macro_ignores_wasd_by_default():
    ctl, *_ = _make()
    r = ctl.add_recorded()
    assert [k.scan for k in r.ignore_keys] == [W, A, S, D]
    assert r.ignore_keys[0].label == "K17"


def test_ignored_keys_are_not_recorded_but_hotkeys_still_work():
    ctl, saved, clock, _ = _make()
    r = ctl.add_recorded()
    ctl.update(r.id, hotkey=KeyRef(67, False, "F9"))
    ctl.start_recording(r.id)
    clock.t = 1.0
    ctl.on_key(W, False, True)
    clock.t = 1.1
    ctl.on_key(18, False, True)  # E
    clock.t = 1.2
    ctl.on_key(18, False, False)
    clock.t = 1.3
    ctl.on_key(W, False, False)
    clock.t = 2.0
    ctl.on_key(67, False, True)  # own hotkey stops
    ctl.on_key(67, False, False)
    assert [(e.type, e.code) for e in ctl.get(r.id).events] == [("key_down", 18), ("key_up", 18)]


def test_add_and_remove_ignore_key():
    ctl, saved, *_ = _make()
    r = ctl.add_recorded()
    n = len(saved)
    ctl.add_ignore_key(r.id, KeyRef(42, False, "Shift"))
    ctl.add_ignore_key(r.id, KeyRef(42, False, "Shift"))  # duplicate ignored
    assert [k.scan for k in ctl.get(r.id).ignore_keys] == [W, A, S, D, 42]
    ctl.remove_ignore_key(r.id, 0)
    assert [k.scan for k in ctl.get(r.id).ignore_keys] == [A, S, D, 42]
    assert len(saved) == n + 2


def _with_events(ctl):
    r = ctl.add_recorded()
    ctl.update(
        r.id,
        events=[
            InputEvent(0, "key_down", 18),
            InputEvent(100, "key_up", 18),
            InputEvent(300, "mouse_down", "left"),
            InputEvent(350, "mouse_up", "left"),
        ],
    )
    return r


def test_update_event_time_resorts():
    ctl, *_ = _make()
    r = _with_events(ctl)
    ctl.update_event(r.id, 1, t=400)  # key_up moved after the mouse events
    assert [(e.t, e.type) for e in ctl.get(r.id).events] == [
        (0, "key_down"),
        (300, "mouse_down"),
        (350, "mouse_up"),
        (400, "key_up"),
    ]


def test_update_event_key_and_action():
    ctl, *_ = _make()
    r = _with_events(ctl)
    ctl.update_event(r.id, 2, type="key_down", code=16, ext=False)  # mouse_down -> Q down
    ev = ctl.get(r.id).events[2]
    assert (ev.type, ev.code, ev.ext) == ("key_down", 16, False)
    ctl.update_event(r.id, 3, type="mouse_up", code="right")
    assert ctl.get(r.id).events[3].code == "right"


def test_update_event_rejects_bad_values():
    ctl, *_ = _make()
    r = _with_events(ctl)
    with pytest.raises(ValueError):
        ctl.update_event(r.id, 0, t=-5)
    with pytest.raises(ValueError):
        ctl.update_event(r.id, 0, type="jump")
    with pytest.raises(IndexError):
        ctl.update_event(r.id, 9, t=1)


def test_delete_event():
    ctl, saved, *_ = _make()
    r = _with_events(ctl)
    ctl.delete_event(r.id, 0)
    assert [e.type for e in ctl.get(r.id).events] == ["key_up", "mouse_down", "mouse_up"]


def test_save_as_changes_path_and_writes_file(tmp_path):
    ctl, saved, _, paths = _make(tmp_path)
    ctl.add_spam()
    target = tmp_path / "sub" / "combo.json"
    ctl.save_as(target)
    assert ctl.path == target
    assert target.exists()
    assert paths == [target]
    assert Config.load(target).macros[0].name == "Macro 1"


def test_load_from_replaces_config_and_rebinds(tmp_path):
    ctl, saved, _, paths = _make(tmp_path)
    ctl.add_spam()
    other = tmp_path / "other.json"
    Config(random_ms=33, macros=[RecordedMacro(id="z", name="Zed", hotkey=KeyRef(66, False, "F8"))]).save(other)
    ctl.load_from(other)
    assert ctl.path == other
    assert [m.id for m in ctl.macros] == ["z"]
    assert ctl.random_ms == 33
    assert ctl._hotkeys.is_bound(66, False)
    assert paths[-1] == other


def test_load_from_missing_file_raises(tmp_path):
    ctl, *_ = _make(tmp_path)
    with pytest.raises(ValueError):
        ctl.load_from(tmp_path / "nope.json")


def test_set_event_delay_shifts_following_events():
    ctl, *_ = _make()
    r = _with_events(ctl)  # t = 0, 100, 300, 350 -> delays 0, 100, 200, 50
    ctl.set_event_delay(r.id, 2, 500)  # mouse_down now 500 ms after key_up
    assert [e.t for e in ctl.get(r.id).events] == [0, 100, 600, 650]
    ctl.set_event_delay(r.id, 0, 250)  # delay before the first event shifts everything
    assert [e.t for e in ctl.get(r.id).events] == [250, 350, 850, 900]


def test_set_event_delay_rejects_negative():
    ctl, *_ = _make()
    r = _with_events(ctl)
    with pytest.raises(ValueError):
        ctl.set_event_delay(r.id, 1, -1)


def test_event_delays_helper():
    ctl, *_ = _make()
    r = _with_events(ctl)
    assert ctl.event_delays(r.id) == [0, 100, 200, 50]


RAZER_XML = """<Macro><Name>Skirk</Name><MacroEvents>
<MacroEvent><Type>1</Type><KeyEvent><Makecode>18</Makecode><State>0</State></KeyEvent></MacroEvent>
<MacroEvent><Type>0</Type><Number>0.1</Number></MacroEvent>
<MacroEvent><Type>1</Type><KeyEvent><Makecode>18</Makecode><State>1</State></KeyEvent></MacroEvent>
</MacroEvents></Macro>"""


def test_import_razer_creates_recorded_macro(tmp_path):
    ctl, saved, *_ = _make(tmp_path)
    f = tmp_path / "Skirk.xml"
    f.write_text(RAZER_XML, encoding="utf-8")
    m = ctl.import_razer(f)
    assert m.name == "Skirk" and m.kind == "recorded"
    assert [(e.t, e.type, e.code) for e in m.events] == [(0, "key_down", 18), (100, "key_up", 18)]
    assert [k.scan for k in m.ignore_keys] == [W, A, S, D]
    assert ctl.get(m.id) is m and saved


def test_import_razer_bad_file_raises(tmp_path):
    ctl, *_ = _make(tmp_path)
    f = tmp_path / "bad.xml"
    f.write_text("<Other/>", encoding="utf-8")
    with pytest.raises(ValueError):
        ctl.import_razer(f)


class FakePoller:
    instances = []

    def __init__(self, *a, **k):
        self.running = False
        FakePoller.instances.append(self)

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


def test_recording_starts_and_stops_mouse_poller(monkeypatch):
    FakePoller.instances.clear()
    ctl, *_ = _make()
    ctl.poller_factory = lambda on_change: FakePoller()
    r = ctl.add_recorded()
    ctl.start_recording(r.id)
    assert FakePoller.instances and FakePoller.instances[-1].running
    ctl.stop_recording()
    assert not FakePoller.instances[-1].running


def test_polled_mouse_events_feed_recorder_and_dedupe_with_hook():
    ctl, saved, clock, _ = _make()
    r = ctl.add_recorded()
    ctl.start_recording(r.id)
    clock.t = 1.0
    ctl.on_mouse("right", True, source="poll")
    clock.t = 1.001
    ctl.on_mouse("right", True, source="hook")  # same press seen by the hook: ignored
    clock.t = 1.2
    ctl.on_mouse("right", False, source="hook")
    clock.t = 1.201
    ctl.on_mouse("right", False, source="poll")
    ctl.stop_recording()
    assert [(e.t, e.type, e.code) for e in ctl.get(r.id).events] == [(0, "mouse_down", "right"), (200, "mouse_up", "right")]


def test_debug_sink_receives_raw_events():
    ctl, *_ = _make()
    lines = []
    ctl.debug_sink = lines.append
    ctl.on_key(18, False, True)
    ctl.on_mouse("right", True, source="poll")
    assert any("K18" in ln and "down" in ln for ln in lines)
    assert any("right" in ln and "poll" in ln for ln in lines)
