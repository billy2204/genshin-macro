"""Data model and JSON persistence for macros. Pure Python, no Win32."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

EVENT_TYPES = ("key_down", "key_up", "mouse_down", "mouse_up")
DEFAULT_RANDOM_MS = 100
CONFIG_VERSION = 1


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class KeyRef:
    scan: int
    ext: bool
    label: str

    def to_dict(self) -> dict:
        return {"scan": self.scan, "ext": self.ext, "label": self.label}

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> Optional["KeyRef"]:
        if not d:
            return None
        return cls(scan=int(d["scan"]), ext=bool(d.get("ext", False)), label=str(d.get("label", f"SC{d['scan']}")))

    def key(self) -> tuple[int, bool]:
        return (self.scan, self.ext)


@dataclass
class InputEvent:
    t: int
    type: str
    code: Union[int, str]
    ext: bool = False

    def to_dict(self) -> dict:
        return {"t": self.t, "type": self.type, "code": self.code, "ext": self.ext}

    @classmethod
    def from_dict(cls, d: dict) -> "InputEvent":
        return cls(t=int(d["t"]), type=str(d["type"]), code=d["code"], ext=bool(d.get("ext", False)))


@dataclass
class SpamMacro:
    id: str
    name: str
    hotkey: Optional[KeyRef] = None
    key: Optional[KeyRef] = None
    interval_ms: int = 80
    kind = "spam"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "hotkey": self.hotkey.to_dict() if self.hotkey else None,
            "key": self.key.to_dict() if self.key else None,
            "interval_ms": self.interval_ms,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SpamMacro":
        return cls(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name", "Spam")),
            hotkey=KeyRef.from_dict(d.get("hotkey")),
            key=KeyRef.from_dict(d.get("key")),
            interval_ms=max(1, int(d.get("interval_ms", 80))),
        )


@dataclass
class RecordedMacro:
    id: str
    name: str
    hotkey: Optional[KeyRef] = None
    loop: bool = False
    events: list[InputEvent] = field(default_factory=list)
    ignore_keys: list[KeyRef] = field(default_factory=list)  # never recorded (e.g. WASD)
    kind = "recorded"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "id": self.id,
            "name": self.name,
            "hotkey": self.hotkey.to_dict() if self.hotkey else None,
            "loop": self.loop,
            "events": [e.to_dict() for e in self.events],
            "ignore_keys": [k.to_dict() for k in self.ignore_keys],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RecordedMacro":
        return cls(
            id=str(d.get("id") or new_id()),
            name=str(d.get("name", "Recorded")),
            hotkey=KeyRef.from_dict(d.get("hotkey")),
            loop=bool(d.get("loop", False)),
            events=[InputEvent.from_dict(e) for e in d.get("events", [])],
            ignore_keys=[k for k in (KeyRef.from_dict(x) for x in d.get("ignore_keys", [])) if k is not None],
        )

    @property
    def duration_ms(self) -> int:
        return self.events[-1].t if self.events else 0


Macro = Union[SpamMacro, RecordedMacro]


def macro_from_dict(d: dict) -> Macro:
    kind = d.get("kind")
    if kind == "spam":
        return SpamMacro.from_dict(d)
    if kind == "recorded":
        return RecordedMacro.from_dict(d)
    raise ValueError(f"Unknown macro kind: {kind!r}")


@dataclass
class Config:
    random_ms: int = DEFAULT_RANDOM_MS
    macros: list[Macro] = field(default_factory=list)
    record_hotkey: Optional[KeyRef] = None
    overlay: bool = True

    def to_dict(self) -> dict:
        return {
            "version": CONFIG_VERSION,
            "random_ms": self.random_ms,
            "record_hotkey": self.record_hotkey.to_dict() if self.record_hotkey else None,
            "overlay": self.overlay,
            "macros": [m.to_dict() for m in self.macros],
        }

    @classmethod
    def from_dict(cls, d: Any) -> "Config":
        if not isinstance(d, dict):
            return cls()
        try:
            random_ms = max(0, int(d.get("random_ms", DEFAULT_RANDOM_MS)))
        except (TypeError, ValueError):
            random_ms = DEFAULT_RANDOM_MS
        raw = d.get("macros", [])
        macros: list[Macro] = []
        for m in raw if isinstance(raw, list) else []:
            try:
                macros.append(macro_from_dict(m))
            except Exception:
                continue  # skip one bad entry, keep the rest
        return cls(
            random_ms=random_ms,
            macros=macros,
            record_hotkey=KeyRef.from_dict(d.get("record_hotkey")),
            overlay=bool(d.get("overlay", True)),
        )

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Never raises. A file that exists but cannot be parsed is copied to
        `<name>.bak` so the next save does not destroy the user's data."""
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return cls()
        try:
            return cls.from_dict(json.loads(text))
        except Exception:
            try:
                path.with_suffix(path.suffix + ".bak").write_text(text, encoding="utf-8")
            except OSError:
                pass
            return cls()

    def save(self, path: Path) -> None:
        path = Path(path)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
