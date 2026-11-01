"""Fallback mouse-button source: poll the async button state and report transitions.

Games that read the mouse through raw input / DirectInput can leave WH_MOUSE_LL hooks
silent for clicks, but GetAsyncKeyState still reflects the physical buttons. The poller
runs only while recording; the Recorder's held-set de-duplicates against hook events.
"""
from __future__ import annotations

import threading
from typing import Callable

VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
BUTTONS = {VK_LBUTTON: "left", VK_RBUTTON: "right"}


class MouseButtonPoller:
    def __init__(self, is_down: Callable[[int], bool], on_change: Callable[[str, bool], None], interval_s: float = 0.002):
        self._is_down = is_down
        self._on_change = on_change
        self._interval = interval_s
        self._state = {vk: bool(is_down(vk)) for vk in BUTTONS}
        # a button already held when we start was never seen pressed: ignore its first release too
        self._skip_release = {vk for vk, held in self._state.items() if held}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def tick(self) -> None:
        for vk, name in BUTTONS.items():
            now = bool(self._is_down(vk))
            if now != self._state[vk]:
                self._state[vk] = now
                if not now and vk in self._skip_release:
                    self._skip_release.discard(vk)
                    continue
                self._on_change(name, now)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.tick()
            except Exception:
                pass

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="mouse-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t is not threading.current_thread():
            t.join(timeout=0.5)
        self._thread = None
