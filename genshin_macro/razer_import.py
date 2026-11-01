"""Import Razer Synapse macro XML exports into our InputEvent timeline.

Razer format (observed, Synapse 3):
  <MacroEvent><Type>0</Type><Number>0.3</Number>            delay in seconds
  <MacroEvent><Type>1</Type><KeyEvent><Makecode>16</Makecode><State>0|1</State>   key, set-1 scan code, 0=down 1=up
  <MacroEvent><Type>2</Type><MouseEvent><MouseButton>0|1|2</MouseButton><State>  mouse: 0 left, 1 right, 2 middle
  <MacroEvent><Type>6</Type><Number>N</Number><LoopEvent><State>0|1</State>      loop block start/end, repeat N times
  Makecodes >= 0xE000 are extended keys (0xE04D = right arrow).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from .model import InputEvent

MOUSE_BUTTONS = {"0": "left", "1": "right"}


def parse_razer_xml(text: str) -> tuple[str, list[InputEvent]]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError as ex:
        raise ValueError(f"File không phải XML hợp lệ: {ex}") from ex
    if root.tag != "Macro" or root.find("MacroEvents") is None:
        raise ValueError("Không phải file macro Razer (thiếu <Macro>/<MacroEvents>)")
    name = (root.findtext("Name") or "Razer macro").strip()
    raw = list(root.find("MacroEvents"))
    events: list[InputEvent] = []
    _emit(raw, 0, len(raw), 0.0, events)
    return name, events


def _emit(raw, start: int, end: int, t_ms: float, out: list[InputEvent]) -> float:
    """Walk raw[start:end], appending events; returns the time after the last one."""
    i = start
    while i < end:
        e = raw[i]
        typ = (e.findtext("Type") or "").strip()
        if typ == "0":
            t_ms += float(e.findtext("Number") or 0) * 1000.0
        elif typ == "1":
            code = _int(e.findtext("KeyEvent/Makecode"))
            state = _int(e.findtext("KeyEvent/State"))
            if code is not None and state is not None:
                ext = code >= 0xE000
                out.append(InputEvent(t=int(round(t_ms)), type="key_down" if state == 0 else "key_up", code=code & 0xFF, ext=ext))
        elif typ == "2":
            button = MOUSE_BUTTONS.get((e.findtext("MouseEvent/MouseButton") or "").strip())
            state = _int(e.findtext("MouseEvent/State"))
            if button is not None and state is not None:
                out.append(InputEvent(t=int(round(t_ms)), type="mouse_down" if state == 0 else "mouse_up", code=button))
        elif typ == "6" and (e.findtext("LoopEvent/State") or "").strip() == "0":
            count = max(1, _int(e.findtext("Number")) or 1)
            close = _find_loop_end(raw, i + 1, end)
            for _ in range(count):
                t_ms = _emit(raw, i + 1, close, t_ms, out)
            i = close  # skip the closing marker
        i += 1
    return t_ms


def _find_loop_end(raw, start: int, end: int) -> int:
    depth = 0
    for j in range(start, end):
        e = raw[j]
        if (e.findtext("Type") or "").strip() != "6":
            continue
        state = (e.findtext("LoopEvent/State") or "").strip()
        if state == "0":
            depth += 1
        elif state == "1":
            if depth == 0:
                return j
            depth -= 1
    return end  # unterminated loop: treat rest as body


def _int(s: Optional[str]) -> Optional[int]:
    try:
        return int(float(s.strip())) if s is not None else None
    except ValueError:
        return None
