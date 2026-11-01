"""Self-update: check a JSON manifest, download the new exe, swap it in via a .bat.

Manifest format (hosted anywhere, e.g. GitHub Releases "latest/download/manifest.json"):
    {"version": "1.2.0", "url": "https://.../GenshinMacro.exe"}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

APP_VERSION = "1.3.0"
DEFAULT_UPDATE_URL = "https://github.com/billy2204/genshin-macro/releases/latest/download/manifest.json"


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
    try:
        data = json.loads(text)
    except ValueError as ex:
        raise ValueError(f"Manifest không phải JSON: {ex}") from ex
    if not isinstance(data, dict) or "version" not in data or "url" not in data:
        raise ValueError("Manifest thiếu 'version' hoặc 'url'")
    return str(data["version"]), str(data["url"])


def _fetch_text(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": f"GenshinMacro/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8")


def check_for_update(manifest_url: str) -> Optional[tuple[str, str]]:
    """Return (version, download_url) if the manifest advertises a newer version, else None."""
    version, url = parse_manifest(_fetch_text(manifest_url))
    return (version, url) if is_newer(version, APP_VERSION) else None


def download(url: str, dest: Path, timeout: int = 60) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": f"GenshinMacro/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return dest


def make_swap_script(pid: int, target: Path, new_exe: Path) -> str:
    """Batch script: wait for `pid` to exit, copy new exe over target, relaunch, self-delete."""
    return "\r\n".join([
        "@echo off",
        ":wait",
        f'tasklist /FI "PID eq {pid}" 2>nul | find "{pid}" >nul',
        "if not errorlevel 1 (",
        "  timeout /t 1 /nobreak >nul",
        "  goto wait",
        ")",
        f'copy /y "{new_exe}" "{target}" >nul',
        f'start "" "{target}"',
        f'del "{new_exe}" >nul 2>&1',
        'del "%~f0"',
        "",
    ])


def clean_env() -> dict:
    """Environment without PyInstaller's onefile bookkeeping vars. A child started with
    them inherited fails with "invalid originating onefile parent process"."""
    return {k: v for k, v in os.environ.items() if not k.startswith(("_PYI", "_MEI"))}


def current_exe() -> Optional[Path]:
    return Path(sys.executable).resolve() if getattr(sys, "frozen", False) else None


def apply_update(new_exe: Path) -> None:
    """Spawn the swap script and exit the current process. Only valid when frozen."""
    target = current_exe()
    if target is None:
        raise RuntimeError("Chỉ cập nhật được khi chạy từ file .exe")
    script = Path(tempfile.gettempdir()) / "genshin_macro_update.bat"
    script.write_text(make_swap_script(os.getpid(), target, Path(new_exe)), encoding="utf-8")
    subprocess.Popen(
        ["cmd", "/c", str(script)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        close_fds=True,
        env=clean_env(),
    )
    os._exit(0)
