"""Pure recording logic: turns raw key/mouse events into a clean InputEvent list."""
from __future__ import annotations

from typing import Callable, Hashable, Union

from .model import InputEvent

Code = Union[int, str]


class Recorder:
    def __init__(
        self,
        clock: Callable[[], float],
        is_app_foreground: Callable[[], bool],
        foreground_hwnd: Callable[[], int] = lambda: 0,
    ):
        self._clock = clock
        self._is_app_foreground = is_app_foreground
        self._foreground_hwnd = foreground_hwnd
        self._target_hwnd: int | None = None  # window the recording is locked to
        self._recording = False
        self._events: list[InputEvent] = []
        self._held: dict[Hashable, int] = {}  # (code, ext) -> index of its key_down in _events
        self._t0: float | None = None

    @property
    def recording(self) -> bool:
        return self._recording

    @property
    def event_count(self) -> int:
        return len(self._events)

    def start(self) -> None:
        self._recording = True
        self._events = []
        self._held = {}
        self._t0 = None
        self._target_hwnd = None

    def feed(self, type: str, code: Code, ext: bool) -> None:
        if not self._recording or self._is_app_foreground():
            return
        fg = self._foreground_hwnd()
        if self._target_hwnd is None:
            self._target_hwnd = fg  # lock onto the window the first event went to
        elif fg != self._target_hwnd:
            return  # user switched windows (Alt+Tab etc.): ignore everything after
        key = (code, bool(ext))
        is_down = type.endswith("_down")
        if is_down and key in self._held:
            return  # auto-repeat
        if not is_down and key not in self._held:
            return  # orphan up
        now = self._clock()
        if self._t0 is None:
            self._t0 = now
        t = int(round((now - self._t0) * 1000))
        self._events.append(InputEvent(t=t, type=type, code=code, ext=bool(ext)))
        if is_down:
            self._held[key] = len(self._events) - 1
        else:
            del self._held[key]

    def stop(self) -> list[InputEvent]:
        self._recording = False
        drop = set(self._held.values())
        events = [e for i, e in enumerate(self._events) if i not in drop]
        self._held = {}
        if events and events[0].t != 0:
            shift = events[0].t
            events = [InputEvent(t=e.t - shift, type=e.type, code=e.code, ext=e.ext) for e in events]
        self._events = events
        return list(events)
