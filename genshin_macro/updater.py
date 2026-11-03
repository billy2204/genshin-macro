"""Self-update.

Two install styles are supported:
  * installed (Inno Setup, `unins000.exe` next to the exe): download the new Setup.exe and
    run it silently; the installer closes the app, replaces files and relaunches it.
  * portable (single exe anywhere): download the new exe and swap it in with a .bat that
    waits for both PyInstaller processes to exit and retries the copy until the file unlocks.

Manifest format (hosted e.g. on GitHub Releases "latest/download/manifest.json"):
    {"version": "1.3.1",
     "url": "https://.../GenshinMacroSetup.exe",        # installer (preferred when installed)
     "portable": "https://.../GenshinMacro.exe"}         # single-file exe (optional)
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

APP_VERSION = "1.3.4"
DEFAULT_UPDATE_URL = "https://github.com/billy2204/genshin-macro/releases/latest/download/manifest.json"
INSTALLER_FLAGS = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS"]


# ---- versions / manifest ---------------------------------------------------------
def _ver_tuple(v: str) -> tuple:
    v = v.strip().lstrip("vV")
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return _ver_tuple(remote) > _ver_tuple(local)


def parse_manifest(text: str) -> tuple[str, str]:
    data = parse_manifest_full(text)
    return data["version"], data["url"]


def parse_manifest_full(text: str) -> dict:
    try:
        data = json.loads(text)
    except ValueError as ex:
        raise ValueError(f"Manifest không phải JSON: {ex}") from ex
    if not isinstance(data, dict) or "version" not in data or "url" not in data:
        raise ValueError("Manifest thiếu 'version' hoặc 'url'")
    out = {"version": str(data["version"]), "url": str(data["url"])}
    if data.get("portable"):
        out["portable"] = str(data["portable"])
    return out


def _fetch_text(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": f"GenshinMacro/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def check_for_update(manifest_url: str) -> Optional[tuple[str, str]]:
    """Return (version, download_url) if newer. The URL is the installer when this copy is
    installed, else the portable exe (falling back to the installer URL)."""
    data = parse_manifest_full(_fetch_text(manifest_url))
    if not is_newer(data["version"], APP_VERSION):
        return None
    url = data["url"] if is_installed() else data.get("portable", data["url"])
    return data["version"], url


def download(url: str, dest: Path, timeout: int = 60) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": f"GenshinMacro/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return dest


# ---- process helpers ---------------------------------------------------------------
def clean_env() -> dict:
    """Environment without PyInstaller's onefile bookkeeping vars. A child started with
    them inherited fails with "invalid originating onefile parent process"."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}


def current_exe() -> Optional[Path]:
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def is_installed() -> bool:
    """True when running from an Inno Setup installation (uninstaller sits next to the exe)."""
    exe = current_exe()
    return exe is not None and (exe.parent / "unins000.exe").exists()


def parent_pid() -> int:
    """PID of our parent process (for a onefile build: the PyInstaller bootloader)."""
    if sys.platform != "win32":
        return os.getppid()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    TH32CS_SNAPPROCESS = 0x2
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel32.Process32FirstW.argtypes = (ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.argtypes = (ctypes.c_void_p, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    me = os.getpid()
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.th32ProcessID == me:
                return int(entry.th32ParentProcessID)
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return 0


# ---- portable swap ---------------------------------------------------------------------
def make_swap_script(pid: int, target: Path, new_exe: Path, parent_pid: int = 0) -> str:
    """Batch script: wait for our process (and the bootloader parent) to exit, copy the new
    exe over the target, retrying while the old image is still locked, relaunch, self-delete."""
    waits = [pid] + ([parent_pid] if parent_pid else [])
    lines = ["@echo off"]
    for n, p in enumerate(waits):
        lines += [
            f":wait{n}",
            f'tasklist /FI "PID eq {p}" 2>nul | find "{p}" >nul',
            "if not errorlevel 1 (",
            "  timeout /t 1 /nobreak >nul",
            f"  goto wait{n}",
            ")",
        ]
    lines += [
        "set tries=0",
        ":copy",
        f'copy /y "{new_exe}" "{target}" >nul 2>&1',
        "if errorlevel 1 (",
        "  set /a tries+=1",
        "  if %tries% geq 60 goto fail",
        "  timeout /t 1 /nobreak >nul",
        "  goto copy",
        ")",
        f'start "" "{target}"',
        f'del "{new_exe}" >nul 2>&1',
        'del "%~f0"',
        "exit /b 0",
        ":fail",
        f'start "" "{target}"',
        'del "%~f0"',
        "",
    ]
    return "\r\n".join(lines)


def apply_update(new_exe: Path) -> None:
    """Portable install: spawn the swap script and exit. Only valid when frozen."""
    target = current_exe()
    if target is None:
        raise RuntimeError("Chỉ cập nhật được khi chạy từ file .exe")
    script = Path(tempfile.gettempdir()) / "genshin_macro_update.bat"
    script.write_text(make_swap_script(os.getpid(), target, Path(new_exe), parent_pid()), encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
        env=clean_env(),
    )
    os._exit(0)


# ---- installer -----------------------------------------------------------------------------
def run_installer(setup_exe: Path) -> None:
    """Installed copy: run the downloaded Inno Setup installer silently and exit; it closes
    the app, replaces the files and relaunches."""
    subprocess.Popen([str(setup_exe)] + INSTALLER_FLAGS, close_fds=True, env=clean_env())
    os._exit(0)


def install_downloaded(path: Path) -> None:
    """Dispatch: installer when installed (or when the file looks like a setup), else swap."""
    if is_installed() or "setup" in path.name.lower():
        run_installer(path)
    else:
        apply_update(path)
