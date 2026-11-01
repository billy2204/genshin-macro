import json
from pathlib import Path

import pytest

from genshin_macro import updater
from genshin_macro.updater import APP_VERSION, is_newer, make_swap_script, parse_manifest


def test_app_version_is_semver():
    assert len(APP_VERSION.split(".")) == 3 and all(p.isdigit() for p in APP_VERSION.split("."))


def test_is_newer_compares_numerically():
    assert is_newer("1.2.0", "1.1.9")
    assert is_newer("1.10.0", "1.9.0")
    assert not is_newer("1.1.0", "1.1.0")
    assert not is_newer("1.0.0", "1.1.0")
    assert is_newer("v2.0", "1.9.9")  # tolerant of "v" prefix / fewer parts


def test_parse_manifest_requires_version_and_url():
    v, u = parse_manifest(json.dumps({"version": "1.2.0", "url": "https://x/y.exe"}))
    assert (v, u) == ("1.2.0", "https://x/y.exe")
    with pytest.raises(ValueError):
        parse_manifest(json.dumps({"version": "1.2.0"}))
    with pytest.raises(ValueError):
        parse_manifest("not json")


def test_swap_script_waits_copies_and_relaunches(tmp_path):
    target = tmp_path / "GenshinMacro.exe"
    new = tmp_path / "new.exe"
    script = make_swap_script(pid=1234, target=target, new_exe=new)
    assert "1234" in script
    assert str(target) in script and str(new) in script
    assert "copy /y" in script.lower()
    assert 'start "" ' in script
    assert "del " in script  # cleans itself up


def test_check_for_update_uses_fetcher(monkeypatch):
    monkeypatch.setattr(updater, "_fetch_text", lambda url, timeout=10: json.dumps({"version": "9.9.9", "url": "https://x/new.exe"}))
    assert updater.check_for_update("https://x/manifest.json") == ("9.9.9", "https://x/new.exe")
    monkeypatch.setattr(updater, "_fetch_text", lambda url, timeout=10: json.dumps({"version": APP_VERSION, "url": "https://x/new.exe"}))
    assert updater.check_for_update("https://x/manifest.json") is None


def test_clean_env_strips_pyinstaller_vars(monkeypatch):
    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
    monkeypatch.setenv("_PYI_APPLICATION_HOME_DIR", r"C:\x")
    monkeypatch.setenv("_MEIPASS2", r"C:\y")
    monkeypatch.setenv("PATH", "keep")
    env = updater.clean_env()
    assert not any(k.startswith(("_PYI", "_MEI")) for k in env)
    assert env["PATH"] == "keep"


def test_apply_update_spawns_script_with_clean_env(monkeypatch, tmp_path):
    spawned = {}

    class FakePopen:
        def __init__(self, args, **kw):
            spawned["args"] = args
            spawned["env"] = kw.get("env")

    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
    monkeypatch.setattr(updater, "current_exe", lambda: tmp_path / "GenshinMacro.exe")
    monkeypatch.setattr(updater.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(updater.os, "_exit", lambda code: None)
    updater.apply_update(tmp_path / "new.exe")
    assert spawned["env"] is not None and "_PYI_PARENT_PROCESS_LEVEL" not in spawned["env"]
    assert spawned["args"][0] == "cmd"


def test_swap_script_waits_for_both_pids_and_retries_copy(tmp_path):
    script = make_swap_script(pid=1234, target=tmp_path / "a.exe", new_exe=tmp_path / "b.exe", parent_pid=777)
    assert '"PID eq 1234"' in script and '"PID eq 777"' in script
    assert ":copy" in script and "goto copy" in script  # retry loop until the exe is no longer locked
    assert "fc " in script or "if errorlevel 1" in script


def test_parent_pid_is_a_positive_int():
    ppid = updater.parent_pid()
    assert isinstance(ppid, int) and ppid > 0 and ppid != updater.os.getpid()


def test_is_installed_detects_inno_uninstaller(tmp_path, monkeypatch):
    exe = tmp_path / "GenshinMacro.exe"
    exe.write_bytes(b"x")
    monkeypatch.setattr(updater, "current_exe", lambda: exe)
    assert updater.is_installed() is False
    (tmp_path / "unins000.exe").write_bytes(b"x")
    assert updater.is_installed() is True


def test_run_installer_uses_silent_flags(monkeypatch, tmp_path):
    spawned = {}

    class FakePopen:
        def __init__(self, args, **kw):
            spawned["args"] = args
            spawned["env"] = kw.get("env")

    monkeypatch.setenv("_PYI_PARENT_PROCESS_LEVEL", "1")
    monkeypatch.setattr(updater.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(updater.os, "_exit", lambda code: None)
    updater.run_installer(tmp_path / "Setup.exe")
    assert spawned["args"][0] == str(tmp_path / "Setup.exe")
    assert "/VERYSILENT" in spawned["args"] and "/CLOSEAPPLICATIONS" in spawned["args"]
    assert "_PYI_PARENT_PROCESS_LEVEL" not in spawned["env"]
