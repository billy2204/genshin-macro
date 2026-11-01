"""Win32 edge: SendInput output, foreground window, key labels, elevation, single instance."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

MAGIC = 0x47534D43  # tag on dwExtraInfo so our listeners ignore our own input

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MOUSE_FLAGS = {
    ("left", True): 0x0002,   # MOUSEEVENTF_LEFTDOWN
    ("left", False): 0x0004,  # MOUSEEVENTF_LEFTUP
    ("right", True): 0x0008,  # MOUSEEVENTF_RIGHTDOWN
    ("right", False): 0x0010, # MOUSEEVENTF_RIGHTUP
}

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetKeyNameTextW.argtypes = (wintypes.LONG, wintypes.LPWSTR, ctypes.c_int)
user32.GetKeyNameTextW.restype = ctypes.c_int
user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetAncestor.restype = wintypes.HWND

GA_ROOT = 2
ERROR_ALREADY_EXISTS = 183
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080


def _send(inp: INPUT) -> None:
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


class Win32Output:
    """Implements player.Output via SendInput with hardware scan codes."""

    def _key(self, scan: int, ext: bool, up: bool) -> None:
        flags = KEYEVENTF_SCANCODE
        if ext:
            flags |= KEYEVENTF_EXTENDEDKEY
        if up:
            flags |= KEYEVENTF_KEYUP
        inp = INPUT(type=INPUT_KEYBOARD)
        inp.ki = KEYBDINPUT(wVk=0, wScan=scan & 0xFF, dwFlags=flags, time=0, dwExtraInfo=MAGIC)
        _send(inp)

    def key_down(self, scan: int, ext: bool) -> None:
        self._key(scan, ext, up=False)

    def key_up(self, scan: int, ext: bool) -> None:
        self._key(scan, ext, up=True)

    def _mouse(self, button: str, down: bool) -> None:
        inp = INPUT(type=INPUT_MOUSE)
        inp.mi = MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSE_FLAGS[(button, down)], time=0, dwExtraInfo=MAGIC)
        _send(inp)

    def mouse_down(self, button: str) -> None:
        self._mouse(button, True)

    def mouse_up(self, button: str) -> None:
        self._mouse(button, False)


def foreground_hwnd() -> int:
    return int(user32.GetForegroundWindow() or 0)


def root_hwnd(hwnd: int) -> int:
    return int(user32.GetAncestor(hwnd, GA_ROOT) or hwnd)


def make_noactivate(hwnd: int) -> None:
    """Make a top-level window never take keyboard focus (overlay): clicks on it
    don't steal the game's focus, and it stays out of Alt+Tab."""
    hwnd = root_hwnd(hwnd)
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)


def label_for(scan: int, ext: bool) -> str:
    lparam = (scan & 0xFF) << 16
    if ext:
        lparam |= 1 << 24
    buf = ctypes.create_unicode_buffer(64)
    n = user32.GetKeyNameTextW(lparam, buf, 64)
    if n > 0 and buf.value.strip():
        return buf.value
    return f"SC{scan}"


def is_admin() -> bool:
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> None:
    if getattr(sys, "frozen", False):
        exe, args = sys.executable, sys.argv[1:]
    else:
        exe, args = sys.executable, [sys.argv[0]] + sys.argv[1:]
    params = " ".join(f'"{a}"' for a in args)
    rc = shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
    sys.exit(0 if rc > 32 else 1)


_mutex_handle = None


def acquire_single_instance(name: str = "GenshinMacroSingleton") -> bool:
    global _mutex_handle
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    _mutex_handle = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
