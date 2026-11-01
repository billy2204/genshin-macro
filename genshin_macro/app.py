"""Application entry: elevation, single instance, wiring, main loop."""
from __future__ import annotations

import json
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


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _settings_file() -> Path:
    return app_dir() / "settings.json"


def load_settings() -> dict:
    try:
        data = json.loads(_settings_file().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(**changes) -> None:
    data = load_settings()
    data.update(changes)
    try:
        _settings_file().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def config_path() -> Path:
    """Default macros.json next to the exe, unless settings.json remembers another path."""
    default = app_dir() / "macros.json"
    try:
        p = Path(load_settings()["config_path"])
        return p if p.is_file() else default
    except Exception:
        return default


def remember_config_path(path: Path) -> None:
    save_settings(config_path=str(path))


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
        save=lambda cfg: cfg.save(controller.path),
        recorder=Recorder(time.monotonic, is_app_foreground, foreground_hwnd=winput.foreground_hwnd),
        hotkeys=HotkeyManager(is_app_foreground),
        player=player,
        events=events,
        label_for=winput.label_for,
        path=path,
        on_path_change=remember_config_path,
    )

    from .listeners import start_listeners
    from .ui import App
    from .updater import DEFAULT_UPDATE_URL

    app = App(
        controller,
        events,
        on_overlay_created=winput.make_noactivate,
        update_url=load_settings().get("update_url", DEFAULT_UPDATE_URL),
        on_update_url_change=lambda u: save_settings(update_url=u),
    )
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
