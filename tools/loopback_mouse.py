"""Loopback: inject right + left clicks with pynput (untagged) and check that our
listeners deliver them to the controller. Also feeds a Recorder to prove the whole path."""
import ctypes
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pynput import mouse  # noqa: E402

from genshin_macro.listeners import start_listeners  # noqa: E402
from genshin_macro.recorder import Recorder  # noqa: E402

seen = []
rec = Recorder(time.monotonic, lambda: False)


class Ctl:
    def on_key(self, scan, ext, down):
        seen.append(("key", scan, down))

    def on_mouse(self, button, down):
        seen.append(("mouse", button, down))
        rec.feed("mouse_down" if down else "mouse_up", button, False)


u = ctypes.WinDLL("user32")
h = u.GetForegroundWindow()
buf = ctypes.create_unicode_buffer(256)
u.GetWindowTextW(h, buf, 256)
print("foreground:", repr(buf.value))

kb, ms = start_listeners(Ctl())
kb.wait()
ms.wait()
time.sleep(0.3)
rec.start()
c = mouse.Controller()
c.press(mouse.Button.right); time.sleep(0.03); c.release(mouse.Button.right)
time.sleep(0.05)
c.press(mouse.Button.left); time.sleep(0.03); c.release(mouse.Button.left)
time.sleep(0.4)
events = rec.stop()
kb.stop()
ms.stop()
print("listener saw:", seen)
print("recorder got:", [(e.t, e.type, e.code) for e in events])
