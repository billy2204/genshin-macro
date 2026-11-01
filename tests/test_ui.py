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
