"""pynput low-level hooks that feed raw scan-code events into the Controller."""
from __future__ import annotations

from pynput import keyboard, mouse

from .winput import MAGIC

WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x0100, 0x0101, 0x0104, 0x0105
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0201, 0x0202, 0x0204, 0x0205
LLKHF_EXTENDED = 0x01

_MOUSE_MSGS = {
    WM_LBUTTONDOWN: ("left", True),
    WM_LBUTTONUP: ("left", False),
    WM_RBUTTONDOWN: ("right", True),
    WM_RBUTTONUP: ("right", False),
}


def start_listeners(controller) -> tuple[keyboard.Listener, mouse.Listener]:
    def kb_filter(msg, data):
        if data.dwExtraInfo == MAGIC:
            return
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            down = True
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            down = False
        else:
            return
        try:
            controller.on_key(int(data.scanCode), bool(data.flags & LLKHF_EXTENDED), down)
        except Exception:
            pass  # never let an error kill the hook

    def mouse_filter(msg, data):
        if data.dwExtraInfo == MAGIC:
            return
        hit = _MOUSE_MSGS.get(msg)
        if hit is None:
            return
        try:
            controller.on_mouse(hit[0], hit[1])
        except Exception:
            pass

    kb = keyboard.Listener(win32_event_filter=kb_filter, on_press=lambda k: None, on_release=lambda k: None)
    ms = mouse.Listener(win32_event_filter=mouse_filter)
    kb.start()
    ms.start()
    return kb, ms
