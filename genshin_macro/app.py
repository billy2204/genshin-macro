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

    app_hwnd = {"value": 0}

    def is_app_foreground() -> bool:
        return app_hwnd["value"] != 0 and winput.root_hwnd(winput.foreground_hwnd()) == app_hwnd["value"]

    player = Player(
        winput.Win32Output(),
        get_random_ms=lambda: controller.random_ms,
        foreground_hwnd=winput.foreground_hwnd,
        on_state=lambda mid: events.put(("state", mid)),
    )
    controller = Controller(
        config,
        save=lambda cfg: cfg.save(path),
        recorder=Recorder(time.monotonic, is_app_foreground),
        hotkeys=HotkeyManager(is_app_foreground),
        player=player,
        events=events,
        label_for=winput.label_for,
    )

    from .listeners import start_listeners
    from .ui import App

    app = App(controller, events, on_overlay_created=winput.make_noactivate)
    app.update_idletasks()
    app_hwnd["value"] = winput.root_hwnd(app.winfo_id())
    kb, ms = start_listeners(controller)

    def on_close() -> None:
        controller.stop_all()
        kb.stop()
        ms.stop()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_close)
    app.mainloop()
    return 0
