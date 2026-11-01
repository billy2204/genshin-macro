"""Macro playback: pure `run_macro` plus a threaded `Player` wrapper."""
from __future__ import annotations

import random
import threading
import time
from typing import Callable, Optional, Protocol

from .model import Macro, RecordedMacro, SpamMacro
from .timing import loop_gap_ms, schedule, spam_gap_ms, spam_hold_ms


class Output(Protocol):
    def key_down(self, scan: int, ext: bool) -> None: ...
    def key_up(self, scan: int, ext: bool) -> None: ...
    def mouse_down(self, button: str) -> None: ...
    def mouse_up(self, button: str) -> None: ...


def _real_sleep_ms(ms: float) -> None:
    if ms > 0:
        time.sleep(ms / 1000.0)


class _Pressed:
    """Tracks what this run has pressed so it can be released on exit."""

    def __init__(self, output: Output):
        self._output = output
        self._order: list[tuple] = []

    def emit(self, type: str, code, ext: bool) -> None:
        if type == "key_down":
            self._output.key_down(code, ext)
            self._order.append(("key", code, ext))
        elif type == "key_up":
            self._output.key_up(code, ext)
            self._forget(("key", code, ext))
        elif type == "mouse_down":
            self._output.mouse_down(code)
            self._order.append(("mouse", code))
        elif type == "mouse_up":
            self._output.mouse_up(code)
            self._forget(("mouse", code))

    def _forget(self, item: tuple) -> None:
        if item in self._order:
            self._order.remove(item)

    def release_all(self) -> None:
        for item in reversed(self._order):
            if item[0] == "key":
                self._output.key_up(item[1], item[2])
            else:
                self._output.mouse_up(item[1])
        self._order.clear()


def run_macro(
    macro: Macro,
    output: Output,
    stop: threading.Event,
    random_ms: int,
    rng,
    sleep: Callable[[float], None],
    still_foreground: Callable[[], bool],
) -> None:
    pressed = _Pressed(output)

    def should_stop() -> bool:
        return stop.is_set() or not still_foreground()

    try:
        if isinstance(macro, SpamMacro):
            if macro.key is None:
                return
            scan, ext = macro.key.scan, macro.key.ext
            while not should_stop():
                pressed.emit("key_down", scan, ext)
                sleep(spam_hold_ms(random_ms, rng))
                if stop.is_set():
                    break
                pressed.emit("key_up", scan, ext)
                sleep(spam_gap_ms(macro.interval_ms, random_ms, rng))
        elif isinstance(macro, RecordedMacro):
            if not macro.events:
                return
            while True:
                for delay, ev in schedule(macro.events, random_ms, rng):
                    if should_stop():
                        return
                    sleep(delay)
                    if stop.is_set():
                        return
                    pressed.emit(ev.type, ev.code, ev.ext)
                if not macro.loop or should_stop():
                    return
                sleep(loop_gap_ms(random_ms, rng))
    finally:
        pressed.release_all()


class Player:
    def __init__(
        self,
        output: Output,
        get_random_ms: Callable[[], int],
        foreground_hwnd: Callable[[], int],
        on_state: Callable[[Optional[str]], None],
        sleep: Callable[[float], None] = _real_sleep_ms,
        rng=None,
    ):
        self._output = output
        self._get_random_ms = get_random_ms
        self._foreground_hwnd = foreground_hwnd
        self._on_state = on_state
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running_id: Optional[str] = None

    @property
    def running_id(self) -> Optional[str]:
        return self._running_id

    def start(self, macro: Macro) -> None:
        self.stop()
        with self._lock:
            self._stop = threading.Event()
            stop = self._stop
            hwnd0 = self._foreground_hwnd()
            self._running_id = macro.id
            self._on_state(macro.id)

            def still_fg() -> bool:
                return self._foreground_hwnd() == hwnd0

            def target() -> None:
                try:
                    run_macro(macro, self._output, stop, self._get_random_ms(), self._rng, self._sleep, still_fg)
                finally:
                    with self._lock:
                        if self._running_id == macro.id and self._stop is stop:
                            self._running_id = None
                    self._on_state(None)

            self._thread = threading.Thread(target=target, name=f"macro-{macro.id}", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
            self._thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with self._lock:
            self._running_id = None

    def toggle(self, macro: Macro) -> None:
        if self._running_id == macro.id:
            self.stop()
        else:
            self.start(macro)
