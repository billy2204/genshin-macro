"""Pure hotkey dispatch: single-key hotkeys, fire once per physical press."""
from __future__ import annotations

from typing import Callable

KeyId = tuple[int, bool]


class HotkeyManager:
    def __init__(self, is_app_foreground: Callable[[], bool]):
        self._is_app_foreground = is_app_foreground
        self._bindings: dict[KeyId, Callable[[], None]] = {}
        self._held: set[KeyId] = set()

    def bind(self, scan: int, ext: bool, cb: Callable[[], None]) -> None:
        self._bindings[(scan, bool(ext))] = cb

    def unbind(self, scan: int, ext: bool) -> None:
        self._bindings.pop((scan, bool(ext)), None)

    def clear(self) -> None:
        self._bindings.clear()

    def is_bound(self, scan: int, ext: bool) -> bool:
        return (scan, bool(ext)) in self._bindings

    def on_key(self, scan: int, ext: bool, down: bool) -> None:
        key = (scan, bool(ext))
        if not down:
            self._held.discard(key)
            return
        if key in self._held:
            return  # auto-repeat
        self._held.add(key)
        if self._is_app_foreground():
            return
        cb = self._bindings.get(key)
        if cb is not None:
            cb()
