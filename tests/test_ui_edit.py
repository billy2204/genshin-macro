"""UI: ignore-key list, event editing controls, file path controls."""
import queue
import sys
import tkinter as tk

import pytest

from genshin_macro.controller import Controller
from genshin_macro.hotkeys import HotkeyManager
from genshin_macro.model import Config, InputEvent, KeyRef
from genshin_macro.recorder import Recorder

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs a desktop")


class FakePlayer:
    running_id = None

    def toggle(self, macro):
        pass

    def stop(self):
        pass


@pytest.fixture
def app(tmp_path):
    from genshin_macro.ui import App

    events = queue.Queue()
    path = tmp_path / "macros.json"
    ctl = Controller(
        Config(), lambda cfg: cfg.save(ctl.path), Recorder(lambda: 0.0, lambda: False), HotkeyManager(lambda: False),
        FakePlayer(), events, path=path,
    )
    try:
        a = App(ctl, events)
    except tk.TclError as ex:
        pytest.skip(f"no Tk display: {ex}")
    a.withdraw()
    yield a, ctl, events, tmp_path
    a.destroy()


def _recorded_with_events(a, ctl):
    a._add_recorded()
    r = ctl.macros[0]
    ctl.update(r.id, events=[InputEvent(0, "key_down", 18), InputEvent(100, "key_up", 18), InputEvent(300, "mouse_down", "left")])
    a._load_editor()
    return r


def test_ignore_list_shows_defaults_and_add_remove(app):
    a, ctl, events, _ = app
    a._add_recorded()
    assert list(a.ignore_list.get(0, "end")) == ["SC17", "SC30", "SC31", "SC32"]
    a._capture("ignore")
    ctl.on_key(42, False, True)
    a._poll()
    assert list(a.ignore_list.get(0, "end"))[-1] == "SC42"
    a.ignore_list.selection_set(0)
    a._remove_ignore()
    assert list(a.ignore_list.get(0, "end")) == ["SC30", "SC31", "SC32", "SC42"]


def test_selecting_event_fills_edit_fields(app):
    a, ctl, _, _ = app
    _recorded_with_events(a, ctl)
    items = a.event_tree.get_children()
    a.event_tree.selection_set(items[2])
    a._on_event_select()
    assert a.ev_t_var.get() == 300
    assert a.ev_action_var.get() == "Nhấn"
    assert a.ev_kind_var.get() == "Chuột trái"


def test_apply_event_edit_changes_time_and_resorts(app):
    a, ctl, _, _ = app
    r = _recorded_with_events(a, ctl)
    items = a.event_tree.get_children()
    a.event_tree.selection_set(items[1])
    a._on_event_select()
    a.ev_t_var.set(500)
    a._apply_event()
    rows = [a.event_tree.item(i, "values") for i in a.event_tree.get_children()]
    assert [r_[0] for r_ in rows] == ["0", "300", "500"]
    assert ctl.get(r.id).events[-1].type == "key_up"


def test_apply_event_edit_to_mouse_right(app):
    a, ctl, _, _ = app
    r = _recorded_with_events(a, ctl)
    a.event_tree.selection_set(a.event_tree.get_children()[0])
    a._on_event_select()
    a.ev_kind_var.set("Chuột phải")
    a.ev_action_var.set("Nhả")
    a._apply_event()
    ev = ctl.get(r.id).events[0]
    assert (ev.type, ev.code) == ("mouse_up", "right")


def test_delete_event_button(app):
    a, ctl, _, _ = app
    r = _recorded_with_events(a, ctl)
    a.event_tree.selection_set(a.event_tree.get_children()[0])
    a._delete_event()
    assert len(ctl.get(r.id).events) == 2
    assert len(a.event_tree.get_children()) == 2


def test_save_as_and_open_update_path_label(app):
    a, ctl, _, tmp_path = app
    a._add_spam()
    target = tmp_path / "x" / "combo.json"
    a._save_as_path(target)
    assert str(target) in a.path_lbl.cget("text")
    assert target.exists()
    other = tmp_path / "other.json"
    Config(random_ms=7, macros=[]).save(other)
    a._open_path(other)
    assert str(other) in a.path_lbl.cget("text")
    assert a.listbox.size() == 0
    assert a.random_var.get() == 7
