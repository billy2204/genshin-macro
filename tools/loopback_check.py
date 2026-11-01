"""Loopback check: our tagged SendInput must be invisible to our listeners,
while untagged injected input (pynput Controller) must reach the controller."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pynput import keyboard  # noqa: E402

from genshin_macro.listeners import start_listeners  # noqa: E402
from genshin_macro.winput import Win32Output  # noqa: E402

seen, raw = [], []


class Ctl:
    def on_key(self, scan, ext, down):
        seen.append(("key", scan, ext, down))

    def on_mouse(self, button, down):
        seen.append(("mouse", button, down))


rawl = keyboard.Listener(
    win32_event_filter=lambda msg, d: raw.append((hex(msg), d.scanCode, d.dwExtraInfo)),
    on_press=lambda k: None,
    on_release=lambda k: None,
)
rawl.start()
kb, ms = start_listeners(Ctl())
rawl.wait(); kb.wait(); ms.wait()
time.sleep(0.3)
out = Win32Output()
out.key_down(0x57, False); time.sleep(0.03); out.key_up(0x57, False)  # F11
out.mouse_down("right"); time.sleep(0.03); out.mouse_up("right")
c = keyboard.Controller(); c.press(keyboard.Key.f13); c.release(keyboard.Key.f13)  # untagged
time.sleep(0.5)
rawl.stop(); kb.stop(); ms.stop()
print("raw hook saw:", raw)
print("controller saw (expect only F13 scan 0x64 down/up):", seen)
