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
    assert a.ev_t_var.get() == 200  # delay since previous event (300 - 100)
    assert a.ev_action_var.get() == "Nhấn"
    assert a.ev_kind_var.get() == "Chuột trái"


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


def test_tree_shows_delay_not_absolute_time_and_total_line(app):
    a, ctl, _, _ = app
    r = _recorded_with_events(a, ctl)  # t = 0, 100, 300
    rows = [a.event_tree.item(i, "values") for i in a.event_tree.get_children()]
    assert [row[0] for row in rows] == ["0", "100", "200"]
    assert "300 ms" in a.rec_info.cget("text")


def test_apply_delay_edit_shifts_following(app):
    a, ctl, _, _ = app
    r = _recorded_with_events(a, ctl)
    a.event_tree.selection_set(a.event_tree.get_children()[1])
    a._on_event_select()
    assert a.ev_t_var.get() == 100  # delay, not absolute
    a.ev_t_var.set(400)
    a._apply_event()
    assert [e.t for e in ctl.get(r.id).events] == [0, 400, 600]
    rows = [a.event_tree.item(i, "values") for i in a.event_tree.get_children()]
    assert [row[0] for row in rows] == ["0", "400", "200"]
    assert a.event_tree.selection() == ("1",)


def test_update_now_runs_full_flow_without_prompts(app, monkeypatch):
    from pathlib import Path as _P

    a, ctl, _, _ = app
    calls = []
    monkeypatch.setattr("genshin_macro.ui.updater.check_for_update", lambda url: ("9.9.9", "https://x/new.exe"))
    monkeypatch.setattr("genshin_macro.ui.updater.download", lambda url, dest: calls.append(("download", url)) or dest)
    monkeypatch.setattr("genshin_macro.ui.updater.current_exe", lambda: _P("C:/fake/GenshinMacro.exe"))
    monkeypatch.setattr("genshin_macro.ui.updater.apply_update", lambda p: calls.append(("apply", p)))

    def no_prompt(*a_, **k):
        raise AssertionError("update must not ask questions")

    monkeypatch.setattr("genshin_macro.ui.messagebox.askyesno", no_prompt)
    a.update_url = "https://x/manifest.json"
    a._update_now()
    assert calls[0] == ("download", "https://x/new.exe")
    assert calls[1][0] == "apply"


def test_update_now_reports_up_to_date(app, monkeypatch):
    a, ctl, _, _ = app
    shown = []
    monkeypatch.setattr("genshin_macro.ui.updater.check_for_update", lambda url: None)
    monkeypatch.setattr("genshin_macro.ui.messagebox.showinfo", lambda *x, **k: shown.append(x))
    a.update_url = "https://x/manifest.json"
    a._update_now()
    assert shown and "mới nhất" in shown[0][1]


def test_update_now_error_opens_dialog(app, monkeypatch):
    a, ctl, _, _ = app
    opened, errors = [], []

    def boom(url):
        raise OSError("HTTP Error 404: Not Found")

    monkeypatch.setattr("genshin_macro.ui.updater.check_for_update", boom)
    monkeypatch.setattr("genshin_macro.ui.messagebox.showerror", lambda *x, **k: errors.append(x))
    monkeypatch.setattr(a, "_update_dialog", lambda: opened.append(1))
    a.update_url = "https://x/manifest.json"
    a._update_now()
    assert errors and "404" in errors[0][1]
    assert opened == [1]


def test_import_razer_button_adds_and_selects_macro(app, tmp_path):
    a, ctl, _, _ = app
    f = tmp_path / "Skirk.xml"
    f.write_text(
        "<Macro><Name>Skirk</Name><MacroEvents>"
        "<MacroEvent><Type>1</Type><KeyEvent><Makecode>18</Makecode><State>0</State></KeyEvent></MacroEvent>"
        "<MacroEvent><Type>0</Type><Number>0.1</Number></MacroEvent>"
        "<MacroEvent><Type>1</Type><KeyEvent><Makecode>18</Makecode><State>1</State></KeyEvent></MacroEvent>"
        "</MacroEvents></Macro>",
        encoding="utf-8",
    )
    a._import_razer_path(f)
    assert a.listbox.size() == 1 and "Skirk" in a.listbox.get(0)
    assert a.kind_lbl.cget("text") == "Ghi thao tác"
    assert len(a.event_tree.get_children()) == 2
