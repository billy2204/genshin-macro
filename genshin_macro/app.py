"""Application entry: elevation, single instance, wiring, main loop."""
from __future__ import annotations

import queue
import sys
import time
from pathlib import Path
from tkinter import messagebox

from .controller import Controller
from .hotkeys import HotkeyManager
from .model import Config
from .player import Player
from .recorder import Recorder


def config_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "macros.json"
    return Path(__file__).resolve().parents[1] / "macros.json"


def main() -> int:
    from . import winput

    if not winput.is_admin():
        winput.relaunch_as_admin()  # exits
        return 1
    if not winput.acquire_single_instance():
        messagebox.showwarning("Genshin Macro", "Ứng dụng đã đang chạy.")
        return 0

    path = config_path()
    config = Config.load(path)
    events: queue.Queue = queue.Queue()

    my_pid = winput.current_pid()

    def is_app_foreground() -> bool:
        # Any window of this process (main window, its dialogs) counts as "the app".
        # The overlay is WS_EX_NOACTIVATE so it never becomes foreground.
        return winput.foreground_pid() == my_pid

    player = Player(
        winput.Win32Output(),
        get_random_ms=lambda: controller.random_ms,
        foreground_hwnd=winput.foreground_hwnd,
        on_state=lambda mid: events.put(("state", mid)),
    )
    controller = Controller(
        config,
        save=lambda cfg: cfg.save(path),
        recorder=Recorder(time.monotonic, is_app_foreground, foreground_hwnd=winput.foreground_hwnd),
        hotkeys=HotkeyManager(is_app_foreground),
        player=player,
        events=events,
        label_for=winput.label_for,
    )

    from .listeners import start_listeners
    from .ui import App

    app = App(controller, events, on_overlay_created=winput.make_noactivate)
    kb, ms = start_listeners(controller)

    def on_close() -> None:
        controller.stop_all()
        player.join(2.0)  # let the macro thread release its keys before we exit
        kb.stop()
        ms.stop()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_close)
    app.mainloop()
    return 0
