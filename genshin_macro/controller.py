"""Glue between the pure core (model/recorder/hotkeys/player) and the UI + listeners."""
from __future__ import annotations

import queue
import threading
from typing import Callable, Optional

from .hotkeys import HotkeyManager
from .model import Config, KeyRef, Macro, RecordedMacro, SpamMacro, new_id
from .recorder import Recorder


class Controller:
    def __init__(
        self,
        config: Config,
        save: Callable[[Config], None],
        recorder: Recorder,
        hotkeys: HotkeyManager,
        player,
        events: queue.Queue,
        label_for: Callable[[int, bool], str] = lambda s, e: f"SC{s}",
    ):
        self._config = config
        self._save = save
        self._recorder = recorder
        self._hotkeys = hotkeys
        self._player = player
        self._events = events
        self._label_for = label_for
        self._lock = threading.RLock()
        self._recording_id: Optional[str] = None
        self._capture_cb: Optional[Callable[[KeyRef], None]] = None
        self.rebind_all()

    # ---- queries -----------------------------------------------------------
    @property
    def macros(self) -> list[Macro]:
        return list(self._config.macros)

    @property
    def random_ms(self) -> int:
        return self._config.random_ms

    @property
    def recording_id(self) -> Optional[str]:
        return self._recording_id

    @property
    def running_id(self) -> Optional[str]:
        return self._player.running_id

    def get(self, macro_id: str) -> Macro:
        for m in self._config.macros:
            if m.id == macro_id:
                return m
        raise KeyError(macro_id)

    # ---- editing -----------------------------------------------------------
    def _next_name(self) -> str:
        return f"Macro {len(self._config.macros) + 1}"

    def add_spam(self) -> SpamMacro:
        with self._lock:
            m = SpamMacro(id=new_id(), name=self._next_name())
            self._config.macros.append(m)
            self._changed()
            return m

    def add_recorded(self) -> RecordedMacro:
        with self._lock:
            m = RecordedMacro(id=new_id(), name=self._next_name())
            self._config.macros.append(m)
            self._changed()
            return m

    def delete(self, macro_id: str) -> None:
        with self._lock:
            if self._player.running_id == macro_id:
                self._player.stop()
            if self._recording_id == macro_id:
                self.stop_recording()
            self._config.macros = [m for m in self._config.macros if m.id != macro_id]
            self._changed()

    def update(self, macro_id: str, **fields) -> None:
        with self._lock:
            m = self.get(macro_id)
            if "hotkey" in fields and fields["hotkey"] is not None:
                hk: KeyRef = fields["hotkey"]
                for other in self._config.macros:
                    if other.id != macro_id and other.hotkey and other.hotkey.key() == hk.key():
                        raise ValueError(f"Phím tắt đã dùng cho '{other.name}'")
            if "interval_ms" in fields:
                fields["interval_ms"] = max(1, int(fields["interval_ms"]))
            for k, v in fields.items():
                if not hasattr(m, k):
                    raise AttributeError(k)
                setattr(m, k, v)
            self._changed()

    def set_random_ms(self, value: int) -> None:
        with self._lock:
            self._config.random_ms = max(0, int(value))
            self._save(self._config)

    def _changed(self) -> None:
        self.rebind_all()
        self._save(self._config)

    def rebind_all(self) -> None:
        self._hotkeys.clear()
        for m in self._config.macros:
            if m.hotkey is not None:
                self._hotkeys.bind(m.hotkey.scan, m.hotkey.ext, self._make_hotkey_cb(m.id))

    def _make_hotkey_cb(self, macro_id: str) -> Callable[[], None]:
        def cb() -> None:
            if self._recording_id == macro_id:
                self.stop_recording()
                return
            if self._recording_id is not None:
                return  # another macro is being recorded; don't play over it
            try:
                macro = self.get(macro_id)
            except KeyError:
                return
            self._player.toggle(macro)
            self._events.put(("state", self._player.running_id))

        return cb

    # ---- recording ---------------------------------------------------------
    def start_recording(self, macro_id: str) -> None:
        with self._lock:
            m = self.get(macro_id)
            if not isinstance(m, RecordedMacro):
                raise ValueError("Chỉ macro kiểu Ghi mới ghi được")
            self._player.stop()
            if self._recording_id is not None:
                self.stop_recording()
            self._recording_id = macro_id
            self._recorder.start()
            self._events.put(("recording", macro_id))

    def stop_recording(self) -> None:
        with self._lock:
            if self._recording_id is None:
                return
            events = self._recorder.stop()
            macro_id, self._recording_id = self._recording_id, None
            try:
                m = self.get(macro_id)
                if isinstance(m, RecordedMacro):
                    m.events = events
                    self._save(self._config)
            except KeyError:
                pass
            self._events.put(("recording", None))

    # ---- capture -----------------------------------------------------------
    def begin_capture(self, cb: Callable[[KeyRef], None]) -> None:
        self._capture_cb = cb

    def cancel_capture(self) -> None:
        self._capture_cb = None

    # ---- raw input from listener thread ------------------------------------
    def on_key(self, scan: int, ext: bool, down: bool) -> None:
        cb = self._capture_cb
        if cb is not None:
            if down:
                self._capture_cb = None
                cb(KeyRef(scan=scan, ext=bool(ext), label=self._label_for(scan, bool(ext))))
            return
        if self._recording_id is not None:
            self._recorder.feed("key_down" if down else "key_up", scan, ext)
        self._hotkeys.on_key(scan, ext, down)

    def on_mouse(self, button: str, down: bool) -> None:
        if self._capture_cb is not None:
            return
        if self._recording_id is not None:
            self._recorder.feed("mouse_down" if down else "mouse_up", button, False)

    def stop_all(self) -> None:
        self._player.stop()
        self.stop_recording()
