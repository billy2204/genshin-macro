"""Glue between the pure core (model/recorder/hotkeys/player) and the UI + listeners."""
from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Callable, Optional

from .hotkeys import HotkeyManager
from .model import EVENT_TYPES, Config, InputEvent, KeyRef, Macro, RecordedMacro, SpamMacro, new_id

MOUSE_LABELS = {"left": "Chuột trái", "right": "Chuột phải"}
DEFAULT_IGNORE_SCANS = (17, 30, 31, 32)  # W A S D
from .razer_import import parse_razer_xml
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
        path: Optional[Path] = None,
        on_path_change: Callable[[Path], None] = lambda p: None,
    ):
        self._config = config
        self._save = save
        self.path: Optional[Path] = Path(path) if path else None
        self._on_path_change = on_path_change
        self._recorder = recorder
        self._hotkeys = hotkeys
        self._player = player
        self._events = events
        self._label_for = label_for
        self._lock = threading.RLock()
        self._recording_id: Optional[str] = None
        self._capture_cb: Optional[Callable[[KeyRef], None]] = None
        self.selected_id: Optional[str] = None  # set by the UI; target of the record hotkey
        self.rebind_all()

    # ---- queries -----------------------------------------------------------
    @property
    def macros(self) -> list[Macro]:
        return list(self._config.macros)

    @property
    def random_ms(self) -> int:
        return self._config.random_ms

    @property
    def record_hotkey(self) -> Optional[KeyRef]:
        return self._config.record_hotkey

    @property
    def overlay(self) -> bool:
        return self._config.overlay

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
            m = RecordedMacro(
                id=new_id(),
                name=self._next_name(),
                ignore_keys=[KeyRef(s, False, self._label_for(s, False)) for s in DEFAULT_IGNORE_SCANS],
            )
            self._config.macros.append(m)
            self._changed()
            return m

    def import_razer(self, path: Path) -> RecordedMacro:
        """Create a Recorded macro from a Razer Synapse XML export."""
        text = Path(path).read_text(encoding="utf-8-sig")
        name, events = parse_razer_xml(text)
        with self._lock:
            m = RecordedMacro(
                id=new_id(),
                name=name or self._next_name(),
                events=events,
                ignore_keys=[KeyRef(s, False, self._label_for(s, False)) for s in DEFAULT_IGNORE_SCANS],
            )
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
                self._check_hotkey_free(fields["hotkey"], exclude_id=macro_id)
            if "interval_ms" in fields:
                fields["interval_ms"] = max(1, int(fields["interval_ms"]))
            for k, v in fields.items():
                if not hasattr(m, k):
                    raise AttributeError(k)
                setattr(m, k, v)
            self._changed()

    def _check_hotkey_free(self, hk: KeyRef, exclude_id: Optional[str] = None, allow_record: bool = False) -> None:
        for other in self._config.macros:
            if other.id != exclude_id and other.hotkey and other.hotkey.key() == hk.key():
                raise ValueError(f"Phím tắt đã dùng cho '{other.name}'")
        rh = self._config.record_hotkey
        if not allow_record and rh is not None and rh.key() == hk.key():
            raise ValueError("Phím này đang là phím Ghi")

    def set_record_hotkey(self, hk: Optional[KeyRef]) -> None:
        with self._lock:
            if hk is not None:
                self._check_hotkey_free(hk, allow_record=True)
            self._config.record_hotkey = hk
            self._changed()

    def set_overlay(self, on: bool) -> None:
        with self._lock:
            self._config.overlay = bool(on)
            self._save(self._config)

    def describe_event(self, ev: InputEvent) -> tuple[int, str, str]:
        action = "Nhấn" if ev.type.endswith("_down") else "Nhả"
        if ev.type.startswith("mouse"):
            label = MOUSE_LABELS.get(str(ev.code), str(ev.code))
        else:
            label = self._label_for(int(ev.code), bool(ev.ext))
        return (ev.t, action, label)

    # ---- ignore keys / event editing ----------------------------------------
    def _recorded(self, macro_id: str) -> RecordedMacro:
        m = self.get(macro_id)
        if not isinstance(m, RecordedMacro):
            raise ValueError("Chỉ macro kiểu Ghi mới có mục này")
        return m

    def add_ignore_key(self, macro_id: str, key: KeyRef) -> None:
        with self._lock:
            m = self._recorded(macro_id)
            if any(k.key() == key.key() for k in m.ignore_keys):
                return
            m.ignore_keys.append(key)
            self._save(self._config)

    def remove_ignore_key(self, macro_id: str, index: int) -> None:
        with self._lock:
            m = self._recorded(macro_id)
            del m.ignore_keys[index]
            self._save(self._config)

    def update_event(self, macro_id: str, index: int, *, t=None, type=None, code=None, ext=None) -> None:
        with self._lock:
            m = self._recorded(macro_id)
            ev = m.events[index]  # IndexError if out of range
            new_t = ev.t if t is None else int(t)
            new_type = ev.type if type is None else str(type)
            new_code = ev.code if code is None else code
            new_ext = ev.ext if ext is None else bool(ext)
            if new_t < 0:
                raise ValueError("Thời gian phải >= 0")
            if new_type not in EVENT_TYPES:
                raise ValueError(f"Loại sự kiện không hợp lệ: {new_type}")
            if new_type.startswith("mouse"):
                if new_code not in MOUSE_LABELS:
                    raise ValueError("Chuột chỉ có 'left' hoặc 'right'")
                new_ext = False
            else:
                new_code = int(new_code)
            m.events[index] = InputEvent(t=new_t, type=new_type, code=new_code, ext=new_ext)
            m.events.sort(key=lambda e: e.t)  # stable: keeps order of equal times
            self._save(self._config)

    def event_delays(self, macro_id: str) -> list[int]:
        """Delay of each event relative to the previous one (first = its own t)."""
        evs = self._recorded(macro_id).events
        return [e.t if i == 0 else e.t - evs[i - 1].t for i, e in enumerate(evs)]

    def set_event_delay(self, macro_id: str, index: int, delay_ms: int) -> None:
        """Set the wait before event `index`; all later events shift by the same amount."""
        with self._lock:
            m = self._recorded(macro_id)
            delay_ms = int(delay_ms)
            if delay_ms < 0:
                raise ValueError("Thời gian chờ phải >= 0")
            ev = m.events[index]
            prev_t = m.events[index - 1].t if index > 0 else 0
            shift = (prev_t + delay_ms) - ev.t
            if shift:
                for j in range(index, len(m.events)):
                    e = m.events[j]
                    m.events[j] = InputEvent(t=e.t + shift, type=e.type, code=e.code, ext=e.ext)
            self._save(self._config)

    def delete_event(self, macro_id: str, index: int) -> None:
        with self._lock:
            m = self._recorded(macro_id)
            del m.events[index]
            self._save(self._config)

    # ---- file path ------------------------------------------------------------
    def save_as(self, path: Path) -> None:
        with self._lock:
            path = Path(path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self.path = path
            self._config.save(path)
            self._on_path_change(path)

    def load_from(self, path: Path) -> None:
        path = Path(path)
        if not path.is_file():
            raise ValueError(f"Không tìm thấy file: {path}")
        with self._lock:
            self._player.stop()
            self.stop_recording()
            cfg = Config.load(path)
            self._config.random_ms = cfg.random_ms
            self._config.macros = cfg.macros
            self._config.record_hotkey = cfg.record_hotkey
            self._config.overlay = cfg.overlay
            self.path = path
            self.selected_id = None
            self.rebind_all()
            self._on_path_change(path)
            self._events.put(("reload", None))

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
        rh = self._config.record_hotkey
        if rh is not None:
            self._hotkeys.bind(rh.scan, rh.ext, self.toggle_recording)

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

    def toggle_recording(self) -> None:
        """Record hotkey: stop if recording, else start recording the selected Recorded macro."""
        with self._lock:
            if self._recording_id is not None:
                self.stop_recording()
                return
            sid = self.selected_id
            if sid is None:
                return
            try:
                m = self.get(sid)
            except KeyError:
                return
            if isinstance(m, RecordedMacro):
                self.start_recording(sid)

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
        if self._recording_id is not None and not self._is_ignored(scan, ext):
            self._recorder.feed("key_down" if down else "key_up", scan, ext)
        self._hotkeys.on_key(scan, ext, down)

    def _is_ignored(self, scan: int, ext: bool) -> bool:
        try:
            m = self.get(self._recording_id)
        except KeyError:
            return False
        return isinstance(m, RecordedMacro) and any(k.key() == (scan, bool(ext)) for k in m.ignore_keys)

    def on_mouse(self, button: str, down: bool) -> None:
        if self._capture_cb is not None:
            return
        if self._recording_id is not None:
            self._recorder.feed("mouse_down" if down else "mouse_up", button, False)

    def stop_all(self) -> None:
        self._player.stop()
        self.stop_recording()
