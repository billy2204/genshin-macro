"""Manual smoke test: focus Notepad, run this, expect 'f' then a right-click menu after 3 s."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genshin_macro.winput import Win32Output, foreground_hwnd, label_for  # noqa: E402

out = Win32Output()
print("Sending to foreground window in 3 s... hwnd =", foreground_hwnd(), "label(0x21) =", label_for(0x21, False))
time.sleep(3)
out.key_down(0x21, False)
time.sleep(0.05)
out.key_up(0x21, False)
time.sleep(0.2)
out.mouse_down("right")
time.sleep(0.05)
out.mouse_up("right")
print("done")
