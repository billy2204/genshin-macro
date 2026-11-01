"""UI wiring smoke test: real Controller + fake Player, real Tk window (withdrawn)."""
import queue
import sys
import tkinter as tk

import pytest

from genshin_macro.controller import Controller
from genshin_macro.hotkeys import HotkeyManager
from genshin_macro.model import Config, KeyRef
from genshin_macro.recorder import Recorder

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs a desktop")


class FakePlayer:
    running_id = None

    def toggle(self, macro):
        self.running_id = None if self.running_id == macro.id else macro.id

    def stop(self):
        self.running_id = None


@pytest.fixture
def app():
    from genshin_macro.ui import App

    events = queue.Queue()
    ctl = Controller(Config(), lambda cfg: None, Recorder(lambda: 0.0, lambda: False), HotkeyManager(lambda: False), FakePlayer(), events)
    try:
        a = App(ctl, events)
    except tk.TclError as ex:  # no display
        pytest.skip(f"no Tk display: {ex}")
    a.withdraw()
    yield a, ctl, events
    a.destroy()


def test_add_select_and_editor_shows_kind(app):
    a, ctl, _ = app
    a._add_spam()
    a._add_recorded()
    a.update()
    assert a.listbox.size() == 2
    assert a.kind_lbl.cget("text") == "Ghi thao tác"
    a.listbox.selection_clear(0, "end")
    a.listbox.selection_set(0)
    a._on_select()
    assert a.kind_lbl.cget("text") == "Spam phím"


def test_captured_event_sets_hotkey_and_refreshes_list(app):
    a, ctl, events = app
    a._add_spam()
    a._capture("hotkey")
    assert a.hotkey_btn.cget("text") == "Nhấn phím…"
    ctl.on_key(66, False, True)  # listener thread would do this
    a._poll()
    a.update()
    m = ctl.macros[0]
    assert m.hotkey == KeyRef(66, False, "SC66")
    assert "[SC66]" in a.listbox.get(0)
    assert a.hotkey_btn.cget("text") == "SC66"


def test_duplicate_hotkey_shows_error_not_crash(app, monkeypatch):
    a, ctl, _ = app
    shown = []
    monkeypatch.setattr("genshin_macro.ui.messagebox.showerror", lambda *x: shown.append(x))
    a._add_spam()
    a._add_spam()
    ctl.update(ctl.macros[0].id, hotkey=KeyRef(66, False, "F8"))
    a._selected = ctl.macros[1].id
    a._set_field("hotkey", KeyRef(66, False, "F8"))
    assert shown and ctl.macros[1].hotkey is None


def test_status_reflects_recording(app, monkeypatch):
    a, ctl, events = app
    monkeypatch.setattr("genshin_macro.ui.messagebox.showinfo", lambda *x: None)
    a._add_recorded()
    a._toggle_record()
    a._poll()
    assert a.status.cget("text").startswith("Đang ghi")
    assert a.rec_btn.cget("text") == "■ Dừng ghi"
    a._toggle_record()
    a._poll()
    assert a.status.cget("text") == "Sẵn sàng"


def test_selection_updates_controller_selected_id(app):
    a, ctl, _ = app
    a._add_spam()
    a._add_recorded()
    assert ctl.selected_id == ctl.macros[1].id
    a.listbox.selection_clear(0, "end")
    a.listbox.selection_set(0)
    a._on_select()
    assert ctl.selected_id == ctl.macros[0].id


def test_event_list_shows_recorded_events(app):
    from genshin_macro.model import InputEvent

    a, ctl, _ = app
    a._add_recorded()
    ctl.update(ctl.macros[0].id, events=[InputEvent(0, "key_down", 30), InputEvent(120, "key_up", 30), InputEvent(300, "mouse_down", "left")])
    a._load_editor()
    rows = [a.event_tree.item(i, "values") for i in a.event_tree.get_children()]
    assert rows == [("0", "Nhấn", "SC30"), ("120", "Nhả", "SC30"), ("180", "Nhấn", "Chuột trái")]  # delays


def test_record_hotkey_capture_sets_config(app):
    a, ctl, _ = app
    a._capture("record")
    assert a.record_btn.cget("text") == "Nhấn phím…"
    ctl.on_key(68, False, True)
    a._poll()
    assert ctl.record_hotkey == KeyRef(68, False, "SC68")
    assert a.record_btn.cget("text") == "SC68"


def test_overlay_toggle_creates_and_destroys_window(app, monkeypatch):
    a, ctl, _ = app
    assert a.overlay is not None  # default on
    a.overlay_var.set(False)
    a._overlay_changed()
    assert a.overlay is None and ctl.overlay is False
    a.overlay_var.set(True)
    a._overlay_changed()
    assert a.overlay is not None and ctl.overlay is True
    monkeypatch.setattr("genshin_macro.ui.messagebox.showinfo", lambda *x: None)
    a._add_recorded()
    a._toggle_record()
    a._poll()
    assert a.overlay.label.cget("text").startswith("● GHI")
